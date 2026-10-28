"use client";
import Link from "next/link";
import { useState } from "react";
import Shell from "@/components/Shell";
import { Bar, Confetti, CountUp, ErrorNote, Loading, useLoad, useNow, useQuery } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import { clock, eatDate } from "@/lib/clock";
import { BADGE_EMOJI, TIER_MARK } from "@/lib/emoji";
import { useSession } from "@/lib/session";

/** RES-03: score, percentage, grade, time taken, anonymous class average, optional class position, XP and badges. */
function Detail({ id }: { id: number }) {
  const { t, lang } = useSession();
  const { data: d, error, err, loading, reload } = useLoad(() => api<any>(`/results/${id}/`), [id]);
  const [dl, setDl] = useState("");
  const now = useNow(1000);
  if (loading) return <Loading />;
  if (err?.code === "not_ready") {
    const at = err.data?.results_at ? new Date(err.data.results_at).getTime() : 0;
    return <div className="card center"><h2>{t("results_not_ready")}</h2>{at > now && <p className="big-num">{clock(at - now)}</p>}<p className="muted">{at ? t("results_at", { when: eatDate(err.data.results_at, undefined, lang) }) : ""}</p><button className="btn" onClick={reload}>{t("check_again")}</button></div>;
  }
  if (error || !d) return <ErrorNote error={error} retry={reload} />;
  const mins = Math.floor(d.time_taken_seconds / 60), secs = d.time_taken_seconds % 60;
  return (
    <>
      {d.passed && <Confetti once={`result-${id}`} />}
      <p className="muted">{d.subject}</p>
      <h1>{d.exam}</h1>
      <div className="card hero center">
        <span className="big-num">{Number.isInteger(d.score) ? <CountUp to={d.score} /> : d.score}/{d.total}</span>
        <span style={{ fontSize: "1.3rem" }}>{Math.round(d.percent)}% · {t("grade")} {d.grade} ({d.points} {t("points")})</span>
        <b>{d.passed ? `✓ ${t("passed")}` : t("keep_going")}</b>
      </div>
      <div className="grid2">
        <div className="stat"><b>{mins}:{String(secs).padStart(2, "0")}</b>{t("time_taken")}</div>
        <div className="stat"><b>{d.class_average_percent}%</b>{t("class_average")}</div>
        {d.class_position && <div className="stat"><b>{d.class_position}/{d.class_size}</b>{t("class_position")}</div>}
      </div>

      {d.rewards && (d.rewards.xp.length > 0 || d.rewards.badges.length > 0) && (
        <div className="card"><h2>{t("you_earned")}</h2>
          <p className="big-num" style={{ fontSize: "2rem" }}>+<CountUp to={d.rewards.xp_total} /> XP</p>
          <ul className="list">{d.rewards.xp.map((x: any, i: number) => <li key={i} className="row"><span className="grow">{x.label}</span><b>+{x.points}</b></li>)}</ul>
          {d.rewards.badges.map((b: any, i: number) => <p key={i} className="pop">{BADGE_EMOJI[b.code] || "🏅"} <b>{b.name}</b>{b.subject ? ` – ${b.subject}` : ""} {TIER_MARK[b.tier]} {b.tier_label}</p>)}
        </div>
      )}

      <div className="card"><h2>{t("by_topic")}</h2>
        {d.topics.map((x: any) => (
          <div key={x.topic} style={{ margin: ".7rem 0" }}>
            <div className="row"><span className="grow">{x.topic}</span><b>{Math.round(x.percent)}% {x.percent >= 60 ? "✓" : "↗"}</b></div>
            <Bar value={x.percent} label={x.topic} />
          </div>
        ))}
        {d.revise?.length > 0 && <p className="hint"><b>{t("revise")}:</b> {d.revise.join(", ")}</p>}
      </div>

      <div className="row">
        <Link className="btn primary grow" href={`/review/?id=${id}`}>🔍 {t("review_answers")}</Link>
        <button className="btn grow" onClick={() => downloadFile(`/results/${id}/slip/?file=pdf`, `result-slip-${id}.pdf`).catch((e) => setDl(e.message))}>⬇ {t("download_slip")}</button>
      </div>
      {dl && <p className="no" role="alert">{dl}</p>}
    </>
  );
}

export default function Result() {
  const id = useQuery("id");
  return <Shell>{id ? <Detail id={Number(id)} /> : <Loading />}</Shell>;
}
