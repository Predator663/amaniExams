"use client";
import { useState } from "react";
import Shell from "@/components/Shell";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { AVATAR_EMOJI } from "@/lib/emoji";
import { useSession } from "@/lib/session";

/** SRS 5.6: class-level, weekly or all-time, ranks XP only, display names only, can be hidden. */
export default function Leaderboard() {
  const { t } = useSession();
  const [period, setPeriod] = useState<"weekly" | "all">("weekly");
  const { data, error, loading, reload } = useLoad(() => api<any>(`/gamification/leaderboard/?period=${period}`), [period]);
  return (
    <Shell title={t("leaderboard")}>
      <div className="chips" role="group">
        {(["weekly", "all"] as const).map((p) => <button key={p} className={`chip ${period === p ? "on" : ""}`} aria-pressed={period === p} onClick={() => setPeriod(p)}>{period === p ? "✓ " : ""}{t(p === "weekly" ? "this_week" : "all_time")}</button>)}
      </div>
      {loading ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : !data.enabled ? <div className="card"><p className="muted">{data.message}</p></div> : (
        <>
          <p className="muted small">{t("leaderboard_note")}</p>
          {data.you.message && <p className="hint">{data.you.message}</p>}
          <ol className="list card">
            {data.entries.map((e: any) => (
              <li key={e.rank + e.name} className="row" style={e.is_me ? { background: "var(--soft)", borderRadius: 8, padding: ".7rem" } : undefined}>
                <b style={{ width: 32 }}>{e.rank <= 3 ? ["🥇", "🥈", "🥉"][e.rank - 1] : e.rank}</b><span aria-hidden>{AVATAR_EMOJI[e.avatar]}</span>
                <span className="grow">{e.name}{e.is_me ? ` (${t("you")})` : ""}<br /><span className="small muted">{t("level_n", { n: e.level })}</span></span><b>{e.xp} XP</b>
              </li>
            ))}
            {!data.entries.length && <li className="muted">{t("no_xp")}</li>}
          </ol>
        </>
      )}
    </Shell>
  );
}
