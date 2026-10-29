"use client";
import Link from "next/link";
import ResultsWaiting from "@/components/ResultsWaiting";
import { Pager, usePaged } from "@/components/Pager";
import Shell from "@/components/Shell";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

export default function Results() {
  const { t, lang } = useSession();
  const pg = usePaged<any>("/results/", {}, { size: 10 });
  const { rows: data, error, loading, reload } = pg;
  const pend = useLoad(() => api<any[]>("/results/pending/"));
  return (
    <Shell title={t("nav_results")}>
      {pend.data?.map((p) => <ResultsWaiting key={p.attempt_id} attemptId={p.attempt_id} title={`${p.exam} · ${p.subject}`} resultsAt={p.results_at} serverTime={p.server_time} compact />)}
      {loading ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : !data.length ? (pend.data?.length ? null : <div className="card"><p className="muted">{t("no_results")}</p></div>) : (
        <>
          <div ref={pg.top} className={`paged`} aria-busy={pg.busy || undefined}>
          {data.map((r) => (
            <Link key={r.attempt_id} href={`/result/?id=${r.attempt_id}`} className="card row" style={{ textDecoration: "none", color: "inherit" }}>
              <span className="grow"><b>{r.exam}</b><br /><span className="muted small">{r.subject} · {eatDate(r.date, { day: "numeric", month: "short", year: "numeric" }, lang)}</span></span>
              <span><b>{Math.round(r.percent)}%</b> · <b>{r.grade}</b></span><span aria-hidden>›</span>
            </Link>
          ))}
          </div>
          <Pager {...pg.pager} />
          <Link className="btn" href="/progress/">📈 {t("my_analytics")}</Link>
        </>
      )}
    </Shell>
  );
}
