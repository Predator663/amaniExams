"use client";
import { useEffect, useState } from "react";
import { Pager, usePaged } from "@/components/Pager";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { Modal, ErrorNote, Loading, useLoad, Tabs } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import { errorLines } from "@/lib/staff";
import { useSession } from "@/lib/session";

function Errs({ errs, ok }: { errs: string[]; ok?: string }) {
  return <>{errs.length > 0 && <div className="card error" role="alert">{errs.map((e, i) => <p key={i}>⚠ {e}</p>)}</div>}{ok && <p className="ok" role="status">✓ {ok}</p>}</>;
}

/** ADM-03: create, edit and deactivate teacher accounts; assign subjects and classes. (Super Admin: same for Admin accounts, ADM section 2.) */
function Staff({ kind }: { kind: "teachers" | "admins" }) {
  const list = usePaged<any>(`/${kind}/`, {}, { size: 10 });
  const subjects = useLoad(() => api<any[]>("/subjects/")), classes = useLoad(() => api<any[]>("/classes/"));
  const [f, setF] = useState({ username: "", first_name: "", last_name: "", email: "", password: "" });
  const [errs, setErrs] = useState<string[]>([]), [ok, setOk] = useState(""), [open, setOpen] = useState<number | null>(null);
  const [as, setAs] = useState({ subject: "", school_class: "" });
  const run = async (fn: () => Promise<any>, msg: string, after?: () => void) => { setErrs([]); setOk(""); try { const r = await fn(); setOk(typeof msg === "function" ? (msg as any)(r) : msg); list.reload(); after?.(); } catch (e: any) { setErrs(errorLines(e.data, e.message)); } };
  const label = kind === "teachers" ? "teacher" : "admin";
  return (
    <>
      <div className="card"><h3>Add a {label}</h3>
        <div className="grid2">
          <label className="field"><span>Username</span><input className="input" value={f.username} autoCapitalize="none" onChange={(e) => setF({ ...f, username: e.target.value })} /></label>
          <label className="field"><span>Email (optional)</span><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
          <label className="field"><span>First name</span><input className="input" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></label>
          <label className="field"><span>Last name</span><input className="input" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></label>
        </div>
        <label className="field"><span>Starting password (strong; they must change it at first login)</span><input className="input" type="text" value={f.password} autoComplete="off" onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
        <Errs errs={errs} ok={ok} />
        <button className="btn primary" disabled={!f.username || !f.first_name || !f.password} onClick={() => run(() => api(`/${kind}/`, { body: f }), `${label} account created.`, () => setF({ username: "", first_name: "", last_name: "", email: "", password: "" }))}>Create account</button>
      </div>
      {list.loading ? <Loading /> : list.error ? <ErrorNote error={list.error} retry={list.reload} /> : <><div ref={list.top} className="paged" aria-busy={list.busy || undefined}>{list.rows.map((t) => (
        <div key={t.id} className={`card ${t.is_active ? "" : "unread"}`}>
          <div className="row"><span className="grow"><b>{t.first_name} {t.last_name}</b> <span className="muted small">@{t.username}</span>{!t.is_active && <span className="pill">inactive</span>}</span>
            {kind === "teachers" && <button className="btn" onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? "Close" : "Subjects & classes"}</button>}</div>
          {kind === "teachers" && <p className="muted small">{t.assignments.length ? t.assignments.map((a: any) => `${a.subject_name}${a.school_class ? ` (${classes.data?.find((c) => c.id === a.school_class)?.name})` : " (all classes)"}`).join(", ") : "No subjects assigned yet"}</p>}
          <div className="row">
            <button className="btn" onClick={() => run(() => api(`/${kind}/${t.id}/reset-password/`, { body: {} }), ((r: any) => `Temporary password (shown once): ${r.temporary_password}`) as any)}>Reset password</button>
            {t.is_active ? <button className="btn danger" onClick={() => confirm(`Deactivate ${t.username}? Their questions and exams stay.`) && run(() => api(`/${kind}/${t.id}/`, { method: "DELETE" }), "Deactivated.")}>Deactivate</button>
              : <button className="btn" onClick={() => run(() => api(`/${kind}/${t.id}/activate/`, { body: {} }), "Activated.")}>Activate</button>}
          </div>
          {kind === "teachers" && open === t.id && (
            <div className="hint" style={{ marginTop: ".6rem" }}>
              {t.assignments.map((a: any) => <div key={a.id} className="row"><span className="grow">{a.subject_name} · {a.school_class ? classes.data?.find((c) => c.id === a.school_class)?.name : "all classes"}</span><button className="btn danger" onClick={() => run(() => api(`/assignments/${a.id}/`, { method: "DELETE" }), "Removed.")}>Remove</button></div>)}
              <div className="grid2" style={{ marginTop: ".5rem" }}>
                <select className="input" aria-label="Subject" value={as.subject} onChange={(e) => setAs({ ...as, subject: e.target.value })}><option value="">Subject…</option>{subjects.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
                <select className="input" aria-label="Class" value={as.school_class} onChange={(e) => setAs({ ...as, school_class: e.target.value })}><option value="">All classes</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
              </div>
              <button className="btn primary" disabled={!as.subject} onClick={() => run(() => api("/assignments/", { body: { teacher: t.id, subject: Number(as.subject), school_class: as.school_class ? Number(as.school_class) : null } }), "Assigned.", () => setAs({ subject: "", school_class: "" }))}>Assign</button>
            </div>
          )}
        </div>
      ))}</div><Pager {...list.pager} /></>}
    </>
  );
}

