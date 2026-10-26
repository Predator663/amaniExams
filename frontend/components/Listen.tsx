"use client";
import { useEffect, useState } from "react";
import { htmlToText, speak, speechSupported, stopSpeaking } from "@/lib/speech";
import { useSession } from "@/lib/session";
import type { Question } from "@/lib/types";

export function questionText(q: Question, t: (k: string) => string) {
  const parts = [htmlToText(q.prompt)];
  const c = q.content || {};
  const list = (items: any[]) => items.map((o, i) => `${i + 1}. ${htmlToText(o.text || "")} ${o.alt_text ? `Image: ${o.alt_text}` : ""}`);
  if (c.options) parts.push(...list(c.options));
  if (c.items) parts.push(...list(c.items));
  if (c.left) parts.push(t("left_side"), ...list(c.left), t("right_side"), ...list(c.right));
  return parts.join(". ");
}

/** ACC-03: the "Listen" button appears when the student turned read-aloud on. */
export default function Listen({ q }: { q: Question }) {
  const { user, lang, t } = useSession();
  const [on, setOn] = useState(false);
  useEffect(() => () => { stopSpeaking(); }, [q.id]);
  if (!user?.accessibility.read_aloud || !speechSupported()) return null;
  return (
    <button className="btn" aria-pressed={on} onClick={() => {
      if (on) { stopSpeaking(); setOn(false); return; }
      speak(questionText(q, t), lang); setOn(true);
      const done = setInterval(() => { if (!window.speechSynthesis.speaking) { setOn(false); clearInterval(done); } }, 500);
    }}>{on ? `⏹ ${t("stop")}` : `🔊 ${t("listen")}`}</button>
  );
}
