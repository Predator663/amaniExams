"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bar, ErrorNote, Loading } from "./ui";
import { api } from "@/lib/api";
import { DATETIME, ago, eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

/** What is happening on the site right now: live exams, teacher submissions waiting for an administrator, what is coming up,
    results waiting to be published, and (admins) who is online and the latest activity. Refreshes itself every 30 seconds. */

const TIME: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };
const nice = (a: string) => a.replace(/[._]/g, " ");

function Tile({ n, label, href, tone }: { n: number | string; label: string; href?: string; tone?: "bad" | "warn" | "good" }) {
  const body = <><b className={tone || ""}>{n}</b><span>{label}</span></>;
  return href ? <Link href={href} className="ov-tile link">{body}</Link> : <div className="ov-tile">{body}</div>;
}

export default function StaffOverview() {
  const { user, lang } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [d, setD] = useState<any>(null), [err, setErr] = useState(""), [first, setFirst] = useState(true), [at, setAt] = useState<Date | null>(null);
  const load = useCallback(async () => {
    try { setD(await api<any>("/overview/")); setErr(""); setAt(new Date()); } catch (e: any) { setErr(e.message); }
    setFirst(false);
  }, []);
  useEffect(() => {
    load();
    const i = setInterval(() => { if (document.visibilityState === "visible") load(); }, 30_000);
    return () => clearInterval(i);
  }, [load]);

  if (first) return <Loading />;
  if (!d) return <ErrorNote error={err || "Could not load the overview."} retry={load} />;
  const T = d.totals;
  const when = (iso: string) => eatDate(iso, DATETIME, lang);

  return (
    <div className="ov">
      {err && <p className="no small" role="alert">⚠ Could not refresh: {err}</p>}
      <div className="row small muted"><span>Updated {at ? eatDate(at.toISOString(), { hour: "2-digit", minute: "2-digit", second: "2-digit" }, lang) : ""} · refreshes every 30 s</span><span className="grow" /><button className="linkbtn" onClick={load}>↻ Refresh now</button></div>

      <div className="ov-tiles">
        <Tile n={T.live_exams} label="Live exams" href="/staff/monitor/" tone={T.live_exams ? "good" : undefined} />
        <Tile n={T.writing_now} label="Writing now" href="/staff/monitor/" />
        {admin && <Tile n={`${T.students_online}`} label="Students online" />}
        <Tile n={T.awaiting_scheduling} label="Awaiting scheduling" href="/staff/exams/?status=awaiting" tone={T.awaiting_scheduling ? "warn" : undefined} />
        <Tile n={T.scheduled} label="Scheduled" href="/staff/exams/?status=scheduled" />
        <Tile n={T.awaiting_results} label="Results pending" href="/staff/exams/?status=closed" />
        <Tile n={T.submitted_today} label="Papers handed in (24 h)" />
        {admin && <Tile n={T.proximity_alerts} label="Proximity alerts" href="/staff/monitor/" tone={T.proximity_alerts ? "bad" : undefined} />}
      </div>

      <section className="card">
        <div className="row"><h2 className="grow">🟢 Happening now</h2><Link className="btn" href="/staff/monitor/">Live monitor</Link></div>
        {!d.live.length ? <p className="muted">No exam is running right now.</p> : d.live.map((e: any) => {
          const pct = e.eligible ? Math.round((e.submitted / e.eligible) * 100) : 0;
          return (
            <div key={e.id} className="ov-item">
              <div className="row"><span className="grow"><b>{e.title}</b><br /><span className="muted small">{e.subject} · {e.classes.join(", ") || "—"} · ends {eatDate(e.end_at, TIME, lang)}</span></span>
                <Link className="btn primary" href={`/staff/monitor/?exam=${e.id}`}>Watch</Link></div>
              <Bar value={pct} label={`${e.title}: ${pct}% handed in`} />
              <p className="small muted">{e.writing} writing · {e.submitted} handed in · {Math.max(0, e.eligible - e.writing - e.submitted)} not started · {e.eligible} students</p>
            </div>);
        })}
      </section>

      <section className="card">
        <div className="row"><h2 className="grow">📨 {admin ? "Teacher submissions" : "Your submissions"} <span className="muted small">awaiting scheduling</span></h2>
          <Link className="btn" href="/staff/exams/?status=awaiting">See all ({T.awaiting_scheduling})</Link></div>
        {!d.pending_submissions.length ? <p className="muted">{admin ? "No teacher is waiting for you. New submissions appear here first." : "Nothing waiting. Submit a finished paper from the exam page."}</p> :
          <ul className="list">{d.pending_submissions.map((e: any) => (
            <li key={e.id} className="row">
              <span className="grow"><b>{e.title}</b><br /><span className="muted small">{e.subject} · {e.question_count} questions</span><br />
                <span className="small">👩‍🏫 <b>{e.submitted_by || "Teacher"}</b> · {when(e.submitted_at)} <span className="muted">({ago(e.submitted_at, lang)})</span></span></span>
              <Link className="btn primary" href={`/staff/exams/?edit=${e.id}`}>{admin ? "Review & schedule" : "Open"}</Link>
            </li>))}</ul>}
      </section>

      <div className="ov-cols">
        <section className="card">
          <h2>📅 Coming up</h2>
          {!d.upcoming.length ? <p className="muted">Nothing scheduled.</p> : <ul className="list">{d.upcoming.map((e: any) => (
            <li key={e.id}><b>{e.title}</b><br /><span className="muted small">{e.subject} · {e.classes.join(", ") || "—"}</span><br /><span className="small">{when(e.start_at)} · {e.duration_minutes} min</span></li>))}</ul>}
        </section>

        <section className="card">
          <h2>📊 Results</h2>
          {!d.awaiting_results.length && !d.recently_published.length ? <p className="muted">No finished exams yet.</p> : (
            <ul className="list">
              {d.awaiting_results.map((e: any) => <li key={`w${e.id}`}><b>{e.title}</b> <span className="pill warn">Closed</span><br /><span className="muted small">{e.subject} · results {e.results_at ? `due ${eatDate(e.results_at, DATETIME, lang)}` : "pending"}</span></li>)}
              {d.recently_published.map((e: any) => <li key={`p${e.id}`}><b>{e.title}</b> <span className="pill">Published</span><br /><span className="muted small">{e.subject} · {e.end_at ? when(e.end_at) : ""}</span></li>)}
            </ul>)}
        </section>
      </div>

      {admin && (
        <section className="card">
          <div className="row"><h2 className="grow">🧾 Recent activity</h2><Link className="btn" href="/staff/audit/">Audit log</Link></div>
          {!d.recent_activity?.length ? <p className="muted">Nothing recorded yet.</p> : <ul className="list">{d.recent_activity.map((a: any) => (
            <li key={a.id} className="row small"><span className="grow"><b>{a.actor}</b> · {nice(a.action)}{a.target ? ` #${a.target}` : ""}</span><span className="muted">{ago(a.at, lang)}</span></li>))}</ul>}
        </section>
      )}
    </div>
  );
}
