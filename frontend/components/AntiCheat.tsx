"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { api } from "@/lib/api";

/* Anti-cheat tab of the Live monitor (administrators only).
   Draws every writing student on a plan view (metres, north up) from her phone's position, shows who is moving, and raises an
   alert when two students are closer than the alert distance (20 m by default, set on the server). No map tiles are loaded from
   other websites, so student positions never leave the school's own server. Alerts are information for a person to check,
   they are not proof of cheating (the Terms and Privacy policy say so). */

type Checks = { perm?: string; ble?: string; net?: string; motion?: string };
type PS = { id: number; name: string; class: string; index: string; lat: number; lng: number; accuracy: number; speed: number | null; heading: number | null;
  moving: boolean; moving_source: string; age_s: number; fresh: boolean; poor: boolean; checks: Checks };
type PA = { id: number; a: { id: number; name: string }; b: { id: number; name: string }; distance_m: number; min_distance_m: number; confidence: string;
  first_seen: string; last_seen: string; active: boolean; acknowledged: boolean; duration_s: number; lat?: number | null; lng?: number | null };
type NS = { id: number; name: string; class: string; index: string; last_seen_s: number | null; checks: Checks };
type PB = { server_time: string; exam: { id: number; title: string; status: string }; alert_meters: number; writing: number; students: PS[]; no_signal: NS[]; alerts: PA[]; enabled: boolean };
export type AcExam = { exam_id: number; title: string; status: string; in_progress: number };

