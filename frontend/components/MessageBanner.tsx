"use client";
import type { Msg } from "@/lib/messages";
import { useSession } from "@/lib/session";

/** A message from the school at the very top of the screen, above everything (also above the exam lock screen). One tap closes it;
 *  it then stays in the Messages tab until an administrator deletes it. */
export default function MessageBanner({ items, onClose }: { items: Msg[]; onClose: (id: number) => void }) {
  const { t } = useSession();
  const m = items[0];
  if (!m) return null;
  return (
    <div className="msg-banner-wrap" role="alert" aria-live="assertive">
      <button type="button" className="msg-banner" onClick={() => onClose(m.id)} aria-label={`${t("msg_from")}: ${m.body}. ${t("msg_tap")}`}>
        <span className="msg-head"><b>{t("msg_from")}</b>{items.length > 1 && <small>{t("msg_more", { n: items.length - 1 })}</small>}</span>
        <span className="msg-text">{m.body}</span>
        <span className="msg-close" aria-hidden="true">{t("msg_tap")} ✕</span>
      </button>
    </div>
  );
}
