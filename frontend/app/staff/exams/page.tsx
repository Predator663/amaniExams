"use client";
import { useEffect, useMemo, useState } from "react";
import ExamForm from "@/components/ExamForm";
import { Pager, useClientPage } from "@/components/Pager";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { DATETIME, ago, eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

/** EXM-03 / EXM-07: every exam with filters (status, class, subject, teacher, search) and sorting.
    Default order: papers teachers have just submitted (drafts waiting for an administrator) come first, newest on top,
    then live, scheduled (soonest first), other drafts, and finished exams. */

type Exam = any;
const STATUS_LABEL: Record<string, string> = { draft: "Draft", scheduled: "Scheduled", live: "Live", closed: "Closed", published: "Results published" };
const SORTS: [string, string][] = [
  ["smart", "Newly submitted first"], ["submitted", "Latest submission"], ["date_asc", "Exam date: soonest"], ["date_desc", "Exam date: latest"],
  ["created", "Recently created"], ["title", "Title A–Z"], ["subject", "Subject A–Z"],
];

const ts = (iso?: string | null) => (iso ? new Date(iso).getTime() : 0);
/** Group order for the default sort. Lower comes first. */
function rank(e: Exam) {
  if (e.awaiting_scheduling) return 0;
  if (e.status === "live") return 1;
  if (e.status === "scheduled") return 2;
  if (e.status === "draft") return 3;
  return 4;
}
function compare(sort: string) {
  const byTitle = (a: Exam, b: Exam) => a.title.localeCompare(b.title);
  switch (sort) {
    case "submitted": return (a: Exam, b: Exam) => (ts(b.submitted_at) - ts(a.submitted_at)) || (ts(b.created_at) - ts(a.created_at));
    case "date_asc": return (a: Exam, b: Exam) => (a.start_at ? 0 : 1) - (b.start_at ? 0 : 1) || ts(a.start_at) - ts(b.start_at);
    case "date_desc": return (a: Exam, b: Exam) => (a.start_at ? 0 : 1) - (b.start_at ? 0 : 1) || ts(b.start_at) - ts(a.start_at);
    case "created": return (a: Exam, b: Exam) => ts(b.created_at) - ts(a.created_at);
    case "title": return byTitle;
    case "subject": return (a: Exam, b: Exam) => a.subject_name.localeCompare(b.subject_name) || byTitle(a, b);
    default: return (a: Exam, b: Exam) => {
      const ra = rank(a), rb = rank(b);
      if (ra !== rb) return ra - rb;
      if (ra === 0) return ts(b.submitted_at) - ts(a.submitted_at);             // newest submission on top
      if (ra === 1 || ra === 2) return ts(a.start_at) - ts(b.start_at);          // soonest first
      if (ra === 3) return ts(b.created_at) - ts(a.created_at);                  // newest draft first
      return ts(b.start_at) - ts(a.start_at);                                    // finished: most recent first
    };
  }
}

function StatusPill({ e }: { e: Exam }) {
  if (e.awaiting_scheduling) return <span className="pill warn">⏳ Awaiting scheduling</span>;
  return <span className={`pill ${e.status === "live" ? "live" : ""}`}>{STATUS_LABEL[e.status] || e.status}</span>;
}

export default function Exams() {
  const { user, lang } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [edit, setEdit] = useState<number | "new" | null>(null);
  const list = useLoad(() => api<Exam[]>("/exams/"));
  const classes = useLoad(() => api<any[]>("/classes/"));
  const subjects = useLoad(() => api<any[]>("/subjects/"));
  const [q, setQ] = useState(""), [status, setStatus] = useState("all"), [cls, setCls] = useState(""), [subject, setSubject] = useState(""), [teacher, setTeacher] = useState("");
  const [sort, setSort] = useState("smart");

  useEffect(() => {
    const p = new URLSearchParams(location.search);
    const e = p.get("edit"); if (e) setEdit(e === "new" ? "new" : Number(e));
    const s = p.get("status"); if (s) setStatus(s);
  }, []);

  const all: Exam[] = list.data || [];
  const teachers = useMemo(() => {
    const m = new Map<string, string>();
    all.forEach((e) => { const id = e.submitted_by || e.created_by; const n = e.submitted_by_name || e.created_by_name; if (id && n) m.set(String(id), n); });
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [all]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: all.length, awaiting: 0, draft: 0, scheduled: 0, live: 0, closed: 0, published: 0 };
    all.forEach((e) => { c[e.status] = (c[e.status] || 0) + 1; if (e.awaiting_scheduling) c.awaiting++; });
    return c;
  }, [all]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all.filter((e) => {
      if (status === "awaiting" ? !e.awaiting_scheduling : status !== "all" && e.status !== status) return false;
      if (subject && String(e.subject) !== subject) return false;
      if (cls === "none" ? e.classes.length > 0 : cls && !e.classes.includes(Number(cls))) return false;
      if (teacher && String(e.submitted_by || e.created_by) !== teacher) return false;
      if (needle && !`${e.title} ${e.subject_name} ${e.class_names.join(" ")} ${e.submitted_by_name} ${e.created_by_name}`.toLowerCase().includes(needle)) return false;
      return true;
    }).sort(compare(sort));
  }, [all, q, status, cls, subject, teacher, sort]);

  const pg = useClientPage(rows, 10, [q, status, cls, subject, teacher, sort].join("|"));
  const filtered = !!(q || cls || subject || teacher || status !== "all");
  const reset = () => { setQ(""); setStatus("all"); setCls(""); setSubject(""); setTeacher(""); };
  const chips: [string, string][] = [["all", "All"], ["awaiting", "Awaiting scheduling"], ["draft", "Drafts"], ["scheduled", "Scheduled"], ["live", "Live"], ["closed", "Closed"], ["published", "Published"]];

  return (
    <Shell bare title="Exams">
      <StaffNav />
      {edit !== null ? <ExamForm id={edit === "new" ? null : edit} onClose={() => { setEdit(null); list.reload(); }} /> : (
        <>
          <div className="row"><button className="btn primary" onClick={() => setEdit("new")}>+ New exam</button><span className="grow" />
            <button className="btn" onClick={list.reload} aria-label="Refresh">↻ Refresh</button></div>

          {list.loading ? <Loading /> : list.error ? <ErrorNote error={list.error} retry={list.reload} /> : (
            <>
              <div className="card exf">
                <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, subject, class or teacher" aria-label="Search exams" />
                <div className="chips" role="group" aria-label="Status">
                  {chips.map(([k, l]) => (
                    <button key={k} type="button" className={`chip ${status === k ? "on" : ""}`} aria-pressed={status === k} onClick={() => setStatus(k)}>
                      {l}<span className="chip-n">{counts[k] ?? 0}</span>
                    </button>))}
                </div>
                <div className="exf-grid">
                  <label className="field"><span>Class</span>
                    <select className="input" value={cls} onChange={(e) => setCls(e.target.value)}>
                      <option value="">All classes</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}<option value="none">No class chosen yet</option>
                    </select></label>
                  <label className="field"><span>Subject</span>
                    <select className="input" value={subject} onChange={(e) => setSubject(e.target.value)}>
                      <option value="">All subjects</option>{subjects.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select></label>
                  {admin && <label className="field"><span>Teacher</span>
                    <select className="input" value={teacher} onChange={(e) => setTeacher(e.target.value)}>
                      <option value="">All teachers</option>{teachers.map(([id, n]) => <option key={id} value={id}>{n}</option>)}
                    </select></label>}
                  <label className="field"><span>Sort by</span>
                    <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}>{SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
                </div>
                <div className="row small muted"><span role="status">{rows.length} of {all.length} exam{all.length === 1 ? "" : "s"}</span><span className="grow" />
                  {filtered && <button className="linkbtn" onClick={reset}>Clear filters</button>}</div>
              </div>

              {!rows.length ? <div className="card"><p className="muted">{all.length ? "No exam matches these filters." : "No exams yet."}</p></div> :
                <div ref={pg.top}>{pg.rows.map((e) => (
                  <div key={e.id} className={`card exam-card ${e.awaiting_scheduling ? "new" : ""}`}>
                    <div className="row">
                      <span className="grow">
                        <b>{e.title}</b>
                        <span className="muted small exam-meta">
                          {e.subject_name}
                          {" · "}{e.class_names.length ? e.class_names.join(", ") : "No class yet"}
                          {" · "}{e.start_at ? eatDate(e.start_at, DATETIME, lang) : "No date yet"}
                          {" · "}{e.duration_minutes} min · {e.question_count} questions · {e.total_marks} marks
                        </span>
                      </span>
                      <StatusPill e={e} />
                      <button className="btn" onClick={() => setEdit(e.id)}>{e.awaiting_scheduling && admin ? "Review" : "Open"}</button>
                    </div>
                    {e.submitted_at ? (
                      <p className="small exam-sub">📨 Submitted by <b>{e.submitted_by_name || "a teacher"}</b> · {eatDate(e.submitted_at, DATETIME, lang)} <span className="muted">({ago(e.submitted_at, lang)})</span></p>
                    ) : e.created_by_name && e.status === "draft" ? (
                      <p className="small muted exam-sub">✏️ Draft by {e.created_by_name} · not submitted yet</p>
                    ) : null}
                  </div>))}</div>}
              <Pager {...pg.pager} />
            </>
          )}
        </>
      )}
    </Shell>
  );
}
