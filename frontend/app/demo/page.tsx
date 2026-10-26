"use client";
import Link from "next/link";
import { useState } from "react";
import QuestionView, { hasAnswer, initialValue } from "@/components/QuestionView";
import Shell from "@/components/Shell";
import { Bar } from "@/components/ui";
import { useSession } from "@/lib/session";
import type { Question } from "@/lib/types";

const DEMO: Question[] = [
  { id: 1, type: "mcq_single", prompt: "<p>Practice question: what is <b>2 + 2</b>?</p>", marks: 1, content: { options: [{ id: "a", text: "3" }, { id: "b", text: "4" }, { id: "c", text: "5" }] } },
  { id: 2, type: "true_false", prompt: "<p>The sun rises in the east.</p>", marks: 1, content: {} },
  { id: 3, type: "fill_blank", prompt: "<p>Type the word <i>amani</i>.</p>", marks: 1, content: {} },
];

/** HOME-05: a short practice demo so students learn the exam screen before the real exam. Nothing is sent or marked. */
export default function Demo() {
  const { t } = useSession();
  const [i, setI] = useState(0), [v, setV] = useState<any>(initialValue(DEMO[0])), [msg, setMsg] = useState("");
  const q = DEMO[i];
  function next() {
    if (!hasAnswer(q, v)) return setMsg(t("answer_first"));
    setMsg(""); if (i + 1 < DEMO.length) { setI(i + 1); setV(initialValue(DEMO[i + 1])); } else setI(DEMO.length);
  }
  return (
    <Shell bare title={t("demo_title")}>
      <p className="hint">{t("demo_note")}</p>
      {i >= DEMO.length ? (
        <div className="card center"><span className="big-num">🎉</span><h2>{t("demo_done")}</h2><Link className="btn primary" href="/">{t("back_home")}</Link></div>
      ) : (
        <>
          <div className="exam-head" style={{ position: "static" }}><div className="row"><div className="grow small muted">{t("question_x_of_y", { x: i + 1, y: DEMO.length })}</div><div className="timer">10:00</div></div><Bar value={(i / DEMO.length) * 100} label={t("progress")} /></div>
          <div key={q.id} className="card slide-in" style={{ marginTop: ".9rem" }}>
            <QuestionView q={q} value={v} onChange={(x) => { setV(x); setMsg(""); }} />
            {msg && <p className="no" role="alert">⚠ {msg}</p>}
            <button className="btn primary big" style={{ marginTop: "1rem" }} onClick={next}>{t("submit_answer")}</button>
          </div>
        </>
      )}
    </Shell>
  );
}
