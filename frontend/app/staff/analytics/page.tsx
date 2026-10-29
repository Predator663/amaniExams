"use client";
import { useState } from "react";
import { Pager, useClientPage, usePaged } from "@/components/Pager";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { Bar, ErrorNote, Loading, useLoad, Tabs } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import { plain } from "@/lib/staff";

/** TCH-06: topic mastery by class. The number and a symbol carry the meaning, colour only helps (ACC-05). */
function HeatMap({ subject }: { subject: number }) {
  const h = useLoad(() => api<any>(`/analytics/subjects/${subject}/heatmap/`), [subject]);
  const tp = useClientPage<string>(h.data?.topics, 10, String(subject));
  if (h.loading) return <Loading />;
  if (h.error || !h.data) return <ErrorNote error={h.error} retry={h.reload} />;
  const { topics, classes, cells } = h.data;
  const first = (tp.page - 1) * tp.pager.size;
  if (!topics.length) return <div className="card"><p className="muted">No published results yet.</p></div>;
  const mark = (v: number | null) => (v === null ? "–" : v >= 70 ? "▲" : v >= 50 ? "●" : "▼");
  const bg = (v: number | null) => (v === null ? "transparent" : `color-mix(in srgb, var(--primary) ${Math.round(v * 0.6)}%, var(--surface))`);
  return (
    <div className="card">
      <p className="muted small">▲ 70% or more (strong) · ● 50 to 69% · ▼ below 50% (reteach)</p>
      <div className="tbl-wrap"><table><thead><tr><th>Topic</th>{classes.map((c: any) => <th key={c.id}>{c.label}</th>)}</tr></thead>
        <tbody>{tp.rows.map((t: string, k: number) => { const i = first + k; return ( <tr key={t}><td>{t}</td>{cells[i].map((v: number | null, j: number) => <td key={j} style={{ background: bg(v), color: "var(--text)", fontWeight: 700 }}>{mark(v)} {v === null ? "" : `${Math.round(v)}%`}</td>)}</tr>); })}</tbody></table></div>
      <Pager {...tp.pager} onSize={undefined} />
    </div>
  );
}

/** TCH-03, TCH-04: students in the teacher's classes with flags, and one student's profile. */
function Students({ subject }: { subject: number }) {
  const [open, setOpen] = useState<number | null>(null);
  const list = usePaged<any>(`/analytics/subjects/${subject}/students/`, {}, { size: 20 });
  const prof = useLoad(() => (open ? api<any>(`/analytics/subjects/${subject}/students/${open}/`) : Promise.resolve(null)), [subject, open]);
  if (list.loading) return <Loading />;
  if (list.error) return <ErrorNote error={list.error} retry={list.reload} />;
  if (open && prof.data) {
    const p = prof.data;
    return (
      <div className="card">
        <button className="btn" onClick={() => setOpen(null)}>← All students</button>
        <h2>{p.name} <span className="muted small">{p.class}</span></h2>
        {p.flag && <p className="hint">{p.flag === "needs_support" ? "⚠ Needs support" : "★ Top performer"}: {p.flag_reason}</p>}
        <div className="grid3"><div className="stat"><b>{p.average ?? "–"}%</b>Average</div><div className="stat"><b>{p.participation.taken}/{p.participation.eligible}</b>Exams taken</div><div className="stat"><b>{p.average_time_taken_seconds ? Math.round(p.average_time_taken_seconds / 60) : "–"} min</b>Avg time</div></div>
        <h3>Scores over time</h3>
        <div className="row" role="img" aria-label="Scores over time" style={{ alignItems: "flex-end", height: 90 }}>{p.scores_over_time.map((h: any, i: number) => <div key={i} title={`${h.exam}: ${h.percent}%`} style={{ flex: 1, height: `${Math.max(4, h.percent)}%`, background: "var(--primary)", borderRadius: 4 }} />)}</div>
        <h3>Topics</h3>{p.topics.map((t: any) => <div key={t.topic} style={{ margin: ".4rem 0" }}><div className="row"><span className="grow">{t.topic}</span><b>{Math.round(t.percent)}%</b></div><Bar value={t.percent} label={t.topic} /></div>)}
        <h3>Engagement</h3>
        <p>🔥 Streak {p.streak.current} (best {p.streak.best}) · Practice sessions {p.practice_activity.practice_sessions} (last 30 days {p.practice_activity.practice_sessions_last_30_days}) · XP {p.engagement.total_xp}</p>
      </div>
    );
  }
  return (
    <div className="card"><div className="tbl-wrap paged" ref={list.top} aria-busy={list.busy || undefined}><table><thead><tr><th>Student</th><th>Class</th><th>Avg %</th><th>Latest</th><th>Taken</th><th>Streak</th><th>Flag</th></tr></thead><tbody>
      {list.rows.map((s) => <tr key={s.student_id}><td><button className="btn" onClick={() => setOpen(s.student_id)}>{s.name}</button></td><td>{s.class}</td><td>{s.average ?? "–"}</td><td>{s.latest ?? "–"}</td><td>{s.exams_taken}/{s.exams_eligible}</td><td>{s.current_streak}</td>
        <td>{s.flag === "needs_support" ? "⚠ Support" : s.flag === "top_performer" ? "★ Top" : ""}</td></tr>)}</tbody></table></div>
      <Pager {...list.pager} /></div>
  );
}

