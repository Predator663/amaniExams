"use client";
import { useEffect, useState } from "react";
import QuestionEditor from "@/components/QuestionEditor";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { plain, qtypeName } from "@/lib/staff";
import { useSession } from "@/lib/session";

/** QB-09, QB-10: searchable question bank filtered by subject, topic, difficulty, type and status; Draft -> Submitted -> Approved. */
export default function Questions() {
  const { user } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [edit, setEdit] = useState<number | "new" | null>(null);
  const [f, setF] = useState({ subject: "", topic: "", difficulty: "", qtype: "", status: "", q: "" });
  const subjects = useLoad(() => api<any[]>("/subjects/"));
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const list = useLoad(() => api<any[]>(`/questions/?${qs}`), [qs]);
  const [msg, setMsg] = useState("");
  useEffect(() => { const e = new URLSearchParams(location.search).get("edit"); if (e) setEdit(e === "new" ? "new" : Number(e)); }, []);
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));
  async function act(id: number, what: "submit" | "approve" | "reject") {
    setMsg(""); try { await api(`/questions/${id}/${what}/`, { body: {} }); list.reload(); } catch (e: any) { setMsg(e.message); }
  }
  async function del(id: number) {
    if (!confirm("Delete this question? A question already used in an exam is archived instead.")) return;
    try { await api(`/questions/${id}/`, { method: "DELETE" }); list.reload(); } catch (e: any) { setMsg(e.message); }
  }
  return (
    <Shell bare title="Question bank">
      <StaffNav />
      {edit !== null ? <QuestionEditor id={edit === "new" ? null : edit} onClose={() => { setEdit(null); list.reload(); }} /> : (
        <>
          <button className="btn primary" onClick={() => setEdit("new")}>+ New question</button>
          <div className="card" style={{ marginTop: ".8rem" }}>
            <div className="grid2">
              <label className="field"><span>Subject</span><select className="input" value={f.subject} onChange={(e) => set("subject", e.target.value)}><option value="">All</option>{subjects.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
              <label className="field"><span>Topic</span><input className="input" value={f.topic} onChange={(e) => set("topic", e.target.value)} /></label>
              <label className="field"><span>Difficulty</span><select className="input" value={f.difficulty} onChange={(e) => set("difficulty", e.target.value)}><option value="">All</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
              <label className="field"><span>Type</span><select className="input" value={f.qtype} onChange={(e) => set("qtype", e.target.value)}><option value="">All</option>{["mcq_single", "mcq_multi", "true_false", "matching", "fill_blank", "ordering"].map((k) => <option key={k} value={k}>{qtypeName(k)}</option>)}</select></label>
              <label className="field"><span>Status</span><select className="input" value={f.status} onChange={(e) => set("status", e.target.value)}><option value="">All</option>{["draft", "submitted", "approved", "archived"].map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
              <label className="field"><span>Search text</span><input className="input" value={f.q} onChange={(e) => set("q", e.target.value)} /></label>
            </div>
          </div>
          {msg && <p className="no" role="alert">⚠ {msg}</p>}
          {list.loading ? <Loading /> : list.error ? <ErrorNote error={list.error} retry={list.reload} /> : !list.data?.length ? <div className="card"><p className="muted">No questions match.</p></div> : (
            <>
              <p className="muted small">{list.data.length} question(s)</p>
              {list.data.map((q) => (
                <div key={q.id} className="card">
                  <p className="small muted">#{q.id} · {subjects.data?.find((s) => s.id === q.subject)?.name} · Form {q.form_level} · {q.topic || "—"} · {q.difficulty} · {qtypeName(q.qtype)} · {q.marks} mark(s)</p>
                  <p>{plain(q.prompt).slice(0, 160) || "(image only)"}</p>
                  <div className="row"><span className="pill">{q.status}</span>{q.used_in_exam && <span className="pill">used in an exam</span>}{q.practice_eligible && <span className="pill">practice</span>}</div>
                  <div className="row" style={{ marginTop: ".5rem" }}>
                    <button className="btn" onClick={() => setEdit(q.id)}>Edit</button>
                    {q.status === "draft" && <button className="btn" onClick={() => act(q.id, "submit")}>Submit</button>}
                    {admin && q.status === "submitted" && <><button className="btn primary" onClick={() => act(q.id, "approve")}>Approve</button><button className="btn" onClick={() => act(q.id, "reject")}>Send back</button></>}
                    {q.status !== "archived" && <button className="btn danger" onClick={() => del(q.id)}>Delete</button>}
                  </div>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </Shell>
  );
}
