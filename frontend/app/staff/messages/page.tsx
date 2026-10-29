"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import PersonPicker, { type Person } from "@/components/PersonPicker";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import { ErrorNote, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { sendMessage } from "@/lib/messages";
import { useSession } from "@/lib/session";

type Sent = { id: number; body: string; created_at: string; seen: boolean; seen_at: string | null; recipient: { id: number; name: string; role: string; index: string } };

/** Administrators: message one or more students or teachers, see who has closed the banner, and delete messages (which removes them
 *  from the person's Messages tab as well). */
export default function StaffMessages() {
  const { user } = useSession();
  const admin = user?.role === "admin" || user?.role === "super_admin";
  const [people, setPeople] = useState<Person[]>([]);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(""), [err, setErr] = useState("");
  const [sent, setSent] = useState<Sent[] | null>(null);
  const [q, setQ] = useState("");
  const load = useCallback(async () => {
    try { setSent((await api<{ results: Sent[] }>("/admin/messages/")).results); } catch (e: any) { setErr(e?.message || "Could not load."); }
  }, []);
  useEffect(() => { if (admin) load(); }, [admin, load]);
  const send = async () => {
    setBusy(true); setErr(""); setNote("");
    try { const n = await sendMessage(people.map((p) => p.id), body); setNote(`Sent to ${n} ${n === 1 ? "person" : "people"}.`); setBody(""); setPeople([]); load(); }
    catch (e: any) { setErr(e?.message || "Could not send."); }
    setBusy(false);
  };
  const del = async (m: Sent) => {
    if (!confirm(`Delete this message to ${m.recipient.name}? It disappears from their Messages tab too.`)) return;
    try { await api(`/admin/messages/${m.id}/`, { method: "DELETE" }); load(); } catch (e: any) { setErr(e?.message || "Could not delete."); }
  };
  const list = useMemo(() => (sent || []).filter((m) => !q.trim() || m.recipient.name.toLowerCase().includes(q.toLowerCase()) || m.body.toLowerCase().includes(q.toLowerCase())), [sent, q]);
  return (
    <Shell bare title="Messages">
      <StaffNav />
      {!admin ? <p>Only administrators can send messages.</p> : (
        <>
          <div className="card">
            <h2>Send a message</h2>
            <p className="muted small">It shows as a banner on top of the person’s screen (also during an exam) until they tap it away. After that it stays in their Messages tab until you delete it here.</p>
            <PersonPicker roles={["student", "teacher"]} value={people} onChange={setPeople} max={30} label="To (students or teachers)" />
            <label className="field"><span>Message ({body.length}/1000)</span>
              <textarea className="input" rows={4} maxLength={1000} value={body} onChange={(e) => setBody(e.target.value)} /></label>
            {err && <p className="lb-alert" role="alert">{err}</p>}
            {note && <p className="ok" role="status">{note}</p>}
            <button className="btn primary" disabled={busy || !people.length || !body.trim()} onClick={send}>{busy ? "Sending…" : `Send${people.length > 1 ? ` to ${people.length} people` : ""}`}</button>
          </div>
          <div className="card">
            <h2>Sent messages</h2>
            <label className="field"><span>Search</span><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or words in the message" /></label>
            {err && !sent ? <ErrorNote error={err} retry={load} /> : !sent ? <Loading /> : !list.length ? <p className="lb-empty">No messages.</p> : (
              <div className="tbl-wrap"><table><thead><tr><th>To</th><th>Message</th><th>Sent</th><th>Seen</th><th /></tr></thead><tbody>
                {list.map((m) => (
                  <tr key={m.id}><td><b>{m.recipient.name}</b><br /><small className="muted">{m.recipient.role}{m.recipient.index ? ` · #${m.recipient.index}` : ""}</small></td>
                    <td className="msg-cell">{m.body}</td><td>{new Date(m.created_at).toLocaleString()}</td>
                    <td>{m.seen ? `Closed ${new Date(m.seen_at!).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Not yet"}</td>
                    <td><button className="btn danger" onClick={() => del(m)}>Delete</button></td></tr>
                ))}
              </tbody></table></div>
            )}
          </div>
        </>
      )}
    </Shell>
  );
}
