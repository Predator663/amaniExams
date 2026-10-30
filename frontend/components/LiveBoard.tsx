"use client";
import { memo, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import AntiCheat from "@/components/AntiCheat";
import Icon from "@/components/Icon";
import { api } from "@/lib/api";

/* Live monitor board. One request for the whole school, polled only while the tab is visible.
   Rows render only for the exam that is expanded, and only 40 at a time. Animations are
   transform/opacity/stroke-dashoffset only, and switch off for "reduce motion". */

type Stu = {
  id: number; name: string; class: string; index: string; parents?: { id: number; name: string; phone: string; relationship?: string }[];
  left_screen?: number; answered?: number; started_at?: string | null; submitted_at?: string | null;
  seconds_left?: number; online?: boolean; auto_submitted?: boolean; completion?: "full" | "partial"; attempt_no?: number;
  attempt_id?: number; leaves_used?: number; locked?: boolean; lock_reason?: string;
};
type ExamRow = {
  exam_id: number; title: string; subject: string; status: string; classes: string[];
  start_at: string; end_at: string; duration_minutes: number; eligible: number; in_progress: number;
  submitted: number; not_started: number; total_questions: number; full?: number; partial?: number;
  in_progress_students?: Stu[]; submitted_students?: Stu[]; not_started_students?: Stu[];
  connection_problems?: { id: number; name: string }[]; proximity_alerts?: number;
  leave_lock?: { enabled: boolean; limit: number };
};
type Board = { server_time: string; exams: ExamRow[]; totals: { live_exams: number; writing: number; submitted: number } };

/* one shared 1-second clock; only the tiny countdown cells subscribe to it */
const subs = new Set<() => void>();
let tickId: ReturnType<typeof setInterval> | null = null;
let nowSec = Math.floor(Date.now() / 1000);
function subscribe(fn: () => void) {
  subs.add(fn);
  if (!tickId) tickId = setInterval(() => { nowSec = Math.floor(Date.now() / 1000); subs.forEach((f) => f()); }, 1000);
  return () => { subs.delete(fn); if (!subs.size && tickId) { clearInterval(tickId); tickId = null; } };
}
const useNowSec = () => useSyncExternalStore(subscribe, () => nowSec, () => nowSec);

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const hhmm = (iso?: string | null) => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
const hhmmss = (iso?: string | null) => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";

/* trim-path ring: stroke-dashoffset draws the arc */
function Ring({ pct, size = 54, tone = "g", children }: { pct: number; size?: number; tone?: "g" | "b" | "r" | "a"; children?: React.ReactNode }) {
  const r = (size - 8) / 2, p = Math.max(0, Math.min(1, pct));
  return (
    <span className={`lb-ring t-${tone}`} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="lb-ring-bg" cx={size / 2} cy={size / 2} r={r} />
        <circle className="lb-ring-fg" cx={size / 2} cy={size / 2} r={r} pathLength={1} strokeDasharray={1} style={{ strokeDashoffset: 1 - p }} />
      </svg>
      <span className="lb-ring-txt">{children}</span>
    </span>
  );
}

const Countdown = memo(function Countdown({ base, at, total }: { base: number; at: number; total: number }) {
  const n = useNowSec();
  const left = Math.max(0, base - (n - at));
  return <Ring pct={total ? left / total : 0} size={46} tone={left < 300 ? "r" : "g"}><b>{mmss(left)}</b></Ring>;
});

function StartsIn({ startIso, offset, onDue }: { startIso: string; offset: number; onDue: () => void }) {
  const n = useNowSec();
  const left = Math.floor(Date.parse(startIso) / 1000) - (n + offset);
  useEffect(() => { if (left <= 0) { const t = setTimeout(onDue, 800); return () => clearTimeout(t); } }, [left <= 0, n]); // eslint-disable-line
  return <span className="lb-soon">{left > 0 ? `Starts in ${left >= 3600 ? Math.floor(left / 3600) + "h " : ""}${mmss(left % 3600)}` : "Starting…"}</span>;
}

/** Parent numbers arrive masked. "Show number" asks the server for this one number and the reveal is audited. */
function ParentPhone({ g }: { g: { id: number; name: string; phone: string; relationship?: string } }) {
  const [full, setFull] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function reveal() {
    setBusy(true);
    try { const r = (await api(`/proctoring/guardians/${g.id}/reveal-phone/`, { body: {} })) as { phone: string }; setFull(r.phone); } catch { /* not allowed or offline */ }
    setBusy(false);
  }
  const label = `${g.relationship || "Parent"}: ${g.name} · `;
  return full
    ? <a className="lb-tel" href={`tel:${full}`}>{label}{full}</a>
    : <span className="lb-tel">{label}{g.phone} <button className="btn small" disabled={busy} onClick={reveal}>Show number</button></span>;
}

const Row = memo(function Row({ s, kind, total, at, dur, admin, leave, onLock }: { s: Stu; kind: "w" | "s" | "n"; total: number; at: number; dur: number; admin: boolean; leave?: { enabled: boolean; limit: number }; onLock?: (s: Stu, lock: boolean) => void }) {
  const pct = total ? (s.answered ?? 0) / total : 0;
  const used = s.leaves_used ?? 0;
  const why = s.lock_reason === "leaves" ? "locked: left the screen too often" : s.lock_reason === "manual" ? "locked by an administrator" : "";
  const state = kind === "w" ? (s.online ? "on" : "off") : kind === "s" ? "done" : "idle";
  return (
    <li className={`lb-row s-${state}`}>
      <span className="lb-pulse" aria-hidden="true" />
      <div className="lb-who">
        <strong>{s.name}</strong>
        <small>{s.class} · #{s.index}{(s.left_screen ?? 0) > 0 && <em className="lb-flag"> · left screen ×{s.left_screen}{kind === "w" && leave?.enabled ? ` (${used}/${leave.limit} allowed)` : ""}</em>}{kind === "w" && s.locked && <em className="lb-locked"> · 🔒 {why}</em>}</small>
        {kind === "w" && admin && s.attempt_id && onLock && (
          <button className={`btn small lb-lockbtn ${s.locked ? "primary" : ""}`} onClick={() => onLock(s, !s.locked)}>{s.locked ? "🔓 Unlock" : "🔒 Lock"}</button>
        )}
        {admin && (s.parents?.length
          ? s.parents.slice(0, 3).map((g) => <ParentPhone key={g.id} g={g} />)
          : <small className="lb-nophone">No parent number on file</small>)}
      </div>
      {kind === "n" && <div className="lb-prog"><small>{dur ? "Has not written this exam" : ""}</small></div>}
      {kind === "w" && (
        <div className="lb-prog">
          <div className="lb-bar"><i style={{ transform: `scaleX(${pct})` }} /></div>
          <small>{s.answered ?? 0}/{total} answered · started {hhmm(s.started_at)}</small>
        </div>
      )}
      {kind === "s" && (
        <div className="lb-prog">
          <small>{s.completion === "full" ? "Completed" : "Partial"} · submitted <b>{hhmmss(s.submitted_at)}</b>{s.auto_submitted ? " (time ran out)" : ""}</small>
          <small>{s.answered ?? 0}/{total} answered · started {hhmm(s.started_at)}</small>
        </div>
      )}
      {kind === "w" && <Countdown base={s.seconds_left ?? 0} at={at} total={dur * 60} />}
      {kind === "s" && <Ring pct={total ? (s.answered ?? 0) / total : 0} size={44} tone={s.completion === "full" ? "b" : "a"}><b>{total ? Math.round(((s.answered ?? 0) / total) * 100) : 0}%</b></Ring>}
    </li>
  );
});

function ExamCard({ e, open, onToggle, admin, at, q, cls, offset, onDue, onChanged }: { e: ExamRow; open: boolean; onToggle: () => void; admin: boolean; at: number; q: string; cls: string; offset: number; onDue: () => void; onChanged: () => void }) {
  const [tab, setTab] = useState<"w" | "f" | "p" | "n">("w");
  const [lockErr, setLockErr] = useState("");
  // Manual lock / unlock of one student. An unlock also gives her a fresh allowance of exits.
  const setLock = useCallback(async (s: Stu, lock: boolean) => {
    if (!s.attempt_id) return;
    if (lock && !window.confirm(`Lock ${s.name}'s exam now? Her timer keeps running until you unlock her.`)) return;
    try { await api(`/proctoring/attempts/${s.attempt_id}/${lock ? "lock" : "unlock"}/`, { body: {} }); setLockErr(""); onChanged(); }
    catch (err: any) { setLockErr(err?.message || "Could not change the lock."); }
  }, [onChanged]);
  const [limit, setLimit] = useState(40);
  useEffect(() => setLimit(40), [tab, q, cls, open]);
  const live = e.status === "live", soon = e.status === "scheduled";
  const list = useMemo(() => {
    const sub = e.submitted_students ?? [];
    const src = (tab === "w" ? e.in_progress_students : tab === "f" ? sub.filter((x) => x.completion === "full")
      : tab === "p" ? sub.filter((x) => x.completion !== "full") : e.not_started_students) ?? [];
    const t = q.trim().toLowerCase();
    return src.filter((s) => (!cls || s.class === cls) && (!t || s.name.toLowerCase().includes(t) || String(s.index).toLowerCase().includes(t)));
  }, [e, tab, q, cls]);
  const done = e.eligible ? (e.submitted / e.eligible) : 0;
  return (
    <section className={`lb-card ${live ? "is-live" : "is-done"}`}>
      <button className="lb-head" onClick={onToggle} aria-expanded={open}>
        <Ring pct={done} size={58} tone={live ? "g" : "b"}><b>{Math.round(done * 100)}%</b></Ring>
        <span className="lb-title">
          <strong>{e.title}</strong>
          <small>{e.subject} · {e.classes.join(", ") || "—"}</small>
          <small>{hhmm(e.start_at)}–{hhmm(e.end_at)} · {e.duration_minutes} min · {e.total_questions} questions</small>
        </span>
        <span className="lb-stats">
          {soon ? <StartsIn startIso={e.start_at} offset={offset} onDue={onDue} /> : <span className={live ? "lb-live" : "lb-closed"}>{live ? "LIVE" : e.status.toUpperCase()}</span>}
          <small><b>{e.in_progress}</b> writing · <b>{e.submitted}</b> submitted · <b>{e.not_started}</b> not started</small>
        </span>
      </button>
      {open && (
        <div className="lb-body">
          {!!e.connection_problems?.length && (
            <p className="lb-alert">No signal for 90 s: {e.connection_problems.map((c) => c.name).join(", ")}</p>
          )}
          {admin ? (
            <>
              <div className="lb-tabs" role="tablist">
                {([["w", "Writing", e.in_progress], ["f", "Completed", e.full ?? 0], ["p", "Partial", e.partial ?? 0], ["n", live ? "Not started" : "Did not sit", e.not_started]] as const).map(([k, label, n]) => (
                  <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label} <b>{n}</b></button>
                ))}
              </div>
              {live && e.leave_lock && <p className="muted small">{e.leave_lock.enabled ? `Auto-lock is on: a student who leaves the exam screen more than ${e.leave_lock.limit} time${e.leave_lock.limit === 1 ? "" : "s"} is locked until you unlock her.` : "Auto-lock for leaving the screen is off (Settings → School)."} You can also lock or unlock any student by hand.</p>}
              {lockErr && <p className="lb-alert" role="alert">{lockErr}</p>}
              {list.length === 0 ? <p className="lb-empty">Nobody here{q || cls ? " for this filter" : " yet"}.</p> : (
                <ul className="lb-list">
                  {list.slice(0, limit).map((s) => <Row key={s.id} s={s} kind={tab === "w" ? "w" : tab === "n" ? "n" : "s"} total={e.total_questions} at={at} dur={e.duration_minutes} admin={admin} leave={e.leave_lock} onLock={setLock} />)}
                </ul>
              )}
              {list.length > limit && <button className="lb-more" onClick={() => setLimit(limit + 40)}>Show {Math.min(40, list.length - limit)} more</button>}
            </>
          ) : <p className="lb-empty">Teachers see the counts above. Student names are for administrators.</p>}
        </div>
      )}
    </section>
  );
}

