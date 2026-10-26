"use client";
import Shell from "@/components/Shell";
import { Bar, ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { AVATAR_EMOJI, BADGE_EMOJI, TIER_MARK } from "@/lib/emoji";
import { useSession } from "@/lib/session";

/** SRS 5.4 / 5.6: badge cabinet with what to aim for next, XP history, profile. */
export default function Badges() {
  const { t } = useSession();
  const b = useLoad(() => api<any[]>("/gamification/badges/"));
  const xp = useLoad(() => api<any>("/gamification/xp/?limit=15"));
  const me = useLoad(() => api<any>("/gamification/me/"));
  return (
    <Shell title={t("nav_badges")}>
      {me.data && (
        <div className="card row">
          <span style={{ fontSize: "2.4rem" }} aria-hidden>{AVATAR_EMOJI[me.data.profile.avatar] || "🦉"}</span>
          <div className="grow"><b>{me.data.profile.display_name || t("my_profile")}</b><br /><span className="muted">{t("level_n", { n: me.data.level.level })} · {me.data.level.name} · {me.data.xp} XP</span></div>
        </div>
      )}
      {b.loading ? <Loading /> : b.error ? <ErrorNote error={b.error} retry={b.reload} /> : (
        <div className="grid2">
          {b.data!.map((x, i) => (
            <div key={i} className={`badge-tile tier-${x.tier} ${x.earned ? "" : "locked"}`}>
              <span className="em" aria-hidden>{BADGE_EMOJI[x.code] || "🏅"}</span>
              <b>{x.name}</b>{x.subject && <div className="small muted">{x.subject}</div>}
              <div className="small">{x.earned ? `${TIER_MARK[x.tier] || ""} ${x.tier_label}` : `🔒 ${t("locked")}`}</div>
              <p className="small muted">{x.description}</p>
              {x.next_target ? <><div className="small">{x.progress}/{x.next_target} {x.unit}</div><Bar value={(x.progress / x.next_target) * 100} label={x.name} /></> : <div className="small ok">{t("max_tier")}</div>}
            </div>
          ))}
        </div>
      )}
      <h2>{t("xp_history")}</h2>
      {xp.data && <ul className="list card">{xp.data.results.map((e: any, i: number) => <li key={i} className="row"><span className="grow">{e.label}</span><b>+{e.points}</b></li>)}{!xp.data.results.length && <li className="muted">{t("no_xp")}</li>}</ul>}
    </Shell>
  );
}