/** ADM-01, ADM-02: view, search, filter; add, edit, move, deactivate, graduate, archive, restore; bulk actions. */
function Students() {
  const { user } = useSession();
  const superAdmin = user?.role === "super_admin";
  const classes = useLoad(() => api<any[]>("/classes/"));
  const [f, setF] = useState({ q: "", class: "", archived: "0", active: "" });
  const list = usePaged<any>("/students/", f, { size: 20 });
  const [sel, setSel] = useState<number[]>([]), [edit, setEdit] = useState<any>(null), [add, setAdd] = useState(false), [bulkClass, setBulkClass] = useState("");
  const [errs, setErrs] = useState<string[]>([]), [ok, setOk] = useState("");
  const run = async (fn: () => Promise<any>, msg: string, after?: () => void) => { setErrs([]); setOk(""); try { await fn(); setOk(msg); list.reload(); setSel([]); after?.(); } catch (e: any) { setErrs(errorLines(e.data, e.message)); } };
  const bulk = (action: string, extra: any = {}, msg = "Done.") => run(() => api("/students/bulk-action/", { body: { ids: sel, action, ...extra } }), msg);
  const rows = list.rows;
  const allOnPage = rows.length > 0 && rows.every((r) => sel.includes(r.id));
  const archived = f.archived === "1";
  return (
    <>
      <div className="card">
        <div className="grid2">
          <label className="field"><span>Search</span><input className="input" placeholder="Name, username or index number" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></label>
          <label className="field"><span>Class</span><select className="input" value={f.class} onChange={(e) => setF({ ...f, class: e.target.value })}><option value="">All</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label className="field"><span>Show</span><select className="input" value={f.archived + f.active} onChange={(e) => { const v = e.target.value; setF({ ...f, archived: v[0], active: v.slice(1) }); }}><option value="0">Current students</option><option value="01">Active only</option><option value="00">Deactivated or graduated</option><option value="1">Archived (deleted)</option></select></label>
          <div className="row" style={{ alignItems: "flex-end" }}><button className="btn primary" onClick={() => setAdd(true)}>+ Add a student</button>
            <button className="btn" onClick={() => downloadFile(`/students/credentials/?file=pdf${f.class ? `&class=${f.class}` : ""}`, "credentials.pdf").catch((e) => setErrs([e.message]))}>⬇ Username sheet</button>
            <button className="btn" onClick={() => downloadFile("/exports/students/", "students.xlsx").catch((e) => setErrs([e.message]))}>⬇ Excel</button></div>
        </div>
      </div>
      <Errs errs={errs} ok={ok} />
      {sel.length > 0 && !archived && (
        <div className="card hint" role="region" aria-label="Bulk actions"><b>{sel.length} selected</b>
          <div className="row" style={{ marginTop: ".4rem" }}>
            <select className="input" style={{ width: 160 }} aria-label="Move to class" value={bulkClass} onChange={(e) => setBulkClass(e.target.value)}><option value="">Class…</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
            <button className="btn" disabled={!bulkClass} onClick={() => bulk("change_class", { school_class: Number(bulkClass) }, "Class changed.")}>Change class</button>
            <button className="btn" onClick={() => confirm("Reset these passwords to the index numbers?") && bulk("reset_passwords", {}, "Passwords reset.")}>Reset passwords</button>
            <button className="btn" onClick={() => confirm("Deactivate the selected students?") && bulk("deactivate", {}, "Deactivated.")}>Deactivate</button>
            <button className="btn" onClick={() => confirm("Mark the selected students as graduated?") && bulk("graduate", {}, "Graduated.")}>Graduate</button></div></div>
      )}
      {list.loading ? <Loading /> : list.error ? <ErrorNote error={list.error} retry={list.reload} /> : (
        <div className="card"><p className="muted small">{list.count} student(s)</p>
          <div className="tbl-wrap paged" ref={list.top} aria-busy={list.busy || undefined}><table><thead><tr><th>{!archived && <input type="checkbox" aria-label="Select all" checked={allOnPage} onChange={(e) => setSel(e.target.checked ? [...new Set([...sel, ...rows.map((r) => r.id)])] : sel.filter((id) => !rows.some((r) => r.id === id)))} />}</th><th>Name</th><th>Username</th><th>Index no.</th><th>Class</th><th>Status</th><th /></tr></thead>
            <tbody>{rows.map((s) => <tr key={s.id}><td>{!archived && <input type="checkbox" aria-label={`Select ${s.first_name}`} checked={sel.includes(s.id)} onChange={(e) => setSel(e.target.checked ? [...sel, s.id] : sel.filter((x) => x !== s.id))} />}</td>
              <td>{s.first_name} {s.last_name}</td><td>{s.username}</td><td>{s.index_number}</td><td>{s.school_class_name || "—"}</td><td>{s.is_archived ? "archived" : s.graduated ? "graduated" : s.is_active ? "active" : "inactive"}</td><td><button className="btn" onClick={() => setEdit(s)}>Open</button></td></tr>)}</tbody></table></div>
          <Pager {...list.pager} /></div>
      )}
      {add && <StudentForm classes={classes.data || []} onClose={() => setAdd(false)} onSaved={(m) => { setAdd(false); setOk(m); list.reload(); }} />}
      {edit && (
        <Modal label="Student" onClose={() => setEdit(null)}>
          <StudentForm student={edit} classes={classes.data || []} onClose={() => setEdit(null)} onSaved={(m) => { setEdit(null); setOk(m); list.reload(); }} />
          <div className="row" style={{ marginTop: ".6rem" }}>
            {edit.is_archived ? <button className="btn primary" onClick={() => run(() => api(`/students/${edit.id}/restore/`, { body: {} }), "Restored.", () => setEdit(null))}>Restore</button> : <>
              <button className="btn" onClick={() => run(() => api(`/students/${edit.id}/reset-password/`, { body: {} }), "Password reset to the index number.", () => setEdit(null))}>Reset password</button>
              {edit.is_active ? <button className="btn" onClick={() => run(() => api(`/students/${edit.id}/deactivate/`, { body: {} }), "Deactivated.", () => setEdit(null))}>Deactivate</button> : <button className="btn" onClick={() => run(() => api(`/students/${edit.id}/activate/`, { body: {} }), "Activated.", () => setEdit(null))}>Activate</button>}
              <button className="btn" onClick={() => confirm("Mark as graduated?") && run(() => api(`/students/${edit.id}/graduate/`, { body: {} }), "Graduated.", () => setEdit(null))}>Graduate</button>
              <button className="btn danger" onClick={() => confirm("Archive (delete) this student? You can restore her later.") && run(() => api(`/students/${edit.id}/`, { method: "DELETE" }), "Archived. It can be restored.", () => setEdit(null))}>Archive</button></>}
            {superAdmin && <button className="btn danger" onClick={() => confirm("PERMANENTLY delete this student and her data? This cannot be undone.") && run(() => api(`/students/${edit.id}/?permanent=1`, { method: "DELETE" }), "Permanently deleted.", () => setEdit(null))}>Delete permanently</button>}
          </div>
        </Modal>
      )}
    </>
  );
}

