"use client";
import { useState } from "react";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

const PAGE = 50;
/** ADM-10: who did what and when. Read-only: the log cannot be edited. */
export default function Audit() {
  const { user, lang } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [f, setF] = useState({ actor: "", action: "", from: "", to: "" }), [page, setPage] = useState(0);
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), limit: String(PAGE), offset: String(page * PAGE) }).toString();
  const log = useLoad(() => (admin ? api<any>(`/audit-log/?${qs}`) : Promise.resolve(null)), [qs, admin]);
  const set = (k: string, v: string) => { setF({ ...f, [k]: v }); setPage(0); };
  const pages = log.data ? Math.max(1, Math.ceil(log.data.count / PAGE)) : 1;
  return (
    <Shell bare title="Audit log">
      <StaffNav />
      {!admin ? <p>Only administrators can read the audit log.</p> : (
        <>
          <div className="card"><div className="grid2">
            <label className="field"><span>Who (username)</span><input className="input" value={f.actor} onChange={(e) => set("actor", e.target.value)} /></label>
            <label className="field"><span>Action starts with</span><input className="input" list="actions" placeholder="e.g. exam. or password." value={f.action} onChange={(e) => set("action", e.target.value)} /><datalist id="actions">{["exam.", "question.", "password.", "student.", "teacher.", "settings.", "login", "exam.grant"].map((a) => <option key={a} value={a} />)}</datalist></label>
            <label className="field"><span>From</span><input className="input" type="date" value={f.from} onChange={(e) => set("from", e.target.value)} /></label>
            <label className="field"><span>To</span><input className="input" type="date" value={f.to} onChange={(e) => set("to", e.target.value)} /></label>
          </div></div>
          {log.error ? <ErrorNote error={log.error} retry={log.reload} /> : log.loading || !log.data ? <Loading /> : (
            <div className="card"><p className="muted small">{log.data.count} entries · page {page + 1} of {pages}</p>
              <div className="tbl-wrap"><table><thead><tr><th>When (EAT)</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
                <tbody>{log.data.results.map((r: any, i: number) => <tr key={i}><td>{eatDate(r.at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" }, lang)}</td><td>{r.actor || "—"}</td><td>{r.action}</td><td>{r.target}</td>
                  <td className="small">{r.detail && Object.keys(r.detail).length ? Object.entries(r.detail).map(([k, v]) => `${k}: ${v}`).join(", ") : ""}</td></tr>)}</tbody></table></div>
              <div className="row"><button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>← Newer</button><button className="btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Older →</button></div>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
