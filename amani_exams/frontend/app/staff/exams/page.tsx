"use client";
import { useEffect, useState } from "react";
import ExamForm from "@/components/ExamForm";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

/** EXM-03: the exam timetable, grouped by day; EXM-07: status Draft -> Scheduled -> Live -> Closed -> Results Published. */
export default function Exams() {
  const { lang } = useSession();
  const [edit, setEdit] = useState<number | "new" | null>(null);
  const list = useLoad(() => api<any[]>("/exams/"));
  const subjects = useLoad(() => api<any[]>("/subjects/"));
  useEffect(() => { const e = new URLSearchParams(location.search).get("edit"); if (e) setEdit(e === "new" ? "new" : Number(e)); }, []);
  const days = new Map<string, any[]>();
  [...(list.data || [])].sort((a, b) => (a.start_at || "9").localeCompare(b.start_at || "9")).forEach((e) => {
    const k = e.start_at ? eatDate(e.start_at, { weekday: "long", day: "numeric", month: "long", year: "numeric" }, lang) : "No date yet (draft)";
    days.set(k, [...(days.get(k) || []), e]);
  });
  return (
    <Shell bare title="Exams">
      <StaffNav />
      {edit !== null ? <ExamForm id={edit === "new" ? null : edit} onClose={() => { setEdit(null); list.reload(); }} /> : (
        <>
          <button className="btn primary" onClick={() => setEdit("new")}>+ New exam</button>
          {list.loading ? <Loading /> : list.error ? <ErrorNote error={list.error} retry={list.reload} /> : !days.size ? <div className="card"><p className="muted">No exams yet.</p></div> :
            [...days.entries()].map(([day, items]) => (
              <section key={day}><h2>{day}</h2>
                {items.map((e) => (
                  <div key={e.id} className="card row">
                    <span className="grow"><b>{e.title}</b><br /><span className="muted small">{subjects.data?.find((s) => s.id === e.subject)?.name} · {e.start_at ? eatDate(e.start_at, { hour: "2-digit", minute: "2-digit" }, lang) : "—"} · {e.duration_minutes} min · {e.question_count} questions · {e.total_marks} marks</span></span>
                    <span className="pill">{e.status}</span><button className="btn" onClick={() => setEdit(e.id)}>Open</button>
                  </div>))}
              </section>))}
        </>
      )}
    </Shell>
  );
}
