"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading, useLoad, useNow } from "@/components/ui";
import { api } from "@/lib/api";
import { clock } from "@/lib/clock";
import { useSession } from "@/lib/session";

const EVERY = 10_000;

type Kind = "live" | "offline" | "idle" | "done";
type Dossier = { id: number; name: string; cls: string; index: string; kind: Kind; answered: number; secs: number; left: number };
const KIND_LABEL: Record<Kind, string> = { live: "LIVE", offline: "NO SIGNAL", idle: "NOT STARTED", done: "SUBMITTED" };
const KIND_ORDER: Record<Kind, number> = { offline: 0, live: 1, idle: 2, done: 3 };
const initials = (n: string) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";

/** ADM-06 / TCH-08: live exam board. Refreshes by itself every 10 seconds; pauses while the tab is hidden.
 *  Admins see a card per student (green pulse = live, red = not live); teachers see numbers only.
 *  Status is always written in words too, never colour alone. */
function Monitor({ examId, title, admin }: { examId: number; title: string; admin: boolean }) {
  const { lang } = useSession();
  const [d, setD] = useState<any>(null), [err, setErr] = useState(""), [paused, setPaused] = useState(false), [fetchedAt, setFetchedAt] = useState(0);
  const [cls, setCls] = useState(""), [filter, setFilter] = useState<"all" | Kind>("all"), [q, setQ] = useState("");
  const busy = useRef(false);
  const now = useNow(1000);

  const load = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try { setD(await api<any>(`/exams/${examId}/monitor/`)); setFetchedAt(Date.now()); setErr(""); }
    catch (e: any) { setErr(e.message); }
    busy.current = false;
  }, [examId]);

  useEffect(() => { setD(null); load(); }, [load]);
  useEffect(() => {
    if (paused) return;
    const tick = () => { if (!document.hidden) load(); };
    const i = setInterval(tick, EVERY);
    const vis = () => { if (!document.hidden) load(); };  // refresh the moment the tab is shown again
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(i); document.removeEventListener("visibilitychange", vis); };
  }, [paused, load]);

  if (!d) return err ? <ErrorNote error={err} retry={load} /> : <Loading />;
  const tz = { timeZone: "Africa/Dar_es_Salaam" };
  const loc = lang === "sw" ? "sw-TZ" : "en-GB";
  const left = (secs: number) => Math.max(0, secs - (now - fetchedAt) / 1000);
  const started = d.in_progress + d.submitted;
  const live = d.status === "live";
  const stamp = new Date(fetchedAt).toLocaleTimeString(loc, tz);
  const clockNow = new Date(now).toLocaleTimeString(loc, tz);

  const all: Dossier[] = admin ? [
    ...(d.in_progress_students || []).map((x: any): Dossier => ({ id: x.id, name: x.name, cls: x.class, index: x.index || "", kind: x.online ? "live" : "offline", answered: x.answered, secs: x.seconds_left, left: x.left_screen })),
    ...(d.not_started_students || []).map((x: any): Dossier => ({ id: x.id, name: x.name, cls: x.class, index: x.index || "", kind: "idle", answered: 0, secs: 0, left: 0 })),
    ...(d.submitted_students || []).map((x: any): Dossier => ({ id: x.id, name: x.name, cls: x.class, index: x.index || "", kind: "done", answered: 0, secs: 0, left: x.left_screen })),
  ] : [];
  const classes = Array.from(new Set(all.map((x) => x.cls))).sort();
  const inClass = all.filter((x) => !cls || x.cls === cls);
  const count = (k: Kind) => inClass.filter((x) => x.kind === k).length;
  const needle = q.trim().toLowerCase();
  const shown = inClass
    .filter((x) => (filter === "all" || x.kind === filter) && (!needle || x.name.toLowerCase().includes(needle) || x.index.toLowerCase().includes(needle)))
    .sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.name.localeCompare(b.name));
  const liveNow = admin ? d.in_progress - (d.connection_problems || []).length : d.in_progress;
  const lost = admin ? (d.connection_problems || []).length : 0;

  return (
    <section className="ops" aria-label="Live exam board">
      <div className="ops-head">
        <span className={`ops-led ${live ? "on" : ""}`} aria-hidden />
        <div className="ops-id"><small>LIVE BOARD</small><b>{title}</b></div>
        <div className="ops-clock" role="timer" aria-label="Time now in Dar es Salaam">{clockNow}<small>EAT</small></div>
      </div>
      <div className="ops-bar row" role="status" aria-live="polite">
        <span className={`ops-state ${live ? "on" : ""}`}>{live ? "● LIVE" : `EXAM ${String(d.status).toUpperCase()}`}</span>
        <span className="ops-dim">Updated {stamp}{paused ? " · auto-refresh paused" : " · every 10 s"}</span>
        <span className="grow" />
        <button className="ops-btn" onClick={load}>↻ Refresh</button>
        <button className="ops-btn" aria-pressed={paused} onClick={() => { if (paused) load(); setPaused(!paused); }}>{paused ? "▶ Resume" : "⏸ Pause"}</button>
      </div>
      {err && <div className="offline-banner" role="alert">⚠ {err} Showing the last numbers; retrying…</div>}

      <div className="ops-kpis">
        <div className="kpi k-live"><b>{liveNow}</b><span>{admin ? "Live now" : "In progress"}</span></div>
        {admin && <div className={`kpi k-offline ${lost ? "alert" : ""}`}><b>{lost}</b><span>No signal</span></div>}
        <div className="kpi k-idle"><b>{d.not_started}</b><span>Not started</span></div>
        <div className="kpi k-done"><b>{d.submitted}</b><span>Submitted</span></div>
        <div className="kpi k-all"><b>{d.eligible}</b><span>Eligible</span></div>
      </div>
      <div className="ops-prog"><span>Started {started} of {d.eligible}</span><div className="ops-track" role="progressbar" aria-valuenow={d.eligible ? Math.round((started / d.eligible) * 100) : 0} aria-valuemin={0} aria-valuemax={100} aria-label="Students who have started"><i style={{ width: `${d.eligible ? (started / d.eligible) * 100 : 0}%` }} /></div></div>

      {!admin ? <p className="ops-note">Teachers see numbers only during a live exam. Results appear after they are published.</p> : (
        <>
          <div className="ops-tools">
            <div className="ops-chips" role="group" aria-label="Show students">
              {([["all", "All", inClass.length], ["live", "Live", count("live")], ["offline", "No signal", count("offline")], ["idle", "Not started", count("idle")], ["done", "Submitted", count("done")]] as [string, string, number][]).map(([k, l, n]) => (
                <button key={k} type="button" className={`ops-chip c-${k} ${filter === k ? "on" : ""}`} aria-pressed={filter === k} onClick={() => setFilter(k as any)}>{l} <b>{n}</b></button>
              ))}
            </div>
            <input className="ops-in" type="search" placeholder="Search name or index no." aria-label="Search students" value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="ops-in" aria-label="Class" value={cls} onChange={(e) => setCls(e.target.value)}><option value="">All classes</option>{classes.map((c) => <option key={c}>{c}</option>)}</select>
          </div>

          {!shown.length ? <p className="ops-note">{all.length ? "No students match this view." : "No students are assigned to this exam."}</p> : (
            <ul className="ops-grid">
              {shown.map((x) => {
                const pct = d.total_questions ? Math.round((x.answered / d.total_questions) * 100) : 0;
                const t = left(x.secs);
                return (
                  <li key={x.id} className={`dos k-${x.kind}`}>
                    <span className="dos-av" aria-hidden>{initials(x.name)}</span>
                    <div className="dos-main">
                      <div className="dos-name">{x.name}</div>
                      <div className="dos-meta">{x.cls}{x.index ? ` · ${x.index}` : ""}</div>
                      {(x.kind === "live" || x.kind === "offline") && (
                        <>
                          <div className="ops-track sm" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${x.name} progress`}><i style={{ width: `${pct}%` }} /></div>
                          <div className="dos-row"><span>{x.answered}/{d.total_questions} answered</span><span className={`dos-time ${t < 300 ? "low" : ""}`}>{clock(t * 1000)}</span></div>
                        </>
                      )}
                      {x.kind === "idle" && <div className="dos-row"><span>Has not opened the exam</span></div>}
                      {x.kind === "done" && <div className="dos-row"><span>Finished and submitted</span></div>}
                      {x.left > 0 && <div className="dos-warn" title="Information only: the student may have switched app by accident">⚠ Left screen {x.left}×</div>}
                    </div>
                    <span className="dos-tag"><i className="dot" aria-hidden />{KIND_LABEL[x.kind]}</span>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="ops-note">Green pulse = writing with a signal. Red = not live: no signal for 90 s, or the exam has not been opened. Blue = submitted. “Left screen” is information only.</p>
        </>
      )}
    </section>
  );
}

export default function MonitorPage() {
  const { user } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const exams = useLoad(() => api<any[]>("/exams/"));
  const [id, setId] = useState<number | null>(null);
  useEffect(() => {
    if (!exams.data || id) return;
    const q = new URLSearchParams(location.search).get("exam");
    const pick = (q && exams.data.find((e) => e.id === Number(q))) || exams.data.find((e) => e.status === "live") || [...exams.data].filter((e) => e.status === "scheduled").sort((a, b) => (a.start_at || "").localeCompare(b.start_at || ""))[0] || exams.data[0];
    if (pick) setId(pick.id);
  }, [exams.data, id]);
  const list = (exams.data || []).filter((e) => ["scheduled", "live", "closed"].includes(e.status));
  return (
    <Shell bare title="Live monitor">
      <StaffNav />
      {exams.loading ? <Loading /> : exams.error ? <ErrorNote error={exams.error} retry={exams.reload} /> : !list.length ? <div className="card"><p className="muted">No scheduled or live exam.</p></div> : (
        <>
          <label className="field"><span>Exam</span><select className="input" value={id || ""} onChange={(e) => setId(Number(e.target.value))}>{list.map((e) => <option key={e.id} value={e.id}>{e.title} ({e.status})</option>)}</select></label>
          {id && <Monitor key={id} examId={id} title={list.find((e) => e.id === id)?.title || "Exam"} admin={admin} />}
        </>
      )}
    </Shell>
  );
}
