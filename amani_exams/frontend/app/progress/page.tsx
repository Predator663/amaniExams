"use client";
import Shell from "@/components/Shell";
import { Bar, ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

/** RES-04, GRD-02, GRD-03: strengths and weak areas, progress per subject, what to revise, projected division. */
export default function Progress() {
  const { t } = useSession();
  const a = useLoad(() => api<any>("/student/analytics/"));
  if (a.loading) return <Shell title={t("my_analytics")}><Loading /></Shell>;
  if (a.error || !a.data) return <Shell title={t("my_analytics")}><ErrorNote error={a.error} retry={a.reload} /></Shell>;
  const d = a.data, p = d.projected;
  return (
    <Shell title={t("my_analytics")}>
      {d.exams_taken === 0 ? <div className="card"><p className="muted">{t("no_results")}</p></div> : (
        <>
          <div className="card">
            <h2>{t("projected_division")}</h2>
            {p.division ? <p><span className="big-num">{t("division")} {p.division}</span><br /><span className="muted">{p.meaning} · {p.total_points} {t("points")}</span></p>
              : <p className="muted">{t("need_subjects", { n: p.subjects_needed, have: p.subjects_taken })}</p>}
            <p className="hint">ℹ {p.note}</p>
            <div className="tbl-wrap"><table><thead><tr><th>{t("subject")}</th><th>%</th><th>{t("grade")}</th><th>{t("points")}</th></tr></thead>
              <tbody>{p.subjects.map((r: any) => <tr key={r.subject}><td>{r.subject}{r.counted ? "" : ` (${t("not_counted")})`}</td><td>{r.average}</td><td>{r.grade}</td><td>{r.points}</td></tr>)}</tbody></table></div>
          </div>
          {d.subjects.map((s: any) => (
            <div key={s.subject} className="card">
              <h2>{s.subject}</h2>
              <p>{t("average")}: <b>{s.average}%</b> · {t("latest")}: <b>{s.latest}%</b>{s.change_from_previous !== null && <> · <b className={s.change_from_previous >= 0 ? "ok" : "no"}>{s.change_from_previous >= 0 ? "▲" : "▼"} {Math.abs(s.change_from_previous)}</b></>}</p>
              <div className="row" role="img" aria-label={t("progress_chart")} style={{ alignItems: "flex-end", height: 90 }}>
                {s.progress.map((h: any, i: number) => <div key={i} title={`${h.percent}%`} style={{ flex: 1, height: `${Math.max(4, h.percent)}%`, background: "var(--primary)", borderRadius: 4 }} />)}
              </div>
              <h3>{t("topics")}</h3>
              {s.topics.map((x: any) => <div key={x.topic} style={{ margin: ".5rem 0" }}><div className="row"><span className="grow">{x.topic}</span><b>{Math.round(x.percent)}%</b></div><Bar value={x.percent} label={x.topic} /></div>)}
              {s.revise?.length > 0 && <p className="hint"><b>{t("revise")}:</b> {s.revise.join(", ")}</p>}
            </div>
          ))}
        </>
      )}
    </Shell>
  );
}
