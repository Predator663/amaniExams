"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pager, useClientPage, usePaged } from "@/components/Pager";
import Shell from "@/components/Shell";
import { ErrorNote, Loading, Modal, Tabs, useLoad } from "@/components/ui";
import { api, apiBase, downloadFile } from "@/lib/api";
import { useSession } from "@/lib/session";

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-GB", { timeZone: "Africa/Dar_es_Salaam", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
const ICON: Record<string, string> = { queued: "⏳", sending: "📤", sent: "✓", delivered: "✓✓", failed: "✗", cancelled: "⊘" };
const Status = ({ s }: { s: string }) => <span className={`pill st-${s}`}>{ICON[s]} {s}</span>;
const Msg = ({ err, ok }: { err?: string; ok?: string }) => <>{err && <p className="no" role="alert">⚠ {err}</p>}{ok && <p className="ok" role="status">✓ {ok}</p>}</>;

/* ------------------------------------------------------------------------------------------- Parents */
function Parents({ summary, classes, reload }: { summary: any; classes: any[]; reload: () => void }) {
  const [q, setQ] = useState(""), [cls, setCls] = useState("");
  const [edit, setEdit] = useState<any>(null), [add, setAdd] = useState(false), [shown, setShown] = useState<Record<number, string>>({});
  const list = usePaged<any>("/guardians/", { q, class: cls }, { size: 20 });
  const [msg, setMsg] = useState({ err: "", ok: "" });
  const done = (ok: string) => { setMsg({ err: "", ok }); list.reload(); reload(); };
  const fail = (e: any) => setMsg({ err: e.message, ok: "" });
  async function reveal(id: number) {
    try { const r = await api<any>(`/guardians/${id}/reveal/`); setShown((s) => ({ ...s, [id]: r.phone })); setTimeout(() => setShown((s) => { const n = { ...s }; delete n[id]; return n; }), 15000); } catch (e) { fail(e); }
  }
  const d = list.data;
  return (
    <>
      <div className="grid3">
        <div className="stat"><b>{summary.parents}</b><span>Parents saved</span></div>
        <div className="stat"><b>{summary.students_with_parent}/{summary.students}</b><span>Students with a parent</span></div>
        <div className="stat"><b>{summary.students_waiting_first_login}</b><span>Waiting for first login</span></div>
      </div>
      <div className="card">
        <div className="row" style={{ flexWrap: "wrap", gap: ".6rem" }}>
          <input className="input grow" type="search" placeholder="Search parent, child or phone" aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input" aria-label="Class" value={cls} onChange={(e) => setCls(e.target.value)}><option value="">All classes</option>{classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <button className="btn primary" onClick={() => setAdd(true)}>+ Add a parent</button>
        </div>
        <Msg {...msg} />
      </div>
      {list.loading ? <Loading /> : list.error ? <ErrorNote error={list.error} retry={list.reload} /> : !list.rows.length ? (
        <div className="card"><p className="muted">{d.total || q || cls ? "No parents match." : "No parents yet. Use the Upload tab to add your list, or add one by hand."}</p></div>
      ) : (
        <>
          <div className="tbl-wrap paged" ref={list.top} aria-busy={list.busy || undefined}><table>
            <thead><tr><th>Parent</th><th>Phone</th><th>Children</th><th>Last message</th><th></th></tr></thead>
            <tbody>{list.rows.map((g: any) => (
              <tr key={g.id}>
                <td><b>{g.name}</b><br /><span className="muted small">{g.relationship || "—"}{g.has_whatsapp ? " · WhatsApp" : ""} · {g.language === "en" ? "English" : "Kiswahili"}</span></td>
                <td><span className="mono">{shown[g.id] || g.phone}</span> {!shown[g.id] && <button className="btn ghost" onClick={() => reveal(g.id)} aria-label={`Show phone of ${g.name}`}>Show</button>}</td>
                <td>{g.children.map((c: any) => <span key={c.id} className="pill" title={c.class}>{c.name}{c.logged_in ? " ✓" : ""}</span>)} </td>
                <td>{g.last_message ? <><Status s={g.last_message.status} /><br /><span className="muted small">{when(g.last_message.at)}</span></> : <span className="muted">none</span>}</td>
                <td><button className="btn" onClick={() => setEdit(g)}>Edit</button></td>
              </tr>))}</tbody>
          </table></div>
          <p className="muted small">✓ = the child has already logged in.</p>
          <Pager {...list.pager} />
        </>
      )}
      {summary.without_parent?.length > 0 && (
        <details className="card"><summary><b>{summary.students - summary.students_with_parent} students have no parent yet</b></summary>
          <p className="muted small">First 40 shown. Add them in the Upload tab or with “Add a parent”.</p>
          <p>{summary.without_parent.map((s: any) => <span key={s.id} className="pill">{s.name} · {s.index} · {s.class}</span>)}</p></details>
      )}
      {add && <AddParent onClose={() => setAdd(false)} onDone={() => { setAdd(false); done("Parent saved."); }} />}
      {edit && <EditParent g={edit} onClose={() => setEdit(null)} onDone={(m: string) => { setEdit(null); done(m); }} />}
    </>
  );
}

