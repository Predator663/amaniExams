"use client";
import { useEffect, useState } from "react";
import ExamBuilder from "./ExamBuilder";
import { ErrorNote, Loading, useLoad } from "./ui";
import { api, downloadFile } from "@/lib/api";
import { DATETIME, eatDate } from "@/lib/clock";
import { errorLines, fromIso, plain, toIso } from "@/lib/staff";
import { useSession } from "@/lib/session";

type F = { title: string; subject: string; term: string; classes: number[]; start: string; end: string; duration: number; pass: number; rules: string;
  shuffleQ: boolean; shuffleO: boolean; skip: boolean; late: string; warnings: string; partial: boolean; neg: boolean; negFrac: number };
const blank: F = { title: "", subject: "", term: "", classes: [], start: "", end: "", duration: 60, pass: 30, rules: "", shuffleQ: true, shuffleO: true, skip: false, late: "", warnings: "", partial: true, neg: false, negFrac: 0.25 };

function Admin({ exam, reload }: { exam: any; reload: () => void }) {
  const paper = useLoad(() => api<any[]>(`/exams/${exam.id}/questions/`), [exam.id]);
  const [msg, setMsg] = useState(""), [errs, setErrs] = useState<string[]>([]), [q, setQ] = useState(""), [found, setFound] = useState<any[]>([]);
  const [g, setG] = useState({ student: 0, kind: "extra_time", minutes: 15, reason: "" });
  const run = async (fn: () => Promise<any>, ok: string) => { setMsg(""); setErrs([]); try { await fn(); setMsg(ok); reload(); paper.reload(); } catch (e: any) { setErrs(errorLines(e.data, e.message)); } };
  useEffect(() => { if (q.length < 2) return setFound([]); const t = setTimeout(() => api<any[]>(`/students/?q=${encodeURIComponent(q)}`).then((r) => setFound(r.slice(0, 6))).catch(() => {}), 400); return () => clearTimeout(t); }, [q]);
  const st = exam.status;
  return (
    <div className="card">
      <h2>Admin actions</h2>
      <div className="row">
        {st === "draft" && <button className="btn primary" onClick={() => run(() => api(`/exams/${exam.id}/schedule/`, { body: {} }), "Exam scheduled. Students can now see it.")}>Schedule exam</button>}
        {st === "scheduled" && <button className="btn" onClick={() => run(() => api(`/exams/${exam.id}/unschedule/`, { body: {} }), "Back to draft.")}>Unschedule</button>}
        {st === "live" && <button className="btn danger" onClick={() => { const r = window.prompt("Close this live exam NOW? Give a reason:"); if (r) run(() => api(`/exams/${exam.id}/close/`, { body: { confirm: true, reason: r } }), "Exam closed."); }}>Close exam now</button>}
        {(st === "closed" || st === "published") && <button className="btn" onClick={() => downloadFile(`/exports/exams/${exam.id}/results/`, `results-${exam.id}.xlsx`).catch((e) => setErrs([e.message]))}>⬇ Results (Excel)</button>}
      </div>
      {(st === "closed" || st === "published") && paper.data && (
        <>
          <h3>Void a faulty question</h3>
          <p className="muted small">Every affected result is recalculated automatically.</p>
          {paper.data.map((p) => <div key={p.id} className="row" style={{ margin: ".3rem 0" }}><span className="grow small">{p.position}. {plain(p.prompt).slice(0, 80)}{p.voided ? ` — VOIDED (${p.void_reason})` : ""}</span>
            {!p.voided && <button className="btn danger" onClick={() => { const r = window.prompt("Reason for voiding question " + p.position + ":"); if (r) run(() => api(`/exams/${exam.id}/void-question/`, { body: { exam_question_id: p.id, reason: r } }), "Question voided and results recalculated."); }}>Void</button>}</div>)}
        </>
      )}
      {st !== "draft" && (
        <>
          <h3>Extra time or retake for one student</h3>
          <label className="field"><span>Find the student</span><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, username or index number" /></label>
          {found.map((s) => <button key={s.id} className={`btn ${g.student === s.id ? "primary" : ""}`} style={{ margin: ".2rem" }} onClick={() => setG({ ...g, student: s.id })}>{s.first_name} {s.last_name}</button>)}
          <div className="grid2">
            <label className="field"><span>Grant</span><select className="input" value={g.kind} onChange={(e) => setG({ ...g, kind: e.target.value })}><option value="extra_time">Extra time</option><option value="retake">Retake</option></select></label>
            {g.kind === "extra_time" && <label className="field"><span>Minutes</span><input className="input" type="number" min={1} max={240} value={g.minutes} onChange={(e) => setG({ ...g, minutes: Number(e.target.value) })} /></label>}
          </div>
          <label className="field"><span>Reason (kept in the audit log)</span><input className="input" value={g.reason} onChange={(e) => setG({ ...g, reason: e.target.value })} /></label>
          <button className="btn primary" disabled={!g.student || !g.reason.trim()} onClick={() => run(() => api(`/exams/${exam.id}/grant/`, { body: { student_id: g.student, kind: g.kind, extra_minutes: g.minutes, reason: g.reason } }), "Granted and recorded in the audit log.")}>Grant</button>
        </>
      )}
      {errs.length > 0 && <div className="card error" role="alert">{errs.map((e, i) => <p key={i}>⚠ {e}</p>)}</div>}
      {msg && <p className="ok" role="status">✓ {msg}</p>}
    </div>
  );
}

