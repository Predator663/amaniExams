"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { ErrorNote, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { Msg } from "@/lib/messages";
import { useSession } from "@/lib/session";

/** Messages the school sent to this account. They stay here until an administrator deletes them; the person cannot delete them. */
export default function Messages() {
  const { t } = useSession();
  const [items, setItems] = useState<Msg[] | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { setItems((await api<{ items: Msg[] }>("/messages/")).items); setErr(""); }
    catch (e: any) { setErr(e?.message || "Could not load."); }
  }, []);
  useEffect(() => { load(); const i = setInterval(load, 30_000); return () => clearInterval(i); }, [load]);
  const read = async (id: number) => {
    try { await api(`/messages/${id}/dismiss/`, { body: {} }); window.dispatchEvent(new Event("amani:messages")); load(); } catch { /* try again later */ }
  };
  return (
    <Shell title={t("messages")}>
      <p className="muted small">{t("msg_note")}</p>
      {err && !items ? <ErrorNote error={err} retry={load} /> : !items ? <Loading /> : !items.length ? <p className="lb-empty">{t("msg_empty")}</p> : (
        <ul className="msg-list">
          {items.map((m) => (
            <li key={m.id} className={`card msg-item ${m.dismissed ? "" : "new"}`}>
              <div className="msg-meta"><small>{new Date(m.created_at).toLocaleString()}</small>{!m.dismissed && <span className="pill">{t("msg_new")}</span>}</div>
              <p className="msg-body">{m.body}</p>
              {!m.dismissed && <button type="button" className="btn" onClick={() => read(m.id)}>{t("msg_mark")}</button>}
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}