export default function LiveBoard({ admin: adminProp }: { admin?: boolean }) {
  const [board, setBoard] = useState<Board | null>(null);
  const [err, setErr] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [cls, setCls] = useState("");
  const [show, setShow] = useState<"all" | "live" | "done">("all");
  const [days, setDays] = useState(1);
  const [fetchedAt, setFetchedAt] = useState(Math.floor(Date.now() / 1000));
  const [offset, setOffset] = useState(0);
  const [toast, setToast] = useState("");
  const [tabView, setTabView] = useState<"exams" | "ac">("exams");
  const lastAlerts = useRef<number | null>(null);
  const liveIds = useRef<Set<number> | null>(null);
  const busy = useRef(false);

  const load = useCallback(async () => {
    if (busy.current || document.hidden) return;
    busy.current = true;
    try {
      const b = (await api(`/exams/monitor-board/?days=${days}`)) as Board;
      setBoard(b); setErr(""); setFetchedAt(Math.floor(Date.now() / 1000));
      setOffset(Math.round(Date.parse(b.server_time) / 1000 - Date.now() / 1000));
      const now = new Set(b.exams.filter((x) => x.status === "live").map((x) => x.exam_id));
      const fresh = liveIds.current ? b.exams.find((x) => now.has(x.exam_id) && !liveIds.current!.has(x.exam_id)) : undefined;
      liveIds.current = now;
      const nAl = b.exams.reduce((n, x) => n + (x.proximity_alerts ?? 0), 0);  // open, not yet reviewed
      if (lastAlerts.current !== null && nAl > lastAlerts.current) {
        setToast("⚠ Two students are sitting close together. Open the Anti-cheat tab."); setTimeout(() => setToast(""), 12000);
      }
      lastAlerts.current = nAl;
      if (fresh) { setToast(`${fresh.title} has started`); setOpenId(fresh.exam_id); setTimeout(() => setToast(""), 8000); }
      else setOpenId((cur) => cur ?? b.exams.find((x) => x.status === "live")?.exam_id ?? null);
    } catch (e: any) { setErr(e?.message || "Could not reach the server."); }
    finally { busy.current = false; }
  }, [days]);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    const vis = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", vis); };
  }, [load]);

  const classes = useMemo(() => {
    const s = new Set<string>();
    board?.exams.forEach((e) => e.classes.forEach((c) => s.add(c)));
    return [...s].sort();
  }, [board]);
  const admin = adminProp ?? (!board?.exams.length || !!board.exams[0].in_progress_students);
  const openAlerts = (board?.exams ?? []).reduce((n, x) => n + (x.proximity_alerts ?? 0), 0);
  const exams = (board?.exams ?? []).filter((e) => (show === "all" || (show === "live") === (e.status === "live")) && (!cls || e.classes.includes(cls)));

  return (
    <div className="lb">
      <header className="lb-top">
        <div className="lb-sum">
          <span><b>{board?.totals.live_exams ?? "–"}</b><small>exams live</small></span>
          <span><b>{board?.totals.writing ?? "–"}</b><small>writing now</small></span>
          <span><b>{board?.totals.submitted ?? "–"}</b><small>submitted</small></span>
        </div>
        <div className="lb-tools">
          <input className="input" placeholder="Search name or index no." value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search students" />
          <select className="input" value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Class">
            <option value="">All classes</option>
            {classes.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select className="input" value={days} onChange={(e) => { setBoard(null); setDays(Number(e.target.value)); }} aria-label="Period">
            <option value={1}>Last 24 hours</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={120}>This term (120 days)</option>
          </select>
          <select className="input" value={show} onChange={(e) => setShow(e.target.value as any)} aria-label="Exams">
            <option value="all">All exams</option><option value="live">Live only</option><option value="done">Finished only</option>
          </select>
        </div>
      </header>
      {admin && (
        <div className="lb-tabs lb-main-tabs" role="tablist" aria-label="Monitor view">
          <button role="tab" aria-selected={tabView === "exams"} className={tabView === "exams" ? "on" : ""} onClick={() => setTabView("exams")}>Exams</button>
          <button role="tab" aria-selected={tabView === "ac"} className={tabView === "ac" ? "on" : ""} onClick={() => setTabView("ac")}>
            <Icon n="radar" size={15} /> Anti-cheat{openAlerts > 0 && <b className="lb-badge">{openAlerts}</b>}
          </button>
        </div>
      )}
      {toast && <p className="lb-toast" role="status">▶ {toast}</p>}
      {err && <p className="lb-alert" role="alert">{err} Retrying…</p>}
      {!board && !err && <p className="lb-empty">Loading…</p>}
      {board && exams.length === 0 && <p className="lb-empty">No exams in this period. Pick a longer period to see older exams and who did or missed them.</p>}
      {admin && tabView === "ac" && <AntiCheat exams={(board?.exams ?? []).map((e) => ({ exam_id: e.exam_id, title: e.title, status: e.status, in_progress: e.in_progress }))} />}
      <div className="lb-grid" style={admin && tabView === "ac" ? { display: "none" } : undefined}>
        {exams.map((e) => (
          <ExamCard key={e.exam_id} e={e} open={openId === e.exam_id} onToggle={() => setOpenId(openId === e.exam_id ? null : e.exam_id)}
            admin={admin} at={fetchedAt} q={q} cls={cls} offset={offset} onDue={load} onChanged={load} />
        ))}
      </div>
    </div>
  );
}
