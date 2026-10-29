"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import QuestionEditor from "./QuestionEditor";
import { Pager } from "./Pager";
import QuestionView from "./QuestionView";
import { Loading } from "./ui";
import { api } from "@/lib/api";
import { eatDate } from "@/lib/clock";
import { canonicalOrder, groupSections } from "@/lib/sections";
import { errorLines, plain, qtypeName, QTYPES } from "@/lib/staff";
import type { Question } from "@/lib/types";

type Q = { id: number; subject: number; form_level: number; topic: string; subtopic: string; difficulty: string; marks: number; qtype: string; prompt: string; content: any; answer: any; explanation: string; used_count?: number; last_used?: string | null };
type Filters = { q: string; topic: string; difficulty: string; qtype: string; form_level: string; usage: string; sort: string; page: number; size: number };
const F0: Filters = { q: "", topic: "", difficulty: "", qtype: "", form_level: "", usage: "", sort: "newest", page: 1, size: 10 };

/** What the question looks like on the paper. With `showKey` the correct answer is filled in (staff only, never sent to students). */
function keyValue(q: Q): any {
  const a = q.answer || {};
  switch (q.qtype) {
    case "mcq_single": case "mcq_multi": case "true_false": return a.correct;
    case "matching": return a.pairs;
    case "fill_blank": return (a.accepted && a.accepted[0]) ?? (a.numeric ? String(a.numeric.value) : "");
    case "ordering": return a.order;
  }
}
function QPreview({ q, showKey, n }: { q: Q; showKey: boolean; n?: number }) {
  const view: Question = { id: q.id, type: q.qtype as any, prompt: q.prompt, marks: q.marks, content: q.content };
  return (
    <div className="qprev">
      {n !== undefined && <span className="qprev-n">{n}</span>}
      <div className="grow"><QuestionView q={view} value={showKey ? keyValue(q) : undefined} onChange={() => {}} disabled /></div>
    </div>
  );
}

const Diff = ({ d }: { d: string }) => <span className={`dpill d-${d}`}>{d}</span>;

/* ------------------------------------------------------------------ pagination */