/** TCH-05: per question, the percentage correct, the most chosen wrong answer and the observed difficulty. */
function QuestionAnalysis({ subject }: { subject: number }) {
  const exams = useLoad(() => api<any[]>("/exams/"));
  const [id, setId] = useState<number | null>(null);
  const q = useLoad(() => (id ? api<any>(`/analytics/exams/${id}/questions/`) : Promise.resolve(null)), [id]);
  const integ = useLoad(() => (id ? api<any>(`/analytics/exams/${id}/integrity/`) : Promise.resolve(null)), [id]);
  const qp = useClientPage<any>(q.data?.questions, 15, String(id));
  const ip = useClientPage<any>(integ.data?.flags, 10, String(id));
  const done = (exams.data || []).filter((e) => e.subject === subject && e.status === "published");
  return (
    <div className="card">
      <label className="field"><span>Exam (results published)</span><select className="input" value={id || ""} onChange={(e) => setId(Number(e.target.value) || null)}><option value="">Choose…</option>{done.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}</select></label>
      {!done.length && !exams.loading && <p className="muted">No exam of this subject has published results yet.</p>}
      {q.loading && id && <Loading />}
      {q.data && (
        <>
          <p className="muted">{q.data.students} students</p>
          <div className="tbl-wrap" ref={qp.top}><table><thead><tr><th>#</th><th>Question</th><th>Topic</th><th>% correct</th><th>Difficulty (marked → observed)</th><th>Most chosen wrong answer</th></tr></thead><tbody>
            {qp.rows.map((r: any) => <tr key={r.exam_question_id}><td>{r.number}</td><td>{plain(r.prompt).slice(0, 70)}{r.voided ? " (voided)" : ""}</td><td>{r.topic}</td><td><b>{r.percent_correct ?? "–"}%</b></td><td>{r.marked_difficulty} → {r.observed_difficulty}</td><td>{r.most_chosen_wrong ? `${plain(r.most_chosen_wrong.text)} (${r.most_chosen_wrong.share}%)` : "–"}</td></tr>)}</tbody></table></div>
          <Pager {...qp.pager} />
        </>
      )}
      {integ.data && integ.data.flags.length > 0 && <><h3>Left the exam screen</h3><p className="muted small">{integ.data.note}</p><ul className="list" ref={ip.top}>{ip.rows.map((f: any) => <li key={f.student_id}>{f.name}: {f.times_left_screen} time(s)</li>)}</ul><Pager {...ip.pager} onSize={undefined} /></>}
    </div>
  );
}

export default function Analytics() {
  const subjects = useLoad(() => api<any[]>("/analytics/subjects/"));
  const [sid, setSid] = useState<number | null>(null), [tab, setTab] = useState("heat"), [err, setErr] = useState("");
  return (
    <Shell bare title="Analytics">
      <StaffNav />
      {subjects.loading ? <Loading /> : subjects.error ? <ErrorNote error={subjects.error} retry={subjects.reload} /> : (
        <>
          <label className="field"><span>Subject</span><select className="input" value={sid || ""} onChange={(e) => setSid(Number(e.target.value) || null)}><option value="">Choose…</option>{subjects.data!.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          {sid && (
            <>
              <Tabs tabs={[["heat", "Topic heat map"], ["students", "Students"], ["questions", "Question analysis"]]} value={tab} onChange={setTab} />
              {tab === "heat" && <HeatMap subject={sid} />}{tab === "students" && <Students subject={sid} />}{tab === "questions" && <QuestionAnalysis subject={sid} />}
              <div className="row"><button className="btn" onClick={() => downloadFile(`/analytics/subjects/${sid}/export/?file=xlsx`, `subject-${sid}.xlsx`).catch((e) => setErr(e.message))}>⬇ Excel report</button><button className="btn" onClick={() => downloadFile(`/analytics/subjects/${sid}/export/?file=pdf`, `subject-${sid}.pdf`).catch((e) => setErr(e.message))}>⬇ PDF report</button></div>
              {err && <p className="no" role="alert">{err}</p>}
            </>
          )}
        </>
      )}
    </Shell>
  );
}
