"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import { RichHtml } from "@/components/Rich";
import { ErrorNote, Loading, useLoad, useQuery } from "@/components/ui";
import { api } from "@/lib/api";
import { describe } from "@/lib/answers";
import { useSession } from "@/lib/session";

/** RES-05: read-only review; also tells the server which questions she has seen (Mistake Master badge, review XP). */
function Review({ id }: { id: number }) {
  const { t } = useSession();
  const { data, error, loading, reload } = useLoad(() => api<any[]>(`/results/${id}/review/`), [id]);
  const [toast, setToast] = useState("");
  const seen = useRef<Set<number>>(new Set()), timer = useRef<any>(null);

  const report = () => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await api<any>(`/results/${id}/review/seen/`, { body: { numbers: [...seen.current] } });
        if (r.xp_awarded) { setToast(t("review_xp", { n: r.xp_awarded })); window.dispatchEvent(new Event("amani:notifications")); }
      } catch { /* the review still works offline of rewards */ }
    }, 900);
  };
  useEffect(() => {
    if (!data) return;
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { const n = Number((e.target as HTMLElement).dataset.n); if (!seen.current.has(n)) { seen.current.add(n); report(); } }
    }), { threshold: 0.6 });
    document.querySelectorAll("[data-n]").forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote error={error} retry={reload} />;
  return (
    <>
      <Link href={`/result/?id=${id}`}>← {t("back")}</Link>
      <h1>{t("review_answers")}</h1>
      {toast && <p className="hint pop" role="status">⭐ {toast}</p>}
      {data.map((q) => {
        const full = q.marks_awarded >= q.marks - 1e-9, part = q.marks_awarded > 0 && !full;
        return (
          <article key={q.number} data-n={q.number} className="card">
            <p className="small muted">{t("question_n", { n: q.number })} · {q.voided ? t("voided") : `${q.marks_awarded}/${q.marks}`}</p>
            <RichHtml html={q.prompt} className="prompt" />
            {q.voided ? <p className="hint">{t("voided_note")}</p> : (
              <>
                <p className={full ? "ok" : "no"}>{full ? "✓" : part ? "◐" : "✗"} {t("your_answer")}: {q.skipped ? t("skipped") : describe(q.type, q.content, q.your_response, t)}</p>
                {!full && <p><b>{t("correct_answer")}:</b> {describe(q.type, q.content, q.correct_answer, t)}</p>}
                {q.explanation && <div className="hint"><b>{t("explanation")}:</b> <RichHtml html={q.explanation} /></div>}
              </>
            )}
          </article>
        );
      })}
    </>
  );
}

export default function ReviewPage() {
  const id = useQuery("id");
  return <Shell>{id ? <Review id={Number(id)} /> : <Loading />}</Shell>;
}