/* ------------------------------------------------------------------ question bank picker */
function Bank({ exam, selIds, onToggle, onAddMany, onCreate }: { exam: any; selIds: Set<number>; onToggle: (q: Q) => void; onAddMany: (qs: Q[]) => void; onCreate: () => void }) {
  const [f, setF] = useState<Filters>(F0), [text, setText] = useState("");
  const [res, setRes] = useState<any>(null), [busy, setBusy] = useState(true), [err, setErr] = useState(""), [open, setOpen] = useState<number | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const set = (p: Partial<Filters>) => setF((x) => ({ ...x, page: 1, ...p }));
  useEffect(() => { const t = setTimeout(() => setF((x) => (x.q === text ? x : { ...x, q: text, page: 1 })), 350); return () => clearTimeout(t); }, [text]);
  const key = JSON.stringify(f);
  useEffect(() => {
    let live = true; setBusy(true);
    const qs = new URLSearchParams({ page: String(f.page), page_size: String(f.size), sort: f.sort });
    (["q", "topic", "difficulty", "qtype", "form_level", "usage"] as const).forEach((k) => f[k] && qs.set(k, f[k]));
    api<any>(`/exams/${exam.id}/bank/?${qs}`)
      .then((r) => { if (!live) return; setRes(r); setErr(""); if (r.page !== f.page) setF((x) => ({ ...x, page: r.page })); })
      .catch((e) => live && setErr(e.message)).finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [exam.id, key]); // eslint-disable-line react-hooks/exhaustive-deps
  const goto = (p: number) => { setF((x) => ({ ...x, page: p })); top.current?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const filtered = !!(f.q || f.topic || f.difficulty || f.qtype || f.form_level || f.usage);
  const results: Q[] = res?.results || [];
  const notAdded = results.filter((q) => !selIds.has(q.id));

  if (!res && busy) return <Loading />;
  if (err && !res) return <div className="card error" role="alert"><p>⚠ {err}</p></div>;
  if (res && res.total_approved === 0) return (
    <div className="card bld-empty"><h3>No approved questions for this subject yet</h3><p className="muted">Create the first one right here. It is approved and added to this exam straight away.</p><button className="btn primary" onClick={onCreate}>+ Create a question</button></div>
  );
  return (
    <div ref={top}>
      <div className="card bld-filters-card">
        <div className="bld-search"><span aria-hidden>🔎</span><input className="input" type="search" placeholder="Search question text, topic or sub-topic…" aria-label="Search questions" value={text} onChange={(e) => setText(e.target.value)} /></div>
        <div className="seg" role="group" aria-label="Show questions">
          {[["", "All"], ["unused", "Never used"], ["used", "Used before"]].map(([v, l]) => <button key={v} type="button" className={f.usage === v ? "on" : ""} aria-pressed={f.usage === v} onClick={() => set({ usage: v })}>{l}</button>)}
        </div>
        <div className="bld-filters">
          <label className="field"><span>Topic</span><select className="input" value={f.topic} onChange={(e) => set({ topic: e.target.value })}><option value="">All topics</option>{res?.topics.map((t: string) => <option key={t}>{t}</option>)}</select></label>
          <label className="field"><span>Difficulty</span><select className="input" value={f.difficulty} onChange={(e) => set({ difficulty: e.target.value })}><option value="">Any</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
          <label className="field"><span>Type</span><select className="input" value={f.qtype} onChange={(e) => set({ qtype: e.target.value })}><option value="">Any</option>{QTYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label className="field"><span>Form</span><select className="input" value={f.form_level} onChange={(e) => set({ form_level: e.target.value })}><option value="">Any</option>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>Form {n}</option>)}</select></label>
          <label className="field"><span>Sort</span><select className="input" value={f.sort} onChange={(e) => set({ sort: e.target.value })}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="topic">Topic A–Z</option></select></label>
          <label className="field"><span>Per page</span><select className="input" value={f.size} onChange={(e) => set({ size: Number(e.target.value) })}>{[10, 20, 50].map((n) => <option key={n}>{n}</option>)}</select></label>
        </div>
        {filtered && <button className="btn ghost" onClick={() => { setText(""); setF({ ...F0, size: f.size }); }}>✕ Clear filters</button>}
      </div>

      <div className="row bld-count">
        <span className="grow muted small" aria-live="polite">{res?.count ?? 0} question{res?.count === 1 ? "" : "s"}{filtered ? " match" : ""} · page {res?.page} of {res?.pages}</span>
        {notAdded.length > 0 && <button className="btn" onClick={() => onAddMany(notAdded)}>+ Add all {notAdded.length} on this page</button>}
      </div>
      {err && <p className="no" role="alert">⚠ {err}</p>}
      <div className={busy ? "bld-list busy" : "bld-list"}>
        {!results.length ? <div className="card"><p className="muted">No questions match these filters.</p></div> : results.map((q) => {
          const on = selIds.has(q.id), isOpen = open === q.id;
          return (
            <article key={q.id} className={`qcard ${on ? "on" : ""}`}>
              <div className="qc-main">
                <div className="qc-meta">
                  <span className="pill">{qtypeName(q.qtype)}</span>
                  {q.topic && <span className="pill">{q.topic}</span>}
                  <Diff d={q.difficulty} /><span className="muted small">Form {q.form_level} · {q.marks} mark{q.marks === 1 ? "" : "s"}</span>
                  {q.used_count ? <span className="pill used" title={q.last_used ? `Last used ${new Date(q.last_used).toLocaleDateString()}` : ""}>Used in {q.used_count} other exam{q.used_count === 1 ? "" : "s"}</span> : <span className="pill fresh">Never used</span>}
                </div>
                <p className="qc-text">{plain(q.prompt).slice(0, 220) || "(image only)"}</p>
                <button className="linkbtn" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : q.id)}>{isOpen ? "Hide preview ▲" : "Preview with answer ▼"}</button>
                {isOpen && <div className="qc-preview"><QPreview q={q} showKey />{q.explanation && <p className="muted small"><b>Explanation:</b> {plain(q.explanation)}</p>}</div>}
              </div>
              <button className={`btn qc-add ${on ? "" : "primary"}`} aria-pressed={on} onClick={() => onToggle(q)}>{on ? "✓ Added" : "+ Add"}</button>
            </article>
          );
        })}
      </div>
      <Pager page={res?.page || 1} pages={res?.pages || 1} count={res?.count || 0} size={f.size} onPage={goto} onSize={(n) => set({ size: n })} busy={busy} />
    </div>
  );
}

