"use client";
import Link from "next/link";
import { useEffect } from "react";
import Shell from "@/components/Shell";
import { ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { eatDate } from "@/lib/clock";
import { useSession } from "@/lib/session";

/** NOT-01: in-app notifications (upcoming exams, exam start, results ready, password changes, badges). */
export default function Notifications() {
  const { t, lang } = useSession();
  const { data, error, loading, reload } = useLoad(() => api<{ unread: number; items: any[] }>("/notifications/"));
  useEffect(() => { if (data?.unread) api("/notifications/read/", { body: { all: true } }).then(() => window.dispatchEvent(new Event("amani:notifications"))).catch(() => {}); }, [data]);
  const link = (n: any) => n.kind === "results_ready" || n.kind === "results" ? "/results/" : n.data?.attempt_id ? `/result/?id=${n.data.attempt_id}`
    : n.kind === "exam_reminder" || n.kind === "exam_start" ? (n.data?.exam_id ? `/exam/?id=${n.data.exam_id}` : null)
    : n.kind === "badge" || n.kind === "level_up" ? "/badges/" : null;
  return (
    <Shell title={t("notifications")}>
      {loading ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : !data!.items.length ? <div className="card"><p className="muted">{t("no_notifications")}</p></div> : data!.items.map((n) => {
        const href = link(n);
        const body = <><b>{n.title}</b><p style={{ margin: ".2rem 0" }}>{n.body}</p><span className="small muted">{eatDate(n.created_at, undefined, lang)}</span></>;
        return href ? <Link key={n.id} href={href} className={`card ${n.read ? "" : "unread"}`} style={{ display: "block", textDecoration: "none", color: "inherit" }}>{body}</Link> : <div key={n.id} className={`card ${n.read ? "" : "unread"}`}>{body}</div>;
      })}
    </Shell>
  );
}
