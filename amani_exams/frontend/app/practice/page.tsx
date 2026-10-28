"use client";
import { useEffect, useState } from "react";
import Listen from "@/components/Listen";
import QuestionView, { hasAnswer, initialValue } from "@/components/QuestionView";
import Shell from "@/components/Shell";
import { Bar, ErrorNote, Loading, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { describe } from "@/lib/answers";
import { useSession } from "@/lib/session";
import type { Question } from "@/lib/types";

type PState = { session_id: number; subject: string; total: number; answered: number; finished: boolean; index?: number; question?: Question; summary?: { questions: number; fully_correct: number; score_percent: number; xp_earned: number } };

/** SRS 5.5: short self-paced quizzes with instant feedback. They earn XP and keep streaks alive, never exam marks. */
function Play({ initial, onExit }: { initial: PState; onExit: () => void }) {
  const { t } = useSession();
  const [s, setS] = useState<PState>(initial), [v, setV] = useState<any>(), [fb, setFb] = useState<any>(null), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<Question | undefined>(initial.question);
  useEffect(() => { if (s.question) setV(initialValue(s.question)); }, [s.question?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send() {
    if (!shown || !hasAnswer(shown, v)) return setErr(t("answer_first"));
    setErr(""); setBusy(true);
    try {
      const r = await api<{ feedback: any; next: PState }>(`/practice/${s.session_id}/answer/`, { body: { question_id: shown.id, response: v } });
      setFb(r.feedback); setS(r.next);
      if (r.next.finished) window.dispatchEvent(new Event("amani:notifications"));
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }
  function next() { setFb(null); setShown(s.question); }

  if (fb && shown) {
    return (
      <div className="card slide-in">
        <h2 className={fb.correct ? "ok" : "no"}>{fb.correct ? "✓" : fb.fraction > 0 ? "◐" : "✗"} {fb.message}</h2>
        {!fb.correct && <p><b>{t("correct_answer")}:</b> {describe(shown.type, shown.content, fb.correct_answer, t)}</p>}
        {fb.explanation && <div className="hint"><b>{t("explanation")}:</b> {fb.explanation}</div>}
        <button className="btn primary big" style={{ marginTop: "1rem" }} onClick={next}>{s.finished ? t("see_summary") : t("next_question")}</button>
      </div>
    );
  }
  if (s.finished) {
    const m = s.summary!;
    return (
      <div className="card hero center pop">
        <span className="big-num" aria-hidden>🌟</span><h1>{t("practice_done")}</h1>
        <p>{t("practice_score", { a: m.fully_correct, b: m.questions })} · {m.score_percent}%</p>
        <p><b>+{m.xp_earned} XP</b></p>
        <button className="btn big" style={{ color: "var(--text)" }} onClick={onExit}>{t("back")}</button>
      </div>
    );
  }
  return (
    <div className="card slide-in" key={shown?.id}>
      <div className="row"><b className="grow">{s.subject}</b><span className="muted">{t("question_x_of_y", { x: s.index || 1, y: s.total })}</span></div>
      <Bar value={(s.answered / s.total) * 100} label={t("progress")} />
      {shown && <QuestionView q={shown} value={v} onChange={(x) => { setV(x); setErr(""); }} disabled={busy} />}
      {shown && <Listen q={shown} />}
      {err && <p className="no" role="alert">⚠ {err}</p>}
      <button className="btn primary big" style={{ marginTop: "1rem" }} disabled={busy} onClick={send}>{t("check_answer")}</button>
    </div>
  );
}

export default function Practice() {
  const { t } = useSession();
  const subs = useLoad(() => api<any[]>("/practice/subjects/"));
  const [game, setGame] = useState<PState | null>(null), [err, setErr] = useState(""), [count, setCount] = useState(10);
  async function start(id: number) {
    setErr("");
    try { setGame(await api<PState>("/practice/start/", { body: { subject_id: id, count } })); } catch (e: any) { setErr(e.message); }
  }
  return (
    <Shell title={t("nav_practice")}>
      {game ? <Play initial={game} onExit={() => { setGame(null); subs.reload(); }} /> : (
        <>
          <p className="muted">{t("practice_intro")}</p>
          <label className="field"><span>{t("how_many")}: {count}</span><input type="range" min={5} max={20} value={count} onChange={(e) => setCount(Number(e.target.value))} /></label>
          {err && <p className="no" role="alert">⚠ {err}</p>}
          {subs.loading ? <Loading /> : subs.error ? <ErrorNote error={subs.error} retry={subs.reload} /> : !subs.data?.length ? <div className="card"><p className="muted">{t("practice_none")}</p></div> :
            subs.data.map((s) => (
              <div key={s.id} className="card row">
                <span className="grow"><b>{s.name}</b><br /><span className="muted small">{t("n_questions_available", { n: s.available_questions })}</span></span>
                <button className="btn primary" disabled={!s.can_start} onClick={() => start(s.id)}>{s.can_start ? t("start") : t("not_enough")}</button>
              </div>
            ))}
        </>
      )}
    </Shell>
  );
}
