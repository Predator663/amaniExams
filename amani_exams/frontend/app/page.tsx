"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ExamSections from "@/components/ExamSections";
import Shell from "@/components/Shell";
import { Bar, CountUp, ErrorNote, Loading, Modal, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { BADGE_EMOJI, TIER_MARK } from "@/lib/emoji";
import { useSession } from "@/lib/session";
import type { ExamCard } from "@/lib/types";

type Summary = {
  xp: number; level: { level: number; name: string; next_name: string | null; progress_percent: number; xp_to_next: number };
  level_up: { from: number; to: number; name: string } | null;
  streak: { current: number; best: number; message: string; active_today: boolean; freezes_left_this_month: number };
  exam_streak: { current: number; best: number };
  recent_badges: { code: string; name: string; tier: string; tier_label: string; subject: string | null; new: boolean }[];
  new_badges: number; next_goals: { code: string; name: string; subject: string | null; progress: number; target: number; unit: string }[];
};
type ResultRow = { attempt_id: number; exam: string; subject: string; percent: number; grade: string; date: string };

function StudentHome() {
  const { user, t } = useSession();
  const exams = useLoad(() => api<ExamCard[]>("/student/exams/"));
  const sum = useLoad(() => api<Summary>("/gamification/me/"));
  const res = useLoad(() => api<ResultRow[]>("/results/"));
  const [celebrate, setCelebrate] = useState(false);

  useEffect(() => { if (sum.data && (sum.data.level_up || sum.data.new_badges > 0)) setCelebrate(true); }, [sum.data]);
  const ack = () => { setCelebrate(false); api("/gamification/ack/", { method: "POST", body: {} }).catch(() => {}); };

  const s = sum.data;
  const fresh = (res.data || []).slice(0, 3);
  return (
    <>
      <h1>{t("hello", { name: user!.first_name || user!.username })} <span className="wave" aria-hidden>👋</span></h1>

      {exams.loading ? <Loading /> : exams.error ? <ErrorNote error={exams.error} retry={exams.reload} /> : <ExamSections cards={exams.data || []} />}

      {fresh.length > 0 && (
        <>
          <h2>{t("results_ready")}</h2>
          {fresh.map((r) => (
            <Link key={r.attempt_id} href={`/result/?id=${r.attempt_id}`} className="card row" style={{ textDecoration: "none", color: "inherit" }}>
              <span className="grow"><b>{r.exam}</b><br /><span className="muted small">{r.subject}</span></span>
              <span className="big-num" style={{ fontSize: "1.6rem" }}>{r.grade}</span>
              <span aria-hidden>›</span>
            </Link>
          ))}
        </>
      )}

      <h2>{t("my_progress")}</h2>
      {sum.loading ? <Loading /> : s ? (
        <>
          <div className="card">
            <div className="row">
              <span className="flame" aria-hidden>{s.streak.current > 0 ? "🔥" : "🕯️"}</span>
              <div className="grow">
                <b>{t("day_streak", { n: s.streak.current })}</b>
                <div className="muted small">{t("best_streak", { n: s.streak.best })} · {t("freezes_left", { n: s.streak.freezes_left_this_month })}</div>
              </div>
            </div>
            {s.streak.message && <p className="hint">{s.streak.message}</p>}
          </div>
          <div className="card">
            <div className="row"><b>{t("level_n", { n: s.level.level })} · {s.level.name}</b><span className="grow" /><b><CountUp to={s.xp} /> XP</b></div>
            <Bar value={s.level.progress_percent} label={t("xp_progress")} />
            <p className="muted small">{s.level.next_name ? t("xp_to_next", { n: s.level.xp_to_next, name: s.level.next_name }) : t("top_level")}</p>
          </div>
          {s.recent_badges.length > 0 && (
            <div className="card">
              <div className="row"><b className="grow">{t("recent_badges")}</b><Link href="/badges/">{t("see_all")}</Link></div>
              <div className="grid3">
                {s.recent_badges.map((b, i) => (
                  <div key={i} className={`badge-tile tier-${b.tier}`}><span className="em" aria-hidden>{BADGE_EMOJI[b.code] || "🏅"}</span><b className="small">{b.name}</b>{b.subject && <div className="small muted">{b.subject}</div>}<div className="small">{TIER_MARK[b.tier]} {b.tier_label}</div></div>
                ))}
              </div>
            </div>
          )}
          {s.next_goals.length > 0 && (
            <div className="card"><b>{t("next_goals")}</b>
              {s.next_goals.map((g, i) => (
                <div key={i} style={{ margin: ".6rem 0" }}><div className="small">{g.name}{g.subject ? ` – ${g.subject}` : ""}: {g.progress}/{g.target} {g.unit}</div><Bar value={(g.progress / g.target) * 100} label={g.name} /></div>
              ))}
            </div>
          )}
        </>
      ) : sum.error ? <ErrorNote error={sum.error} retry={sum.reload} /> : null}

      <div className="grid2">
        <Link className="btn" href="/practice/">✏️ {t("nav_practice")}</Link>
        <Link className="btn" href="/leaderboard/">🏆 {t("leaderboard")}</Link>
        <Link className="btn" href="/progress/">📈 {t("my_analytics")}</Link>
        <Link className="btn" href="/install/">📲 {t("install_app")}</Link>
      </div>
      <p className="center-text"><Link href="/demo/">{t("try_demo")}</Link></p>

      {celebrate && s && (
        <Modal label={t("well_done")} onClose={ack}>
          <div className="center pop">
            <span className="big-num" aria-hidden>🎉</span>
            <h2>{t("well_done")}</h2>
            {s.level_up && <p><b>{t("level_up", { name: s.level_up.name, n: s.level_up.to })}</b></p>}
            {s.recent_badges.filter((b) => b.new).map((b, i) => <p key={i}>{BADGE_EMOJI[b.code]} {t("new_badge", { name: b.name })}</p>)}
            <button className="btn primary" onClick={ack}>{t("thanks")}</button>
          </div>
        </Modal>
      )}
    </>
  );
}

export default function Home() {
  const { user, t } = useSession();
  useEffect(() => { if (user && user.role !== "student") location.replace("/staff/"); }, [user]);
  return (
    <Shell>
      {user?.role === "student" ? <StudentHome /> : (
        <div className="card center">
          <h1>{t("staff_notice_title")}</h1>
          <p>{t("staff_notice")}</p>
          <Link className="btn primary" href="/staff/">{t("open_staff")}</Link>
        </div>
      )}
    </Shell>
  );
}