function AddParent({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: "", phone: "", relationship: "", student_index: "", has_whatsapp: false, language: "sw" }), [err, setErr] = useState("");
  const set = (k: string, v: any) => setF({ ...f, [k]: v });
  return (
    <Modal label="Add a parent" onClose={onClose}>
      <h2>Add a parent</h2>
      <label className="field"><span>Parent name</span><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></label>
      <label className="field"><span>Mobile number</span><input className="input" inputMode="tel" placeholder="0712 345 678" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></label>
      <label className="field"><span>Relationship (optional)</span><input className="input" placeholder="mother, father, guardian" value={f.relationship} onChange={(e) => set("relationship", e.target.value)} /></label>
      <label className="field"><span>Child’s index number (several: separate with ;)</span><input className="input" value={f.student_index} onChange={(e) => set("student_index", e.target.value)} /></label>
      <label className="field"><span>Message language</span><select className="input" value={f.language} onChange={(e) => set("language", e.target.value)}><option value="sw">Kiswahili</option><option value="en">English</option></select></label>
      <label className="row"><input type="checkbox" checked={f.has_whatsapp} onChange={(e) => set("has_whatsapp", e.target.checked)} /> Uses WhatsApp</label>
      <Msg err={err} />
      <div className="row"><button className="btn primary grow" onClick={async () => { try { await api("/guardians/", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } }}>Save</button><button className="btn" onClick={onClose}>Cancel</button></div>
    </Modal>
  );
}

function EditParent({ g, onClose, onDone }: { g: any; onClose: () => void; onDone: (m: string) => void }) {
  const [f, setF] = useState({ name: g.name, phone: "", relationship: g.relationship, has_whatsapp: g.has_whatsapp, language: g.language }), [err, setErr] = useState(""), [idx, setIdx] = useState("");
  const set = (k: string, v: any) => setF({ ...f, [k]: v });
  const run = async (fn: () => Promise<any>, ok: string) => { try { await fn(); onDone(ok); } catch (e: any) { setErr(e.message); } };
  return (
    <Modal label="Edit parent" onClose={onClose}>
      <h2>Edit parent</h2>
      <label className="field"><span>Name</span><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></label>
      <label className="field"><span>New mobile number (leave empty to keep {g.phone})</span><input className="input" inputMode="tel" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></label>
      <label className="field"><span>Relationship</span><input className="input" value={f.relationship} onChange={(e) => set("relationship", e.target.value)} /></label>
      <label className="field"><span>Message language</span><select className="input" value={f.language} onChange={(e) => set("language", e.target.value)}><option value="sw">Kiswahili</option><option value="en">English</option></select></label>
      <label className="row"><input type="checkbox" checked={f.has_whatsapp} onChange={(e) => set("has_whatsapp", e.target.checked)} /> Uses WhatsApp</label>
      <h3>Children</h3>
      <p>{g.children.map((c: any) => <span key={c.id} className="pill">{c.name} ({c.index}) <button className="btn ghost" aria-label={`Remove ${c.name}`} onClick={() => run(() => api(`/guardians/${g.id}/links/?student=${c.id}`, { method: "DELETE" }), "Child removed.")}>✕</button></span>)}</p>
      <div className="row"><input className="input grow" placeholder="Add a child by index number" value={idx} onChange={(e) => setIdx(e.target.value)} />
        <button className="btn" disabled={!idx.trim()} onClick={() => run(() => api(`/guardians/${g.id}/links/`, { body: { student_index: idx } }), "Child added.")}>Add</button></div>
      <Msg err={err} />
      <div className="row"><button className="btn primary grow" onClick={() => run(() => api(`/guardians/${g.id}/`, { method: "PATCH", body: { ...f, phone: f.phone || undefined } }), "Saved.")}>Save</button>
        <button className="btn danger" onClick={() => confirm(`Delete ${g.name}? Messages already sent are not affected.`) && run(() => api(`/guardians/${g.id}/`, { method: "DELETE" }), "Parent deleted.")}>Delete</button></div>
    </Modal>
  );
}

