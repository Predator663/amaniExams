"use client";
import ExamBanner from "@/components/ExamBanner";
import { useSession } from "@/lib/session";
import type { ExamCard } from "@/lib/types";

const ts = (c: ExamCard) => new Date(c.start_at).getTime();

/** Student home: what she can do now first, then upcoming (soonest first), then everything else. */
export default function ExamSections({ cards }: { cards: ExamCard[] }) {
  const { t } = useSession();
  const live = cards.filter((c) => c.state === "in_progress" || c.state === "open").sort((a, b) => ts(a) - ts(b));
  const upcoming = cards.filter((c) => c.state === "upcoming").sort((a, b) => ts(a) - ts(b));
  const earlier = cards.filter((c) => c.state === "done" || c.state === "missed").sort((a, b) => ts(b) - ts(a));
  return (
    <div className="exam-sections">
      {live.length > 0 && (<section><h2>{t("exams_live")}</h2><ExamBanner cards={live} label={t("exams_live")} /></section>)}
      <section>
        <h2>{t("upcoming_exams")}</h2>
        {upcoming.length > 0 ? <ExamBanner cards={upcoming} /> : live.length === 0 ? <div className="card"><p className="muted">{t("no_upcoming")}</p></div> : <p className="muted small">{t("no_upcoming")}</p>}
      </section>
      {earlier.length > 0 && (<section><h2>{t("exams_earlier")}</h2><ExamBanner cards={earlier} label={t("exams_earlier")} /></section>)}
    </div>
  );
}
