"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export type Msg = { id: number; body: string; created_at: string; dismissed: boolean };

/**
 * Messages an administrator sent to this account. `items` are the ones still to be shown as a banner (newest first); closing one
 * keeps it in the Messages tab. Checked every 20 s, when the tab comes back, and straight away when the exam screen hears from
 * the server that one arrived (the "amani:messages" event).
 */
export function useMessages(enabled: boolean) {
  const [items, setItems] = useState<Msg[]>([]);
  const [unseen, setUnseen] = useState(0);
  const load = useCallback(async () => {
    try {
      const r = await api<{ unseen: number; items: Msg[] }>("/messages/?banner=1");
      setItems(r.items); setUnseen(r.unseen);
    } catch { /* offline: keep what is shown */ }
  }, []);
  useEffect(() => {
    if (!enabled) return;
    load();
    const i = setInterval(load, 20_000);
    const vis = () => { if (document.visibilityState === "visible") load(); };
    window.addEventListener("amani:messages", load);
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(i); window.removeEventListener("amani:messages", load); document.removeEventListener("visibilitychange", vis); };
  }, [enabled, load]);
  const dismiss = useCallback(async (id: number) => {
    setItems((l) => l.filter((m) => m.id !== id));
    setUnseen((n) => Math.max(0, n - 1));
    try { await api(`/messages/${id}/dismiss/`, { body: {} }); } catch { load(); }
  }, [load]);
  return { items, unseen, dismiss };
}

/** Administrators: send the same message to one or more accounts. Throws the server's friendly text on failure. */
export async function sendMessage(recipients: number[], body: string): Promise<number> {
  const r = await api<{ sent: number }>("/admin/messages/", { body: { recipients, body } });
  return r.sent;
}