/* ------------------------------------------------------------------------------------------- Upload */
function Upload({ reload, goParents }: { reload: () => void; goParents: () => void }) {
  const [file, setFile] = useState<File | null>(null), [rep, setRep] = useState<any>(null), [msg, setMsg] = useState({ err: "", ok: "" }), [skip, setSkip] = useState(false), [busy, setBusy] = useState(false);
  const post = (confirm: boolean) => { const fd = new FormData(); fd.append("file", file!); fd.append("confirm", String(confirm)); fd.append("skip_invalid", String(skip)); return api<any>("/guardians/upload/", { body: fd }); };
  async function check() { setBusy(true); setMsg({ err: "", ok: "" }); try { setRep(await post(false)); } catch (e: any) { setRep(null); setMsg({ err: e.message, ok: "" }); } setBusy(false); }
  async function save() {
    setBusy(true);
    try { const r = await post(true); setMsg({ err: "", ok: `Saved: ${r.parents_created} new parents, ${r.links_created} children linked${r.skipped ? `, ${r.skipped} rows skipped` : ""}.` }); setRep(null); setFile(null); reload(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); }
    setBusy(false);
  }
  return (
    <>
      <div className="card">
        <h3>1. Prepare your list</h3>
        <p className="muted">One row per parent. Columns: <b>parent_name, phone, relationship, student_index, whatsapp, language</b>. For two daughters write both index numbers in one cell, separated by <b>;</b>. Phone numbers like 0712 345 678 or +255712345678 both work. The file is checked first: nothing is saved until you confirm.</p>
        <button className="btn" onClick={() => downloadFile("/guardians/template/", "parents_template.csv").catch((e) => setMsg({ err: e.message, ok: "" }))}>⬇ Download the template (CSV)</button>
      </div>
      <div className="card">
        <h3>2. Check the file</h3>
        <input className="input" type="file" accept=".csv,.xlsx,.txt" aria-label="Parents file" onChange={(e) => { setFile(e.target.files?.[0] || null); setRep(null); setMsg({ err: "", ok: "" }); }} />
        <div className="row" style={{ marginTop: ".6rem" }}><button className="btn primary" disabled={!file || busy} onClick={check}>Check the file</button></div>
        <Msg {...msg} />
        {msg.ok && <button className="btn" onClick={goParents}>See the parents →</button>}
      </div>
      {rep && (
        <div className="card">
          <h3>3. Confirm</h3>
          <div className="grid3">
            <div className="stat"><b>{rep.valid_rows}</b><span>Rows OK</span></div><div className="stat"><b className={rep.invalid_rows ? "no" : ""}>{rep.invalid_rows}</b><span>Rows with problems</span></div>
            <div className="stat"><b>{rep.parents_new}</b><span>New parents</span></div>
          </div>
          <div className="tbl-wrap"><table><thead><tr><th>Row</th><th>Parent</th><th>Phone</th><th>Children</th><th>Result</th></tr></thead><tbody>
            {rep.rows.map((r: any) => (<tr key={r.row}><td>{r.row}</td><td>{r.name || "—"}</td><td className="mono">{r.phone}</td><td>{r.students.join(", ") || "—"}</td>
              <td>{r.status === "ok" ? <span className="ok">✓ OK</span> : <span className={r.status === "error" ? "no" : "warn"}>{r.status === "error" ? "✗ " : "⚠ "}{r.problems.join(" ")}</span>}</td></tr>))}
          </tbody></table></div>
          {rep.invalid_rows > 0 && <label className="row"><input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} /> Skip the rows with problems and save the rest</label>}
          <button className="btn primary big" disabled={busy || rep.valid_rows === 0 || (rep.invalid_rows > 0 && !skip)} onClick={save}>Save {rep.valid_rows} rows</button>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------------------------------- Send */
function Send({ summary, classes, reload }: { summary: any; classes: any[]; reload: () => void }) {
  const [scope, setScope] = useState("all"), [cls, setCls] = useState(""), [resend, setResend] = useState(false), [note, setNote] = useState(""), [plan, setPlan] = useState<any>(null), [msg, setMsg] = useState({ err: "", ok: "" });
  const [filter, setFilter] = useState("");
  const jobs = usePaged<any>("/guardians/jobs/", { status: filter }, { size: 20 });
  const body = { scope, class_id: scope === "class" ? Number(cls) : undefined, resend, note: note.trim() };
  const open = (summary.jobs.queued || 0) + (summary.jobs.sending || 0);
  useEffect(() => { if (!open) return; const i = setInterval(() => { jobs.reload(); reload(); }, 5000); return () => clearInterval(i); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  async function check() { setMsg({ err: "", ok: "" }); try { setPlan(await api("/guardians/send/", { body })); } catch (e: any) { setPlan(null); setMsg({ err: e.message, ok: "" }); } }
  async function queue() {
    try { const r = await api<any>("/guardians/send/", { body: { ...body, dry_run: false } }); setPlan(null); setNote(""); setMsg({ err: "", ok: `${r.queued} messages are waiting for the phone to send them.` }); jobs.reload(); reload(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); }
  }
  const act = async (fn: () => Promise<any>, ok: (r: any) => string) => { try { const r = await fn(); setMsg({ err: "", ok: ok(r) }); jobs.reload(); reload(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } };
  const sk = plan?.skipped || {};
  return (
    <>
      <div className="card">
        <h3>Send login details to parents</h3>
        <p className="muted">One text message per parent, sent by your school phone. <b>Every child gets a new random password</b> (not her index number) and must choose her own at the first login. Children who have already logged in, or who were already sent a message, are skipped.</p>
        {!summary.phone_online && <p className="warn" role="status">⚠ No school phone is online. Messages will wait until the phone app is open (see the Phone tab).</p>}
        <div className="grid2">
          <label className="field"><span>Send to</span><select className="input" value={scope} onChange={(e) => { setScope(e.target.value); setPlan(null); }}><option value="all">All parents</option><option value="class">Parents of one class</option></select></label>
          {scope === "class" && <label className="field"><span>Class</span><select className="input" value={cls} onChange={(e) => { setCls(e.target.value); setPlan(null); }}><option value="">Choose…</option>{classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
        </div>
        <label className="row"><input type="checkbox" checked={resend} onChange={(e) => { setResend(e.target.checked); setPlan(null); }} /> Also send again to children who already have a message or have logged in (this gives them a NEW password)</label>
        <label className="field" style={{ marginTop: ".6rem" }}>
          <span>Extra message (optional)</span>
          <textarea className="input" rows={2} maxLength={160} value={note} placeholder="For example: Parents' meeting on Friday 7 November, 9:00 am, at school." onChange={(e) => { setNote(e.target.value); setPlan(null); }} />
          <small className="muted">{note.length}/160. Added as the last line of every message, after the login details. Leave it empty to send only the login details. A longer text may use more than one SMS.</small>
        </label>
        <div className="row" style={{ marginTop: ".6rem" }}><button className="btn" disabled={scope === "class" && !cls} onClick={check}>Check who will get a message</button></div>
        <Msg {...msg} />
        {plan && (
          <div className="hint">
            <p><b>{plan.messages}</b> messages for <b>{plan.students}</b> children.</p>
            <p className="small muted">Skipped: {sk.already_logged_in || 0} already logged in · {sk.already_sent || 0} already sent · {sk.no_children || 0} parents with no child · {sk.inactive || 0} inactive.</p>
            {plan.preview?.text && (
              <>
                <p className="small muted" style={{ marginBottom: ".2rem" }}>Example of one message (the password is hidden here){plan.preview.parts > 1 ? ` — uses ${plan.preview.parts} SMS` : ""}:</p>
                <pre className="sms-preview" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: ".2rem 0 .6rem", padding: ".6rem .8rem", border: "1px solid var(--line,#c9d1de)", borderRadius: 10 }}>{plan.preview.text}</pre>
                {plan.preview.unicode && <p className="warn" role="status">⚠ The extra message has a character (such as an emoji) that makes each SMS shorter and costs more. Use plain letters to keep it cheap.</p>}
              </>
            )}
            <button className="btn primary big" disabled={!plan.messages} onClick={() => confirm(`Queue ${plan.messages} messages? ${plan.students} children get new passwords.`) && queue()}>Queue {plan.messages} messages</button>
          </div>
        )}
      </div>

      <div className="card">
        <div className="row" style={{ flexWrap: "wrap" }}>
          <h3 className="grow" style={{ margin: 0 }}>Messages</h3>
          <select className="input" aria-label="Filter" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">All</option>{["queued", "sending", "sent", "delivered", "failed", "cancelled"].map((s) => <option key={s}>{s}</option>)}</select>
          <button className="btn" onClick={() => act(() => api("/guardians/jobs/retry/", { body: {} }), (r) => `${r.requeued} failed messages will be tried again.`)}>Retry all failed</button>
          <button className="btn danger" onClick={() => confirm("Stop all messages that are still waiting? Those children will need a new message (tick “send again”).") && act(() => api("/guardians/jobs/cancel-queued/", { body: {} }), (r) => `${r.cancelled} messages cancelled.`)}>Cancel waiting</button>
        </div>
        <div className="grid3" style={{ marginTop: ".6rem" }}>
          {(["queued", "sent", "failed"] as const).map((k) => <div key={k} className="stat"><b>{k === "sent" ? (summary.jobs.sent || 0) + (summary.jobs.delivered || 0) : (summary.jobs[k] || 0) + (k === "queued" ? summary.jobs.sending || 0 : 0)}</b><span>{k === "queued" ? "Waiting" : k === "sent" ? "Sent" : "Failed"}</span></div>)}
        </div>
      </div>
      {jobs.loading ? <Loading /> : jobs.error ? <ErrorNote error={jobs.error} retry={jobs.reload} /> : !jobs.rows.length ? <p className="muted">No messages yet.</p> : (
        <><div className="tbl-wrap paged" ref={jobs.top} aria-busy={jobs.busy || undefined}><table><thead><tr><th>Parent</th><th>Children</th><th>Status</th><th>Time</th><th></th></tr></thead><tbody>
          {jobs.rows.map((j) => (<tr key={j.id}><td><b>{j.parent}</b><br /><span className="mono small">{j.phone}</span></td><td className="small">{j.summary.replace("Login details for ", "")}</td>
            <td><Status s={j.status} />{j.error && <div className="no small">{j.error}</div>}{j.attempts > 1 && <div className="muted small">tries: {j.attempts}</div>}</td><td className="small">{when(j.sent_at || j.created_at)}</td>
            <td>{(j.status === "failed" || j.status === "cancelled") && <button className="btn" onClick={() => act(() => api(`/guardians/jobs/${j.id}/retry/`, { body: {} }), () => "Queued again.")}>{j.status === "failed" ? "Retry" : "Send again"}</button>}</td></tr>))}
        </tbody></table></div>
        <Pager {...jobs.pager} /></>
      )}
    </>
  );
}

/* ------------------------------------------------------------------------------------------- Phone */
function Phone({ reload }: { reload: () => void }) {
  const devices = usePaged<any>("/guardians/devices/", {}, { size: 10 });
  const cfg = useLoad(() => api<any>("/guardians/config/"));
  const [name, setName] = useState("School phone"), [made, setMade] = useState<any>(null), [msg, setMsg] = useState({ err: "", ok: "" }), [f, setF] = useState<any>(null);
  useEffect(() => { if (cfg.data) setF(cfg.data); }, [cfg.data]);
  useEffect(() => { const i = setInterval(() => devices.reload(), 15000); return () => clearInterval(i); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const copy = (t: string) => navigator.clipboard?.writeText(t).then(() => setMsg({ err: "", ok: "Copied." })).catch(() => {});
  return (
    <>
      <div className="card">
        <h3>1. Message settings</h3>
        <p className="muted">The web address goes into every message, so keep it short, for example <b>amani-exams.co.tz</b>.</p>
        {f && (
          <>
            <label className="field"><span>School web address (shown in the text)</span><input className="input" autoCapitalize="none" placeholder="amani-exams.co.tz" value={f.public_url} onChange={(e) => setF({ ...f, public_url: e.target.value })} /></label>
            <div className="grid3">
              <label className="field"><span>Seconds between messages</span><input className="input" type="number" min={3} max={120} value={f.seconds_between} onChange={(e) => setF({ ...f, seconds_between: e.target.value })} /></label>
              <label className="field"><span>Rest after this many</span><input className="input" type="number" min={5} max={100} value={f.pause_every} onChange={(e) => setF({ ...f, pause_every: e.target.value })} /></label>
              <label className="field"><span>Rest for (seconds)</span><input className="input" type="number" min={30} max={1800} value={f.pause_seconds} onChange={(e) => setF({ ...f, pause_seconds: e.target.value })} /></label>
            </div>
            <p className="muted small">Slow and steady is safest: networks can block a SIM that sends hundreds of texts at once. About 8 seconds apart with a 3-minute rest every 30 messages is a good start.</p>
            <button className="btn primary" onClick={async () => { try { await api("/guardians/config/", { method: "PATCH", body: f }); setMsg({ err: "", ok: "Saved." }); cfg.reload(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } }}>Save settings</button>
          </>
        )}
        <Msg {...msg} />
      </div>
      <div className="card">
        <h3>2. Pair the school phone</h3>
        <p className="muted">Install the <b>Amani SMS Sender</b> app on the Android phone that holds the SIM card, then create a pairing code here and type it into the app. A code can be used on one phone, and is shown only once.</p>
        <div className="row"><input className="input grow" aria-label="Phone name" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn primary" onClick={async () => { try { setMade(await api("/guardians/devices/", { body: { name } })); devices.reload(); reload(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } }}>Create pairing code</button></div>
      </div>
      {devices.loading ? <Loading /> : devices.error ? <ErrorNote error={devices.error} retry={devices.reload} /> : (
        <><div className="tbl-wrap"><table><thead><tr><th>Phone</th><th>Status</th><th>Last seen</th><th>Messages sent</th><th></th></tr></thead><tbody>
          {!devices.rows.length && <tr><td colSpan={5} className="muted">No phone paired yet.</td></tr>}
          {devices.rows.map((d) => (<tr key={d.id}><td><b>{d.name}</b></td><td>{d.online ? <span className="pill st-delivered">● online</span> : <span className="pill st-failed">○ offline</span>}</td><td className="small">{d.last_seen ? when(d.last_seen) : "never"}</td><td>{d.sent}</td>
            <td><button className="btn danger" onClick={() => confirm(`Remove ${d.name}? It will stop sending.`) && api(`/guardians/devices/${d.id}/`, { method: "DELETE" }).then(() => { devices.reload(); reload(); })}>Remove</button></td></tr>))}
        </tbody></table></div>
        <Pager {...devices.pager} onSize={undefined} /></>
      )}
      {made && (
        <Modal label="Pairing code" onClose={() => setMade(null)}>
          <h2>Pairing code</h2>
          <p className="warn">Copy it now. It is shown only once. Anyone who has it can send messages as the school, so do not share it.</p>
          <label className="field"><span>Server address</span><input className="input mono" readOnly value={apiBase()} onFocus={(e) => e.target.select()} /></label>
          <label className="field"><span>Pairing code</span><input className="input mono" readOnly value={made.token} onFocus={(e) => e.target.select()} /></label>
          <div className="row"><button className="btn" onClick={() => copy(made.token)}>Copy code</button><button className="btn primary grow" onClick={() => setMade(null)}>I have copied it</button></div>
          {apiBase().includes("localhost") && <p className="muted small">This address only works on this computer. For a real phone use the computer’s network address or your real website address.</p>}
        </Modal>
      )}
    </>
  );
}

export default function GuardiansPage() {
  const { user } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [tab, setTab] = useState("parents");
  const summary = useLoad(() => api<any>("/guardians/summary/"));
  const classes = useLoad(() => api<any[]>("/classes/"));
  const reload = useCallback(() => summary.reload(), []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Shell bare title="Parents">
      {!admin ? <p>Only administrators can manage parents.</p> : (summary.loading && !summary.data) || (classes.loading && !classes.data) ? <Loading /> : summary.error && !summary.data ? <ErrorNote error={summary.error} retry={summary.reload} /> : (
        <>
          <Tabs tabs={[["parents", "Parents"], ["upload", "Upload"], ["send", "Send"], ["phone", "Phone"]]} value={tab} onChange={setTab} />
          {tab === "parents" && <Parents summary={summary.data!} classes={classes.data || []} reload={reload} />}
          {tab === "upload" && <Upload reload={reload} goParents={() => setTab("parents")} />}
          {tab === "send" && <Send summary={summary.data!} classes={classes.data || []} reload={reload} />}
          {tab === "phone" && <Phone reload={reload} />}
        </>
      )}
    </Shell>
  );
}