const MPD = 111_320;
const NICE = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000];
const niceStep = (target: number) => NICE.find((n) => n >= target) ?? NICE[NICE.length - 1];
const fmtDist = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(m >= 10000 ? 0 : 1)} km` : `${Math.round(m)} m`);
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function beep() {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new Ctx(), o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination); o.type = "square"; o.frequency.value = 660; g.gain.value = 0.12;
    o.start(); o.stop(ctx.currentTime + 0.5);
  } catch { /* no sound */ }
}

/* Street, district, region, country for a position. Asked from the school server (which may ask a geocoder), cached per ~11 m cell. */
const placeCache = new Map<string, string | null>();
function PlaceLine({ lat, lng, prefix }: { lat?: number | null; lng?: number | null; prefix?: string }) {
  const key = lat == null || lng == null ? "" : `${lat.toFixed(4)},${lng.toFixed(4)}`;
  const [label, setLabel] = useState<string | null | undefined>(key ? placeCache.get(key) : null);
  useEffect(() => {
    if (!key) return;
    if (placeCache.has(key)) { setLabel(placeCache.get(key)); return; }
    setLabel(undefined);
    let live = true, tries = 0, timer: ReturnType<typeof setTimeout>;
    const go = async () => {
      try {
        const r = await api<{ label: string | null; enabled: boolean }>(`/proctoring/place/?lat=${key.split(",")[0]}&lng=${key.split(",")[1]}`);
        if (r.label || !r.enabled) { placeCache.set(key, r.label || null); if (live) setLabel(r.label || null); }
        else if (++tries < 4) timer = setTimeout(go, 1500);  // rate-limited or the service is slow: try again shortly
        else if (live) setLabel(null);
      } catch { if (live) setLabel(null); }
    };
    timer = setTimeout(go, 250);  // short delay so quickly passing the mouse over dots does not send requests
    return () => { live = false; clearTimeout(timer); };
  }, [key]);
  if (label === null || !key) return null;
  return <span className="ac-place">📍 {prefix}{label === undefined ? "Finding place name…" : label}</span>;
}

const checkText = (c: Checks) => {
  const loc = c.perm === "granted" ? "Location on" : c.perm === "denied" ? "Location BLOCKED" : "Location ?";
  const ble = c.ble === "on" ? "Bluetooth on" : c.ble === "off" ? "Bluetooth OFF" : "Bluetooth not readable";
  const net = c.net === "wifi" ? "Wi-Fi" : c.net === "cellular" ? "mobile data" : c.net === "none" ? "no network" : "network ?";
  const mo = c.motion === "moving" ? "device moving" : c.motion === "still" ? "device still" : "motion ?";
  return { loc, ble, net, mo, bad: c.perm === "denied" || c.ble === "off" };
};

/* ------------------------------------------------------------------ the plan view */
function ProxMap({ students, alerts, threshold, labels, focusReq }: { students: PS[]; alerts: PA[]; threshold: number; labels: boolean; focusReq: { ids: number[]; n: number } | null }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 640, h: 440 });
  const [view, setView] = useState({ cx: 0, cy: 0, k: 1 });
  const [auto, setAuto] = useState(true);
  const [tip, setTip] = useState<number | null>(null);
  const pts = useRef(new Map<number, { x: number; y: number }>());
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const pinch = useRef<{ d: number; k: number } | null>(null);

  const origin = useMemo(() => {
    const f = students.filter((s) => s.fresh);
    const src = f.length ? f : students;
    if (!src.length) return { lat: 0, lng: 0, c: 1 };
    const lat = src.reduce((s, p) => s + p.lat, 0) / src.length, lng = src.reduce((s, p) => s + p.lng, 0) / src.length;
    return { lat, lng, c: Math.cos((lat * Math.PI) / 180) };
  }, [students.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const xy = useCallback((p: { lat: number; lng: number }) => ({ x: (p.lng - origin.lng) * MPD * origin.c, y: -(p.lat - origin.lat) * MPD }), [origin]);
  const world = useMemo(() => new Map(students.map((s) => [s.id, xy(s)])), [students, xy]);

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(() => { const r = box.current!.getBoundingClientRect(); if (r.width) setSize({ w: r.width, h: r.height }); });
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const fit = useCallback(() => {
    const live = students.filter((s) => s.fresh);
    if (!live.length) return setView({ cx: 0, cy: 0, k: 1 });
    const ps = live.map((s) => world.get(s.id)!);
    const minX = Math.min(...ps.map((p) => p.x)), maxX = Math.max(...ps.map((p) => p.x));
    const minY = Math.min(...ps.map((p) => p.y)), maxY = Math.max(...ps.map((p) => p.y));
    const k = Math.min((size.w * 0.78) / Math.max(maxX - minX, 60), (size.h * 0.78) / Math.max(maxY - minY, 60));
    setView({ cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, k: Math.min(60, Math.max(0.002, k)) });
  }, [students, world, size]);
  useEffect(() => { if (auto) fit(); }, [auto, fit]);

  useEffect(() => {  // "Locate" on an alert: zoom so the pair fills the view
    if (!focusReq) return;
    const ps = focusReq.ids.map((id) => world.get(id)).filter(Boolean) as { x: number; y: number }[];
    if (!ps.length) return;
    const cx = ps.reduce((s, p) => s + p.x, 0) / ps.length, cy = ps.reduce((s, p) => s + p.y, 0) / ps.length;
    const span = ps.length > 1 ? Math.hypot(ps[0].x - ps[1].x, ps[0].y - ps[1].y) : 0;
    setAuto(false); setView({ cx, cy, k: Math.min(60, Math.min(size.w, size.h) * 0.8 / Math.max(span * 3, threshold * 3)) });
  }, [focusReq]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoom = useCallback((f: number, at?: { x: number; y: number }) => {
    setAuto(false);
    setView((v) => {
      const k = Math.min(60, Math.max(0.002, v.k * f));
      if (!at) return { ...v, k };
      const wx = v.cx + (at.x - size.w / 2) / v.k, wy = v.cy + (at.y - size.h / 2) / v.k;  // keep the point under the cursor fixed
      return { cx: wx - (at.x - size.w / 2) / k, cy: wy - (at.y - size.h / 2) / k, k };
    });
  }, [size]);

  useEffect(() => {  // wheel zoom needs a non-passive listener to stop the page from scrolling
    const el = box.current; if (!el) return;
    const h = (e: WheelEvent) => { e.preventDefault(); const r = el.getBoundingClientRect(); zoom(e.deltaY < 0 ? 1.25 : 0.8, { x: e.clientX - r.left, y: e.clientY - r.top }); };
    el.addEventListener("wheel", h, { passive: false });
    return () => el.removeEventListener("wheel", h);
  }, [zoom]);

  const sx = (x: number) => (x - view.cx) * view.k + size.w / 2, sy = (y: number) => (y - view.cy) * view.k + size.h / 2;

  const down = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.current.size === 1) drag.current = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy };
    if (pts.current.size === 2) { const [a, b] = [...pts.current.values()]; pinch.current = { d: Math.hypot(a.x - b.x, a.y - b.y), k: view.k }; drag.current = null; }
    setTip(null);
  };
  const move = (e: React.PointerEvent) => {
    if (!pts.current.has(e.pointerId)) return;
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.current.size === 2 && pinch.current) {
      const [a, b] = [...pts.current.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y);
      setAuto(false); setView((v) => ({ ...v, k: Math.min(60, Math.max(0.002, pinch.current!.k * (d / pinch.current!.d))) }));
    } else if (drag.current) {
      const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) { setAuto(false); setView((v) => ({ ...v, cx: drag.current!.cx - dx / v.k, cy: drag.current!.cy - dy / v.k })); }
    }
  };
  const up = (e: React.PointerEvent) => { pts.current.delete(e.pointerId); if (pts.current.size < 2) pinch.current = null; if (!pts.current.size) drag.current = null; };

  /* grid */
  const step = niceStep(110 / view.k);
  const x0 = view.cx - size.w / 2 / view.k, x1 = view.cx + size.w / 2 / view.k, y0 = view.cy - size.h / 2 / view.k, y1 = view.cy + size.h / 2 / view.k;
  const gx: number[] = [], gy: number[] = [];
  for (let x = Math.ceil(x0 / step) * step; x <= x1 && gx.length < 60; x += step) gx.push(x);
  for (let y = Math.ceil(y0 / step) * step; y <= y1 && gy.length < 60; y += step) gy.push(y);
  const barM = niceStep(90 / view.k), barPx = barM * view.k;

  const inAlert = new Map<number, PA>();
  alerts.filter((a) => a.active).forEach((a) => { inAlert.set(a.a.id, a); inAlert.set(a.b.id, a); });
  const tipS = tip != null ? students.find((s) => s.id === tip) : null;
  const tipPos = tipS ? { x: sx(world.get(tipS.id)!.x), y: sy(world.get(tipS.id)!.y) } : null;
  const tipAlert = tipS ? inAlert.get(tipS.id) : undefined;
  const cls = (s: PS) => (inAlert.has(s.id) ? "al" : !s.fresh ? "st" : s.poor ? "po" : s.moving ? "mv" : "ok");

  return (
    <div className="ac-map" ref={box}>
      <svg width={size.w} height={size.h} viewBox={`0 0 ${size.w} ${size.h}`} role="group" aria-label="Student positions" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <g className="ac-grid" aria-hidden="true">
          {gx.map((x) => <line key={"x" + x} x1={sx(x)} x2={sx(x)} y1={0} y2={size.h} />)}
          {gy.map((y) => <line key={"y" + y} x1={0} x2={size.w} y1={sy(y)} y2={sy(y)} />)}
        </g>
        {alerts.filter((a) => a.active).map((a) => {
          const p = world.get(a.a.id), q = world.get(a.b.id); if (!p || !q) return null;
          return (
            <g key={a.id} className="ac-link" aria-hidden="true">
              <line x1={sx(p.x)} y1={sy(p.y)} x2={sx(q.x)} y2={sy(q.y)} />
              <text x={(sx(p.x) + sx(q.x)) / 2} y={(sy(p.y) + sy(q.y)) / 2 - 8} textAnchor="middle">{fmtDist(a.distance_m)}</text>
            </g>
          );
        })}
        {students.map((s) => {
          const w = world.get(s.id)!, X = sx(w.x), Y = sy(w.y);
          if (X < -60 || Y < -60 || X > size.w + 60 || Y > size.h + 60) return null;
          const c = cls(s), moving = s.moving && s.fresh;
          return (
            <g key={s.id} className={`ac-pt ${c}`} transform={`translate(${X} ${Y})`} tabIndex={0} role="button"
              aria-label={`${s.name}, ${moving ? "moving" : "still"}${inAlert.has(s.id) ? ", too close to another student" : ""}`}
              onPointerDown={(e) => e.stopPropagation()} onMouseEnter={() => setTip(s.id)} onMouseLeave={() => setTip((t) => (t === s.id ? null : t))}
              onFocus={() => setTip(s.id)} onBlur={() => setTip((t) => (t === s.id ? null : t))} onClick={() => setTip(s.id)}
              onKeyDown={(e) => e.key === "Escape" && setTip(null)}>
              {s.accuracy * view.k > 12 && <circle className="ac-acc" r={Math.min(s.accuracy * view.k, 240)} />}
              {inAlert.has(s.id) && <circle className="ac-ring" r={Math.min(threshold * view.k, 600)} />}
              {moving && <circle className="ac-ripple" r={9} />}
              {moving && s.heading != null && s.speed != null && s.speed > 0.5 && <path className="ac-arrow" d="M0,-20 L5,-12 L-5,-12 Z" transform={`rotate(${s.heading})`} />}
              <circle className="ac-dot" r={9} />
              <text className="ac-ini" textAnchor="middle" dy=".35em">{s.name.trim().charAt(0).toUpperCase()}</text>
              {labels && <text className="ac-name" y={24} textAnchor="middle">{s.name}</text>}
            </g>
          );
        })}
        <g className="ac-scale" aria-hidden="true" transform={`translate(14 ${size.h - 18})`}>
          <line x1={0} x2={barPx} y1={0} y2={0} /><line x1={0} x2={0} y1={-4} y2={4} /><line x1={barPx} x2={barPx} y1={-4} y2={4} />
          <text x={barPx + 8} y={4}>{fmtDist(barM)}</text>
        </g>
        <g className="ac-north" aria-hidden="true" transform={`translate(${size.w - 22} 24)`}><path d="M0,-12 L6,6 L0,2 L-6,6 Z" /><text y="20" textAnchor="middle">N</text></g>
      </svg>
      <div className="ac-ctl">
        <button className="btn icon" aria-label="Zoom in" onClick={() => zoom(1.5)}>+</button>
        <button className="btn icon" aria-label="Zoom out" onClick={() => zoom(1 / 1.5)}>−</button>
        <button className={`btn icon ${auto ? "on" : ""}`} aria-label="Fit all students" title="Fit all students" onClick={() => setAuto(true)}><Icon n="pin" size={18} /></button>
      </div>
      {!students.length && <p className="ac-none">No student positions yet. They appear as soon as a student starts the exam.</p>}
      {tipS && tipPos && (() => {
        const c = checkText(tipS.checks || {});
        const left = Math.min(Math.max(tipPos.x + 16, 8), size.w - 236), top = Math.min(Math.max(tipPos.y - 12, 8), size.h - 200);
        const other = tipAlert ? (tipAlert.a.id === tipS.id ? tipAlert.b : tipAlert.a) : null;
        return (
          <div className="ac-tip" role="tooltip" style={{ left, top }}>
            <strong>{tipS.name}</strong>
            <small>{tipS.class}{tipS.index ? ` · #${tipS.index}` : ""}</small>
            <span className={tipS.moving ? "mv" : ""}>{!tipS.fresh ? `No update for ${tipS.age_s}s` : tipS.moving ? `Moving (${tipS.moving_source === "gps" ? "position changing" : "device motion"})` : "Staying still"}</span>
            <span>Accuracy ±{Math.round(tipS.accuracy)} m{tipS.poor ? " (too rough to compare)" : ""}{tipS.speed != null && tipS.speed > 0.3 ? ` · ${(tipS.speed * 3.6).toFixed(1)} km/h` : ""}</span>
            {other && <span className="al">⚠ {fmtDist(tipAlert!.distance_m)} from {other.name}</span>}
            <span className={c.bad ? "al" : "dim"}>{c.loc} · {c.ble} · {c.net} · {c.mo}</span>
            <PlaceLine lat={tipS.lat} lng={tipS.lng} prefix="Near " />
            <span className="dim">Updated {tipS.age_s}s ago</span>
          </div>
        );
      })()}
    </div>
  );
}

