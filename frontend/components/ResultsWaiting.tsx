"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useNow } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, eatDate, makeOffset } from "@/lib/clock";
import { useSession } from "@/lib/session";

/** After submitting: "Submitted, waiting for results" with a live countdown to the release time.
    At zero it asks the server for the result (which publishes it and creates the notification),
    refreshes the bell, and turns into a "View my results" button, all without a page refresh. */
export default function ResultsWaiting({ attemptId, title, resultsAt, serverTime, compact = false }: {
  attemptId: number; title?: string; resultsAt: string; serverTime?: string; compact?: boolean;
}) {
  const { t, lang } = useSession();
  const now = useNow(1000);
  const offset = useRef(serverTime ? makeOffset(serverTime) : 0);
  const at = new Date(resultsAt).getTime();
  const total = useRef(Math.max(1000, at - (Date.now() + offset.current)));
  const left = at - (now + offset.current);
  const [ready, setReady] = useState(false);
  const busy = useRef(false);

  useEffect(() => {
    if (ready || left > 0) return;
    let stop = false;
    const check = async () => {
      if (busy.current || stop) return;
      busy.current = true;
      try {
        await api(`/results/${attemptId}/`);  // 200 = published (and the results-ready notification now exists)
        if (stop) return;
        setReady(true);
        window.dispatchEvent(new Event("amani:notifications"));  // refresh the bell straight away
        try {
          if ("Notification" in window && Notification.permission === "granted" && document.hidden)
            new Notification(t("results_ready_toast", { title: title || "" }), { icon: "/icons/icon-192.png" });
        } catch { /* optional */ }
      } catch { /* not ready yet: try again below */ }
      finally { busy.current = false; }
    };
    check();
    const i = setInterval(check, 4000);
    return () => { stop = true; clearInterval(i); };
  }, [left <= 0, ready, attemptId]); // eslint-disable-line react-hooks/exhaustive-deps

  const pct = ready ? 1 : Math.max(0, Math.min(1, 1 - left / total.current));
  const phase = ready ? "ready" : left > 0 ? "wait" : "prep";
  return (
    <section className={`rw rw-${phase}${compact ? " rw-compact" : ""}`} role="status" aria-live="polite">
      <span className="rw-glow" aria-hidden="true" />
      <div className="rw-ring" aria-hidden="true">
        <svg viewBox="0 0 120 120">
          <circle className="rw-track" cx="60" cy="60" r="52" />
          <circle className="rw-arc" cx="60" cy="60" r="52" pathLength={1} strokeDasharray={1} style={{ strokeDashoffset: 1 - pct }} />
          <circle className="rw-dash" cx="60" cy="60" r="44" pathLength={1} />
        </svg>
        <span className="rw-center">
          {phase === "ready" ? <b className="rw-tick">✓</b> : phase === "prep" ? <i className="rw-spin" /> : <b>{clock(left)}</b>}
        </span>
      </div>
      <div className="rw-text">
        {title && <small>{title}</small>}
        <h2>{phase === "ready" ? t("results_now_title") : t("waiting_title")}</h2>
        <p>{phase === "ready" ? t("results_now_sub") : phase === "prep" ? t("results_preparing") : t("waiting_sub")}</p>
        {phase === "wait" && <p className="rw-when">{t("results_in")} <b>{clock(left)}</b> · {eatDate(resultsAt, undefined, lang)}</p>}
        {phase === "ready" && <Link className="btn primary big" href={`/result/?id=${attemptId}`}>{t("view_my_results")}</Link>}
      </div>
    </section>
  );
}
