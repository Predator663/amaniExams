"use client";
import Link from "next/link";
import { clock, eatDate, makeOffset } from "@/lib/clock";
import { useSession } from "@/lib/session";
import type { ExamCard } from "@/lib/types";
import { useNow } from "./ui";

/** HOME-01/02: days remaining, switching to hours and minutes on the exam day; 'Exam today'; 'Starts in 10 minutes'. */
export default function ExamBanner({ cards, label }: { cards: ExamCard[]; label?: string }) {
  const { t, lang } = useSession();
  const now = useNow(1000);
  if (!cards.length) return <div className="card"><p className="muted">{t("no_upcoming")}</p></div>;
  const n = now + makeOffset(cards[0].server_time);  // server time, not the phone's clock (BR-03)
  return (
    <div className="snap" role="list" aria-label={label || t("upcoming_exams")}>
      {cards.map((c) => {
        const start = new Date(c.start_at).getTime(), end = new Date(c.end_at).getTime();
        const diff = start - n;
        const dayKey = (ms: number) => new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Dar_es_Salaam" }).format(new Date(ms));
        const today = dayKey(n) === dayKey(start);
        let head = "", big = "";
        if (c.state === "done") { head = t("exam_done"); }
        else if (c.state === "missed" || n > end) { head = t("exam_missed"); }
        else if (c.state === "in_progress") { head = t("exam_in_progress"); }
        else if (diff <= 0) { head = t("exam_open_now"); }
        else if (diff <= 10 * 60_000) { head = t("starts_in_10"); big = clock(diff); }
        else if (today) { head = t("exam_today"); big = clock(diff); }
        else { const d = Math.ceil(diff / 86_400_000); head = d === 1 ? t("tomorrow") : t("days_to_go", { n: d }); big = `${d}`; }
        const go = c.state === "in_progress" || c.state === "open" || (c.state === "upcoming" && today);
        return (
          <div key={c.id} className="card" role="listitem">
            <p className="small muted">{c.subject}</p>
            <h3 style={{ margin: 0 }}>{c.title}</h3>
            <p className="muted small">{eatDate(c.start_at, undefined, lang)} · {c.duration_minutes} {t("minutes")} · {c.question_count} {t("questions")}</p>
            <p><b>{head}</b>{big && today ? <span className="big-num" style={{ display: "block" }} aria-live="off">{big}</span> : null}</p>
            {go && <Link className="btn primary" href={`/exam/?id=${c.id}`}>{c.state === "in_progress" ? t("continue_exam") : t("open_exam")}</Link>}
            {!go && c.state === "upcoming" && <Link className="btn" href={`/exam/?id=${c.id}`}>{t("see_details")}</Link>}
          </div>
        );
      })}
    </div>
  );
}
