"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type Person = { id: number; name: string; role: "student" | "teacher"; detail: string };

/** Search by name or index number and pick people; the choices appear as chips that can be removed. */
export default function PersonPicker({ roles, value, onChange, max, label }: { roles: ("student" | "teacher")[]; value: Person[]; onChange: (v: Person[]) => void; max: number; label: string }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Person[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const text = q.trim();
    if (text.length < 2) { setFound([]); return; }
    let live = true;
    const id = setTimeout(async () => {
      setBusy(true);
      try {
        const out: Person[] = [];
        for (const role of roles) {
          const r = await api<{ results: any[] }>(`/${role}s/?q=${encodeURIComponent(text)}&page=1&page_size=8`);
          for (const u of r.results || []) {
            out.push({ id: u.id, role, name: `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username,
              detail: role === "student" ? [u.school_class_name, u.index_number ? `#${u.index_number}` : ""].filter(Boolean).join(" · ") : "Teacher" });
          }
        }
        if (live) setFound(out);
      } catch { if (live) setFound([]); }
      if (live) setBusy(false);
    }, 250);
    return () => { live = false; clearTimeout(id); };
  }, [q, roles.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const chosen = new Set(value.map((p) => p.id));
  const add = (p: Person) => { if (value.length < max && !chosen.has(p.id)) onChange([...value, p]); setQ(""); setFound([]); };
  return (
    <div className="picker">
      <label className="field"><span>{label}</span>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={value.length >= max ? `Up to ${max} people` : "Type a name or index number"} disabled={value.length >= max} autoComplete="off" /></label>
      {(found.length > 0 || busy) && (
        <ul className="picker-list" role="listbox" aria-label="Matches">
          {busy && !found.length && <li className="muted small">Searching…</li>}
          {found.filter((p) => !chosen.has(p.id)).map((p) => (
            <li key={`${p.role}${p.id}`}><button type="button" className="picker-item" role="option" aria-selected="false" onClick={() => add(p)}><b>{p.name}</b><small>{p.detail}</small></button></li>
          ))}
        </ul>
      )}
      {value.length > 0 && (
        <p className="picker-chips">
          {value.map((p) => <span key={`${p.role}${p.id}`} className="chip">{p.name}<button type="button" aria-label={`Remove ${p.name}`} onClick={() => onChange(value.filter((x) => x.id !== p.id))}>✕</button></span>)}
        </p>
      )}
    </div>
  );
}