/* ------------------------------------------------------------------ the tab */
export default function AntiCheat({ exams }: { exams: AcExam[] }) {
  const list = useMemo(() => exams.filter((e) => e.status === "live" || e.in_progress > 0), [exams]);
  const [examId, setExamId] = useState<number | null>(null);
  const [data, setData] = useState<PB | null>(null);
  const [err, setErr] = useState("");
  const [labels, setLabels] = useState(true);
  const [focus, setFocus] = useState<{ ids: number[]; n: number } | null>(null);
  const seen = useRef<Set<number> | null>(null);
  const busy = useRef(false);

  useEffect(() => { if (!list.length) setExamId(null); else if (examId == null || !list.some((e) => e.exam_id === examId)) setExamId(list[0].exam_id); }, [list, examId]);

  const load = useCallback(async () => {
    if (examId == null || busy.current || document.hidden) return;
    busy.current = true;
    try {
      const d = await api<PB>(`/proctoring/exams/${examId}/`);
      setData(d); setErr("");
      const open = new Set(d.alerts.filter((a) => a.active && !a.acknowledged).map((a) => a.id));
      if (seen.current && [...open].some((id) => !seen.current!.has(id))) beep();
      seen.current = open;
    } catch (e: any) { setErr(e?.message || "Could not reach the server."); }
    finally { busy.current = false; }
  }, [examId]);

  useEffect(() => {
    seen.current = null; setData(null);
    load();
    const t = setInterval(load, 4000);
    const vis = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", vis); };
  }, [load]);

  const review = async (id: number) => { try { await api(`/proctoring/alerts/${id}/ack/`, { body: {} }); load(); } catch (e: any) { setErr(e?.message || "Could not save."); } };

  const active = data?.alerts.filter((a) => a.active) ?? [];
  const past = data?.alerts.filter((a) => !a.active) ?? [];
  const moving = data?.students.filter((s) => s.moving && s.fresh).length ?? 0;
  const tracked = data?.students.filter((s) => s.fresh).length ?? 0;

  if (!list.length) return <p className="lb-empty">No exam is being written right now. Positions appear here while an exam is live.</p>;
  return (
    <div className="ac">
      <div className="ac-top">
        <label className="ac-pick"><span>Exam</span>
          <select className="input" value={examId ?? ""} onChange={(e) => setExamId(Number(e.target.value))} aria-label="Exam">
            {list.map((e) => <option key={e.exam_id} value={e.exam_id}>{e.title}{e.status === "live" ? " · LIVE" : ""}</option>)}
          </select></label>
        <div className="lb-sum">
          <span><b>{data?.writing ?? "–"}</b><small>writing</small></span>
          <span><b>{data ? tracked : "–"}</b><small>located</small></span>
          <span><b>{data ? moving : "–"}</b><small>moving</small></span>
          <span className={active.length ? "ac-bad" : ""}><b>{data ? active.length : "–"}</b><small>too close</small></span>
        </div>
        <label className="ac-chk"><input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Show names</label>
      </div>
      {err && <p className="lb-alert" role="alert">{err} Retrying…</p>}
      {data && !data.enabled && <p className="lb-alert">Location monitoring is switched off on the server (PROCTORING_ENABLED=0).</p>}
      {active.length > 0 && (
        <div className="ac-banner" role="alert"><Icon n="shield" size={20} /> <b>{active.length === 1 ? "Two students are" : `${active.length} pairs of students are`} sitting less than {data?.alert_meters ?? 20} m apart.</b></div>
      )}
      <div className="ac-grid2">
        <div>
          <ProxMap students={data?.students ?? []} alerts={data?.alerts ?? []} threshold={data?.alert_meters ?? 20} labels={labels} focusReq={focus} />
          <p className="ac-legend" aria-hidden="true">
            <span><i className="d ok" />still</span><span><i className="d mv" />moving</span><span><i className="d al" />too close</span><span><i className="d po" />rough position</span><span><i className="d st" />no recent update</span>
          </p>
        </div>
        <aside className="ac-side">
          <h3>Alerts <small>({active.length} open)</small></h3>
          {!data ? <p className="lb-empty">Loading…</p> : !data.alerts.length ? <p className="lb-empty">Nobody has been closer than {data.alert_meters} m.</p> : (
            <ul className="ac-alerts">
              {[...active, ...past].map((a) => (
                <li key={a.id} className={a.active ? "on" : "off"}>
                  <div><b>{a.a.name}</b> &amp; <b>{a.b.name}</b></div>
                  <small>{a.active ? `${fmtDist(a.distance_m)} apart now` : `ended · closest ${fmtDist(a.min_distance_m)}`} · since {hhmm(a.first_seen)} · {a.confidence === "confirmed" ? "precise" : "rough position, check"}</small>
                  {a.active && <PlaceLine lat={a.lat} lng={a.lng} prefix="Near " />}
                  <div className="ac-act">
                    {a.active && <button className="btn" onClick={() => setFocus({ ids: [a.a.id, a.b.id], n: Date.now() })}>Locate</button>}
                    {a.acknowledged ? <small className="ok">Reviewed</small> : <button className="btn" onClick={() => review(a.id)}>Mark reviewed</button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <h3>No location signal <small>({data?.no_signal.length ?? 0})</small></h3>
          {data && !data.no_signal.length ? <p className="lb-empty">Every writing student is reporting a position.</p> : (
            <ul className="ac-alerts">
              {data?.no_signal.map((s) => { const c = checkText(s.checks || {}); return (
                <li key={s.id} className="off"><div><b>{s.name}</b> <small>{s.class}</small></div>
                  <small>{s.last_seen_s == null ? "Has not reported a position yet" : `Last position ${s.last_seen_s}s ago`} · {c.loc} · {c.ble}</small></li>); })}
            </ul>
          )}
          <p className="muted small">An alert is information to check, not proof of cheating: siblings or neighbours may live close by. Positions are kept only while the exam runs.</p>
        </aside>
      </div>
    </div>
  );
}