/* ------------------------------------------------------------------ random rules */
function Random({ exam, selIds, onAdded }: { exam: any; selIds: Set<number>; onAdded: (qs: Q[]) => void }) {
  const [rules, setRules] = useState([{ topic: "", difficulty: "", count: 5 }]), [topics, setTopics] = useState<string[]>([]), [err, setErr] = useState<string[]>([]), [busy, setBusy] = useState(false);
  useEffect(() => { api<any>(`/exams/${exam.id}/bank/?page_size=1`).then((r) => setTopics(r.topics)).catch(() => {}); }, [exam.id]);
  const upd = (i: number, p: any) => setRules(rules.map((r, j) => (j === i ? { ...r, ...p } : r)));
  async function go() {
    setBusy(true); setErr([]);
    try { const qs = await api<Q[]>(`/exams/${exam.id}/pick/`, { body: { rules: rules.filter((r) => r.count > 0).map((r) => ({ ...r, topic: r.topic || undefined, difficulty: r.difficulty || undefined })), exclude: [...selIds] } }); onAdded(qs); }
    catch (e: any) { setErr(errorLines(e.data, e.message)); }
    setBusy(false);
  }
  return (
    <div className="card">
      <h3>Add random questions</h3>
      <p className="muted small">For example 10 easy and 5 hard from one topic. Questions already in your selection are skipped. You can review and remove any of them afterwards.</p>
      {rules.map((r, i) => (
        <div key={i} className="row" style={{ marginBottom: ".5rem" }}>
          <select className="input grow" aria-label="Topic" value={r.topic} onChange={(e) => upd(i, { topic: e.target.value })}><option value="">Any topic</option>{topics.map((t) => <option key={t}>{t}</option>)}</select>
          <select className="input" style={{ width: 130 }} aria-label="Difficulty" value={r.difficulty} onChange={(e) => upd(i, { difficulty: e.target.value })}><option value="">Any level</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select>
          <input className="input" style={{ width: 90 }} type="number" min={1} aria-label="How many" value={r.count} onChange={(e) => upd(i, { count: Number(e.target.value) })} />
          {rules.length > 1 && <button className="btn danger icon" aria-label="Remove rule" onClick={() => setRules(rules.filter((_, j) => j !== i))}>✕</button>}
        </div>))}
      <div className="row"><button className="btn" onClick={() => setRules([...rules, { topic: "", difficulty: "", count: 5 }])}>+ Another rule</button><button className="btn primary" disabled={busy} onClick={go}>🎲 Add random questions</button></div>
      {err.length > 0 && <div className="card error" role="alert" style={{ marginTop: ".7rem" }}>{err.map((e, i) => <p key={i}>⚠ {e}</p>)}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ selected list */
function Selected({ sel, onRemove, onMove, onClear, onPreview, narrow }: { sel: Q[]; onRemove: (id: number) => void; onMove: (id: number, d: -1 | 1) => void; onClear: () => void; onPreview: () => void; narrow?: boolean }) {
  const secs = groupSections(sel), marks = sel.reduce((a, q) => a + Number(q.marks), 0);
  return (
    <div className={`card bld-sel ${narrow ? "" : "bld-aside"}`}>
      <div className="row"><h3 className="grow" style={{ margin: 0 }}>Current exam</h3>{sel.length > 0 && <button className="btn ghost" onClick={onClear}>Clear</button>}</div>
      <div className="bld-totals"><div><b>{sel.length}</b><span>question{sel.length === 1 ? "" : "s"}</span></div><div><b>{Math.round(marks * 100) / 100}</b><span>marks</span></div><div><b>{secs.length}</b><span>section{secs.length === 1 ? "" : "s"}</span></div></div>
      {!sel.length ? <p className="muted small">Nothing selected yet. Add questions from the bank, create new ones, or add random ones.</p> : (
        <div className="bld-sel-list">
          {secs.map((s) => (
            <div key={s.qtype}>
              <p className="bld-sec-h"><b>Section {s.letter}</b> · {s.title} <span className="muted">({s.items.length} · {s.marks} marks)</span></p>
              {s.items.map((q, i) => (
                <div key={q.id} className="bld-sel-row">
                  <span className="grow small">{plain(q.prompt).slice(0, 70) || "(image only)"}</span>
                  <button className="btn ghost icon" disabled={i === 0} aria-label="Move up" onClick={() => onMove(q.id, -1)}>↑</button>
                  <button className="btn ghost icon" disabled={i === s.items.length - 1} aria-label="Move down" onClick={() => onMove(q.id, 1)}>↓</button>
                  <button className="btn ghost icon" aria-label="Remove from exam" onClick={() => onRemove(q.id)}>✕</button>
                </div>))}
            </div>))}
        </div>)}
      <button className="btn primary big" disabled={!sel.length} onClick={onPreview}>Review &amp; preview paper →</button>
    </div>
  );
}

/* ------------------------------------------------------------------ paper preview */
function PaperPreview({ exam, subjectName, sel }: { exam: any; subjectName: string; sel: Q[] }) {
  const [key, setKey] = useState(false), secs = groupSections(sel), marks = sel.reduce((a, q) => a + Number(q.marks), 0);
  let n = 0;
  return (
    <div className="paper">
      <div className="row" style={{ justifyContent: "flex-end" }}><label className="switch"><input type="checkbox" checked={key} onChange={(e) => setKey(e.target.checked)} /> Show correct answers (staff only)</label></div>
      <header className="paper-head">
        <h2>{exam.title || "Untitled exam"}</h2>
        <p>{subjectName} · {exam.duration_minutes} minutes · {Math.round(marks * 100) / 100} marks · {sel.length} questions</p>
        {exam.rules_text && <p className="paper-rules">{exam.rules_text}</p>}
        <div className="paper-toc">{secs.map((s) => <span key={s.qtype} className="pill">Section {s.letter}: {s.title} ({s.items.length})</span>)}</div>
      </header>
      {secs.map((s) => (
        <section key={s.qtype} className="paper-sec">
          <div className="paper-sec-h"><h3>Section {s.letter}</h3><span>{s.title}</span><em>{s.items.length} question{s.items.length === 1 ? "" : "s"} · {s.marks} marks</em></div>
          <p className="muted small paper-instr">{s.instruction}</p>
          {s.items.map((q) => <div key={q.id} className="card paper-q"><QPreview q={q} showKey={key} n={++n} /></div>)}
        </section>))}
    </div>
  );
}

/* ------------------------------------------------------------------ the builder */
export default function ExamBuilder({ exam, reload, editable, admin, subjectName }: { exam: any; reload: () => void; editable: boolean; admin: boolean; subjectName: string }) {
  const [sel, setSel] = useState<Q[]>([]), [saved, setSaved] = useState<number[]>([]), [ready, setReady] = useState(false), [loadErr, setLoadErr] = useState(""), [orphans, setOrphans] = useState(0);
  const [step, setStep] = useState<"select" | "preview">(editable ? "select" : "preview"), [tab, setTab] = useState<"bank" | "create" | "random" | "selected">("bank");
  const [note, setNote] = useState(""), [errs, setErrs] = useState<string[]>([]), [busy, setBusy] = useState(false), [createKey, setCreateKey] = useState(0);
  const root = useRef<HTMLDivElement>(null), [w, setW] = useState<"xs" | "narrow" | "wide">("narrow"), wide = w === "wide";
  useEffect(() => {  // lay out by the builder's own width (the sidebar takes space on desktop), not the screen's
    const el = root.current; if (!el) return;
    const measure = () => { const x = el.getBoundingClientRect().width; setW(x >= 860 ? "wide" : x < 520 ? "xs" : "narrow"); };
    measure();
    if (typeof ResizeObserver === "undefined") { window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); }
    const ro = new ResizeObserver(measure); ro.observe(el); return () => ro.disconnect();
  }, [ready]);
  useEffect(() => { if (wide && tab === "selected") setTab("bank"); }, [wide, tab]);
  const flash = (m: string) => { setNote(m); setTimeout(() => setNote(""), 4000); };

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const paper = await api<any[]>(`/exams/${exam.id}/questions/`);
        const ids: number[] = paper.map((p) => p.source).filter(Boolean);
        if (live) { setSaved(ids); setOrphans(paper.length - ids.length); }
        if (ids.length) {
          const qs = await api<Q[]>(`/questions/?ids=${ids.join(",")}`), by = new Map(qs.map((q) => [q.id, q]));
          if (live) setSel(ids.map((i) => by.get(i)).filter(Boolean) as Q[]);
        }
      } catch (e: any) { live && setLoadErr(e.message); }
      live && setReady(true);
    })();
    return () => { live = false; };
  }, [exam.id]);

  const selIds = useMemo(() => new Set(sel.map((q) => q.id)), [sel]);
  const dirty = ready && JSON.stringify(canonicalOrder(sel).map((q) => q.id)) !== JSON.stringify(saved);
  useEffect(() => { if (!dirty) return; const h = (e: BeforeUnloadEvent) => { e.preventDefault(); }; window.addEventListener("beforeunload", h); return () => window.removeEventListener("beforeunload", h); }, [dirty]);

  const add = (qs: Q[]) => setSel((s) => [...s, ...qs.filter((q) => !s.some((x) => x.id === q.id))]);
  const toggle = (q: Q) => setSel((s) => (s.some((x) => x.id === q.id) ? s.filter((x) => x.id !== q.id) : [...s, q]));
  const move = (id: number, d: -1 | 1) => setSel((s) => {
    const q = s.find((x) => x.id === id); if (!q) return s;
    const mates = s.filter((x) => x.qtype === q.qtype), j = mates.findIndex((x) => x.id === id) + d;
    if (j < 0 || j >= mates.length) return s;
    const other = mates[j], a = s.indexOf(q), b = s.indexOf(other), out = [...s]; out[a] = other; out[b] = q; return out;
  });

  async function savePaper(): Promise<boolean> {
    setErrs([]);
    try { const r = await api<any>(`/exams/${exam.id}/paper/`, { body: { question_ids: canonicalOrder(sel).map((q) => q.id), rules: [] } }); setSaved(canonicalOrder(sel).map((q) => q.id)); setOrphans(0); reload(); flash(`Paper saved: ${r.questions} questions, ${r.total_marks} marks.`); return true; }
    catch (e: any) { setErrs(errorLines(e.data, e.message)); return false; }
  }
  async function save(thenSchedule: boolean, thenSubmit = false) {
    setBusy(true);
    if (await savePaper()) {
      try {
        if (thenSchedule) { await api(`/exams/${exam.id}/schedule/`, { body: {} }); flash("Exam scheduled. Students can now see it."); reload(); }
        else if (thenSubmit) { await api(`/exams/${exam.id}/submit/`, { body: {} }); flash("Submitted. The administrators will see it at the top of their exam list."); reload(); }
      } catch (e: any) { setErrs(errorLines(e.data, e.message)); }
    }
    setBusy(false);
  }

  if (!ready) return <div className="card"><Loading /></div>;
  if (loadErr) return <div className="card error" role="alert"><p>⚠ {loadErr}</p></div>;
  const checks = [
    { ok: sel.length > 0, label: `${sel.length} question${sel.length === 1 ? "" : "s"} selected` },
    { ok: !!(exam.start_at && exam.end_at), label: "Date, start time and end time set" },
    { ok: (exam.classes?.length || 0) + (exam.students?.length || 0) > 0, label: "Classes or students chosen" },
  ];

  return (
    <div className="bld" ref={root} data-w={w}>
      <div className="bld-steps" role="tablist" aria-label="Exam paper steps">
        {editable && <button role="tab" aria-selected={step === "select"} className={`bld-step ${step === "select" ? "on" : ""}`} onClick={() => setStep("select")}><i>1</i> Select questions</button>}
        <button role="tab" aria-selected={step === "preview"} className={`bld-step ${step === "preview" ? "on" : ""}`} disabled={!sel.length} onClick={() => setStep("preview")}><i>{editable ? 2 : "•"}</i> Preview paper</button>
        <span className="grow" />{dirty && editable && <span className="pill warn">Unsaved changes</span>}
      </div>
      {orphans > 0 && editable && <p className="hint">{orphans} question(s) in the saved paper no longer exist in the question bank and will be dropped when you save.</p>}
      {note && <p className="ok" role="status">✓ {note}</p>}

      {step === "select" && editable && (
        <div className="bld-grid">
          <div>
            <div className="bld-tabs" role="tablist">
              {([["bank", "📚 Question bank"], ["create", "✏️ Create new"], ["random", "🎲 Random"], ["selected", `✓ Selected (${sel.length})`]] as const).filter(([k]) => !(wide && k === "selected")).map(([k, l]) =>
                <button key={k} role="tab" aria-selected={tab === k} className={`bld-tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}
            </div>
            {tab === "bank" && <Bank exam={exam} selIds={selIds} onToggle={toggle} onAddMany={(qs) => { add(qs); flash(`${qs.length} added.`); }} onCreate={() => setTab("create")} />}
            {tab === "create" && <QuestionEditor key={createKey} id={null} subject={exam.subject} backLabel="← Back to question bank" onClose={() => setTab("bank")}
              onCreated={(q) => { add([q]); setCreateKey((k) => k + 1); setTab("bank"); flash("Question created, approved and added to this exam."); }} />}
            {tab === "random" && <Random exam={exam} selIds={selIds} onAdded={(qs) => { add(qs); flash(`${qs.length} random question${qs.length === 1 ? "" : "s"} added.`); setTab("selected"); }} />}
            {tab === "selected" && <Selected narrow sel={sel} onRemove={(id) => setSel(sel.filter((q) => q.id !== id))} onMove={move} onClear={() => setSel([])} onPreview={() => setStep("preview")} />}
          </div>
          {wide && <Selected sel={sel} onRemove={(id) => setSel(sel.filter((q) => q.id !== id))} onMove={move} onClear={() => setSel([])} onPreview={() => setStep("preview")} />}
        </div>
      )}
      {step === "select" && editable && !wide && sel.length > 0 && tab !== "selected" && <div className="bld-bar"><span><b>{sel.length}</b> selected · <b>{Math.round(sel.reduce((a, q) => a + Number(q.marks), 0) * 100) / 100}</b> marks</span><button className="btn primary" onClick={() => setStep("preview")}>Preview →</button></div>}

      {step === "preview" && (
        <>
          <PaperPreview exam={exam} subjectName={subjectName} sel={sel} />
          <div className="card paper-actions">
            <h3>Ready to submit for scheduling?</h3>
            <ul className="checks">{checks.map((c) => <li key={c.label} className={c.ok ? "ok" : "todo"}>{c.ok ? "✓" : "○"} {c.label}</li>)}</ul>
            {!admin && <p className="muted small">{exam.submitted_at ? `Submitted on ${eatDate(exam.submitted_at, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}. ` : ""}An administrator sets the date and classes and schedules the exam. Submit the paper so it appears at the top of their list.</p>}
            {errs.length > 0 && <div className="card error" role="alert">{errs.map((e, i) => <p key={i}>⚠ {e}</p>)}</div>}
            {editable && (
              <div className="row">
                <button className="btn" onClick={() => setStep("select")}>← Back to selection</button>
                <span className="grow" />
                <button className="btn" disabled={busy || !sel.length || !dirty} onClick={() => save(false)}>{dirty ? "Save paper" : "Paper saved ✓"}</button>
                {admin && exam.status === "draft" && <button className="btn primary" disabled={busy || !sel.length} onClick={() => save(true)}>Save &amp; submit for scheduling</button>}
                {!admin && exam.status === "draft" && <button className="btn primary" disabled={busy || !sel.length} onClick={() => save(false, true)}>{exam.submitted_at && !dirty ? "Resubmit to admin" : "Save & submit to admin"}</button>}
              </div>)}
          </div>
        </>
      )}
    </div>
  );
}
