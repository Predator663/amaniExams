"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import PersonPicker, { type Person } from "./PersonPicker";

type Rel = { id: number; kind: string; label: string; note: string; a: { id: number; name: string; index: string; class: string }; b: { id: number; name: string; index: string; class: string } };

/** Administrators: say who is expected to sit together (twins, the same house, the same room). Such students are shown on the map with
 *  a line and a label when they are close, and never raise an alert or get locked. */
export default function RelatedStudents({ onChange }: { onChange?: () => void }) {
  const [rels, setRels] = useState<Rel[] | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [kind, setKind] = useState("house");
  const [note, setNote] = useState("");
  const [q, setQ] = useState("");
  const [err, setErr] = useState(""), [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setRels((await api<{ results: Rel[] }>(`/proctoring/relations/${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`)).results); }
    catch (e: any) { setErr(e?.message || "Could not load."); }
  }, [q]);
  useEffect(() => { const id = setTimeout(load, 250); return () => clearTimeout(id); }, [load]);
  const add = async () => {
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api<{ results: Rel[] }>("/proctoring/relations/", { body: { students: people.map((p) => p.id), kind, note } });
      setMsg(`Saved ${r.results.length} ${r.results.length === 1 ? "pair" : "pairs"}.`); setPeople([]); setNote(""); load(); onChange?.();
    } catch (e: any) { setErr(e?.message || "Could not save."); }
    setBusy(false);
  };
  const remove = async (r: Rel) => {
    if (!confirm(`Remove the link between ${r.a.name} and ${r.b.name}? They will raise alerts again if they sit close.`)) return;
    try { await api(`/proctoring/relations/${r.id}/`, { method: "DELETE" }); load(); onChange?.(); } catch (e: any) { setErr(e?.message || "Could not remove."); }
  };
  return (
    <details className="card rel-panel">
      <summary><b>Related students</b> <small className="muted">twins, same house, same room: not alerted, not locked</small></summary>
      <p className="muted small">Choose 2 to 8 students who are expected to be together. Every pair among them is marked. When they are close, the map shows a line with the kind of relation above it.</p>
      <PersonPicker roles={["student"]} value={people} onChange={setPeople} max={8} label="Students" />
      <div className="grid2">
        <label className="field"><span>Kind</span>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}><option value="twin">Twins</option><option value="house">Same house</option><option value="room">Same room (indoors together)</option></select></label>
        <label className="field"><span>Note (optional)</span><input className="input" maxLength={120} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. share one phone, same compound" /></label>
      </div>
      {err && <p className="lb-alert" role="alert">{err}</p>}
      {msg && <p className="ok" role="status">{msg}</p>}
      <button className="btn primary" disabled={busy || people.length < 2} onClick={add}>{busy ? "Saving…" : "Mark as related"}</button>
      <h3>Marked pairs {rels ? <small>({rels.length})</small> : null}</h3>
      <label className="field"><span>Search</span><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or index number" /></label>
      {!rels ? <p className="lb-empty">Loading…</p> : !rels.length ? <p className="lb-empty">No related students marked yet.</p> : (
        <ul className="ac-alerts rel-list">
          {rels.map((r) => (
            <li key={r.id} className="off"><div><b>{r.a.name}</b> &amp; <b>{r.b.name}</b> <span className="ac-sev info">{r.label}</span></div>
              <small>{[r.a.class, r.b.class].filter(Boolean).join(" · ")}{r.note ? ` · ${r.note}` : ""}</small>
              <div className="ac-act"><button className="btn" onClick={() => remove(r)}>Remove</button></div></li>
          ))}
        </ul>
      )}
    </details>
  );
}
