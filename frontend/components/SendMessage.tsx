"use client";
import { useState } from "react";
import { sendMessage } from "@/lib/messages";
import { Modal } from "./ui";

/** A small window for an administrator to message one or two accounts at once (used from the Anti-cheat tab). */
export default function SendMessage({ to, onClose }: { to: { id: number; name: string }[]; onClose: () => void }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const send = async () => {
    setBusy(true); setErr("");
    try { await sendMessage(to.map((p) => p.id), body); setDone(true); }
    catch (e: any) { setErr(e?.message || "Could not send."); }
    setBusy(false);
  };
  return (
    <Modal label="Send a message" onClose={onClose}>
      <h2>Message {to.map((p) => p.name).join(" and ")}</h2>
      {done ? (
        <>
          <p role="status">Sent. It appears as a banner on top of their screen until they close it, then stays in their Messages tab until you delete it (Messages page).</p>
          <button className="btn primary" onClick={onClose}>Done</button>
        </>
      ) : (
        <>
          <label className="field"><span>Message ({body.length}/1000)</span>
            <textarea className="input" rows={4} maxLength={1000} autoFocus value={body} onChange={(e) => setBody(e.target.value)} placeholder="For example: You are too close to another student. Please move to a different room." /></label>
          {err && <p className="lb-alert" role="alert">{err}</p>}
          <div className="row-actions">
            <button className="btn primary" disabled={busy || !body.trim()} onClick={send}>{busy ? "Sending…" : "Send"}</button>
            <button className="btn" onClick={onClose}>Cancel</button>
          </div>
        </>
      )}
    </Modal>
  );
}
