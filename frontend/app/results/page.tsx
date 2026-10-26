"use client";
import Link from "next/link";
import Shell from "@/components/Shell";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

export default function Results() {
  const { t, lang } = useSession();
  const { data, error, loading, reload } = useLoad(() => api<any[]>("/results/"));
  return (
    <Shell title={t("nav_results")}>
      {loading ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : !data?.length ? <div className="card"><p className="muted">{t("no_results")}</p></div> : (
        <>
          {data.map((r) => (
            <Link key={r.attempt_id} href={`/result/?id=${r.attempt_id}`} className="card row" style={{ textDecoration: "none", color: "inherit" }}>
              <span className="grow"><b>{r.exam}</b><br /><span className="muted small">{r.subject} · {eatDate(r.date, { day: "numeric", month: "short", year: "numeric" }, lang)}</span></span>
              <span><b>{Math.round(r.percent)}%</b> · <b>{r.grade}</b></span><span aria-hidden>›</span>
            </Link>
          ))}
          <Link className="btn" href="/progress/">📈 {t("my_analytics")}</Link>
        </>
      )}
    </Shell>
  );
}