/** EXM-01 .. EXM-09: details, window, options, paper, scheduling and special cases. */
export default function ExamForm({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { user, lang } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const subjects = useLoad(() => api<any[]>("/subjects/")), classes = useLoad(() => api<any[]>("/classes/")), terms = useLoad(() => api<any[]>("/terms/"));
  const [cid, setCid] = useState<number | null>(id);
  const exam = useLoad(() => (cid ? api<any>(`/exams/${cid}/`) : Promise.resolve(null)), [cid]);
  const [f, setF] = useState<F>(blank), [errs, setErrs] = useState<string[]>([]), [msg, setMsg] = useState(""), [busy, setBusy] = useState(false);
  const up = (p: Partial<F>) => setF((x) => ({ ...x, ...p }));
  useEffect(() => { const e = exam.data; if (e) setF({ title: e.title, subject: String(e.subject), term: e.term ? String(e.term) : "", classes: e.classes, start: fromIso(e.start_at), end: fromIso(e.end_at), duration: e.duration_minutes, pass: e.pass_mark_percent, rules: e.rules_text,
    shuffleQ: e.shuffle_questions, shuffleO: e.shuffle_options, skip: e.allow_skip, late: e.late_entry_minutes ?? "", warnings: (e.time_warnings || []).join(", "), partial: e.partial_marks, neg: e.negative_marking, negFrac: e.negative_fraction }); }, [exam.data]);

  async function save() {
    setBusy(true); setErrs([]); setMsg("");
    const body: any = { title: f.title, subject: Number(f.subject), duration_minutes: f.duration, shuffle_questions: f.shuffleQ, shuffle_options: f.shuffleO, allow_skip: f.skip,
      partial_marks: f.partial, negative_marking: f.neg, negative_fraction: f.negFrac };
    if (admin) Object.assign(body, { term: f.term ? Number(f.term) : null, classes: f.classes, start_at: toIso(f.start), end_at: toIso(f.end), pass_mark_percent: f.pass, rules_text: f.rules,
      late_entry_minutes: f.late === "" ? null : Number(f.late), time_warnings: f.warnings.split(",").map((x) => parseInt(x.trim())).filter((x) => x > 0) });
    try { const e = cid ? await api<any>(`/exams/${cid}/`, { method: "PATCH", body }) : await api<any>("/exams/", { body }); setCid(e.id); setMsg("Saved."); exam.reload(); }
    catch (e: any) { setErrs(errorLines(e.data, e.message)); }
    setBusy(false);
  }
  async function del() { if (!confirm("Delete this draft exam?")) return; try { await api(`/exams/${cid}/`, { method: "DELETE" }); onClose(); } catch (e: any) { setErrs(errorLines(e.data, e.message)); } }

  if (subjects.loading || classes.loading || terms.loading || exam.loading) return <Loading />;
  if (subjects.error || exam.error) return <ErrorNote error={subjects.error || exam.error} />;
  const e = exam.data, status = e?.status || "draft", editable = status === "draft" || (status === "scheduled" && admin);
  const num = (k: keyof F, label: string, props: any = {}) => <label className="field"><span>{label}</span><input className="input" type="number" value={f[k] as any} onChange={(ev) => up({ [k]: Number(ev.target.value) } as any)} disabled={!editable} {...props} /></label>;
  const chk = (k: keyof F, label: string) => <label className="switch"><input type="checkbox" checked={f[k] as boolean} disabled={!editable} onChange={(ev) => up({ [k]: ev.target.checked } as any)} /> {label}</label>;
  return (
    <div className="examform">
      <div className="row"><button className="btn" onClick={onClose}>← Back to list</button><span className="pill">{cid ? `#${cid}` : "New"} · {status}</span></div>
      {!editable && <p className="hint">A live or finished exam cannot be edited.</p>}
      {e?.submitted_at && <p className="hint">📨 Submitted by <b>{e.submitted_by_name || "a teacher"}</b> on {eatDate(e.submitted_at, DATETIME, lang)}{status === "draft" ? " · waiting to be scheduled" : ""}</p>}
      <div className="card">
        <label className="field"><span>Exam title</span><input className="input" value={f.title} disabled={!editable} onChange={(ev) => up({ title: ev.target.value })} /></label>
        <div className="grid2">
          <label className="field"><span>Subject (each subject is its own exam)</span><select className="input" disabled={!editable || !!cid} value={f.subject} onChange={(ev) => up({ subject: ev.target.value })}><option value="">Choose…</option>{subjects.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          {admin && <label className="field"><span>Term</span><select className="input" disabled={!editable} value={f.term} onChange={(ev) => up({ term: ev.target.value })}><option value="">None</option>{terms.data?.map((t) => <option key={t.id} value={t.id}>{t.year_name} – {t.name}</option>)}</select></label>}
        </div>
        {admin ? (
          <>
            <fieldset><legend>Who sits this exam (classes)</legend><div className="chips">{classes.data?.map((c) => { const on = f.classes.includes(c.id); return <label key={c.id} className={`chip ${on ? "on" : ""}`}><input type="checkbox" checked={on} disabled={!editable} onChange={() => up({ classes: on ? f.classes.filter((x) => x !== c.id) : [...f.classes, c.id] })} />{on ? "✓ " : ""}{c.name}</label>; })}</div></fieldset>
            <div className="grid2">
              <label className="field"><span>Starts (East Africa Time)</span><input className="input" type="datetime-local" value={f.start} disabled={!editable} onChange={(ev) => up({ start: ev.target.value })} /></label>
              <label className="field"><span>Window ends</span><input className="input" type="datetime-local" value={f.end} disabled={!editable} onChange={(ev) => up({ end: ev.target.value })} /></label>
              {num("duration", "Duration (minutes)", { min: 1 })}{num("pass", "Pass mark (%)", { min: 0, max: 100 })}
              <label className="field"><span>Late-entry window (min; empty = school setting)</span><input className="input" type="number" min={0} value={f.late} disabled={!editable} onChange={(ev) => up({ late: ev.target.value })} /></label>
              <label className="field"><span>Time warnings (minutes before end)</span><input className="input" value={f.warnings} disabled={!editable} placeholder="10, 5, 1" onChange={(ev) => up({ warnings: ev.target.value })} /></label>
            </div>
            <label className="field"><span>Rules shown to students before the exam</span><textarea className="input" rows={4} value={f.rules} disabled={!editable} onChange={(ev) => up({ rules: ev.target.value })} /></label>
          </>
        ) : <>{num("duration", "Duration (minutes)", { min: 1 })}<p className="muted small">An administrator sets the date, time and classes.</p></>}
        <div className="grid2">{chk("shuffleQ", "Shuffle questions")}{chk("shuffleO", "Shuffle answer options")}{chk("skip", "Allow skipping (no return)")}{chk("partial", "Partial marks (multi-answer, matching)")}{chk("neg", "Negative marking")}</div>
        {f.neg && num("negFrac", "Share of the marks lost for a wrong answer (0 to 1)", { min: 0, max: 1, step: 0.05 })}
        {errs.length > 0 && <div className="card error" role="alert">{errs.map((x, i) => <p key={i}>⚠ {x}</p>)}</div>}
        {msg && <p className="ok" role="status">✓ {msg}</p>}
        <div className="row"><button className="btn primary" disabled={busy || !editable || !f.title || !f.subject} onClick={save}>{cid ? "Save changes" : "Create exam"}</button>{cid && status === "draft" && <button className="btn danger" onClick={del}>Delete draft</button>}</div>
        {e?.start_at && <p className="muted small">Window: {eatDate(e.start_at, undefined, lang)} to {eatDate(e.end_at, undefined, lang)}</p>}
      </div>
      {!cid && <div className="hint">Save the exam details first. Then you can pick questions from the question bank, create new ones, and preview the paper.</div>}
      {cid && e && <ExamBuilder key={e.id} exam={e} reload={exam.reload} editable={editable} admin={admin} subjectName={subjects.data?.find((x) => x.id === e.subject)?.name || ""} />}
      {cid && e && admin && <Admin exam={e} reload={exam.reload} />}
    </div>
  );
}