function StudentForm({ student, classes, onClose, onSaved }: { student?: any; classes: any[]; onClose: () => void; onSaved: (m: string) => void }) {
  const [f, setF] = useState({ first_name: student?.first_name || "", last_name: student?.last_name || "", index_number: student?.index_number || "", school_class: student?.school_class ? String(student.school_class) : "" });
  const [errs, setErrs] = useState<string[]>([]), [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setErrs([]);
    const body = { ...f, school_class: f.school_class ? Number(f.school_class) : null };
    try {
      const r = student ? await api<any>(`/students/${student.id}/`, { method: "PATCH", body }) : await api<any>("/students/", { body });
      onSaved(student ? "Saved." : `Created. Username: ${r.username}. Starting password: the index number.`);
    } catch (e: any) { setErrs(errorLines(e.data, e.message)); setBusy(false); }
  }
  const body = (
    <>
      <h2>{student ? "Student details" : "Add a student"}</h2>
      <div className="grid2">
        <label className="field"><span>First name</span><input className="input" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></label>
        <label className="field"><span>Last name</span><input className="input" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></label>
        <label className="field"><span>Index number</span><input className="input" value={f.index_number} onChange={(e) => setF({ ...f, index_number: e.target.value })} /></label>
        <label className="field"><span>Class</span><select className="input" value={f.school_class} onChange={(e) => setF({ ...f, school_class: e.target.value })}><option value="">None</option>{classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      </div>
      {student && <p className="muted small">Username: {student.username} (cannot be changed)</p>}
      <Errs errs={errs} />
      <div className="row"><button className="btn primary" disabled={busy || !f.first_name || !f.index_number} onClick={save}>Save</button>{!student && <button className="btn" onClick={onClose}>Cancel</button>}</div>
    </>
  );
  return student ? body : <Modal label="Add a student" onClose={onClose}>{body}</Modal>;
}

export default function People() {
  const { user } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [tab, setTab] = useState("students");
  useEffect(() => { const t = new URLSearchParams(location.search).get("tab"); if (t) setTab(t); }, []);
  const tabs = [["students", "Students"], ["teachers", "Teachers"], ...(user?.role === "super_admin" ? [["admins", "Admins"]] : [])];
  return (
    <Shell bare title="People">
      <StaffNav />
      {!admin ? <p>Only administrators can manage people.</p> : (
        <>
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
          {tab === "students" && <Students />}{tab === "teachers" && <Staff kind="teachers" />}{tab === "admins" && <Staff kind="admins" />}
        </>
      )}
    </Shell>
  );
}
