"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Listen from "@/components/Listen";
import QuestionView, { hasAnswer, initialValue } from "@/components/QuestionView";
import Shell from "@/components/Shell";
import { Bar, ErrorNote, Loading, Modal, useLoad, useNow } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { clock, eatDate, makeOffset } from "@/lib/clock";
import { clearAttempt, dequeue, enqueue, readDraft, readQueue, saveDraft } from "@/lib/offlineQueue";
import { useSession } from "@/lib/session";
import type { AttemptState, ExamCard } from "@/lib/types";

/* ------------------------------------------------------------------ pre-exam screen (EDAY-01, EDAY-02) */
function PreExam({ examId }: { examId: number }) {
  const { t, lang } = useSession();
  const { data, error, loading, reload } = useLoad(() => api<ExamCard[]>("/student/exams/"), [examId]);
  const [agree, setAgree] = useState(false), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const now = useNow(500);
  if (loading) return <Loading />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  const c = data?.find((x) => x.id === examId);
  if (!c) return <div className="card"><p>{t("exam_not_found")}</p><Link className="btn" href="/">{t("nav_home")}</Link></div>;
  if (c.state === "in_progress" && c.attempt_id) { location.replace(`/exam/?attempt=${c.attempt_id}`); return <Loading />; }

  const n = now + makeOffset(c.server_time);
  const diff = new Date(c.start_at).getTime() - n;
  const started = diff <= 0;
  const blocked = c.state === "done" || c.state === "missed";

  async function start() {
    setErr(""); setBusy(true);
    try {
      const s = await api<AttemptState>(`/student/exams/${examId}/start/`, { body: { agree_rules: true } });
      location.replace(`/exam/?attempt=${s.attempt_id}`);
    } catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="card">
      <p className="muted">{c.subject}</p>
      <h1>{c.title}</h1>
      <div className="grid3">
        <div className="stat"><b>{c.question_count}</b>{t("questions")}</div>
        <div className="stat"><b>{c.total_marks}</b>{t("total_marks")}</div>
        <div className="stat"><b>{c.duration_minutes}</b>{t("minutes")}</div>
      </div>
      <p className="muted">{eatDate(c.start_at, undefined, lang)}</p>
      <h2>{t("exam_rules")}</h2>
      <div className="hint" style={{ whiteSpace: "pre-wrap" }}>{c.rules_text || t("default_rules")}</div>
      <div className="hint" style={{ marginTop: ".6rem" }}>🔋 {t("connection_reminder")}</div>

      {blocked ? (
        <p className="no" role="alert">{c.state === "done" ? t("exam_done") : t("exam_missed")}</p>
      ) : (
        <>
          <label className="switch"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> {t("agree_rules")}</label>
          {!started && <p className="center-text" role="timer"><span className="muted">{t("starts_in")}</span><span className="big-num" style={{ display: "block" }}>{clock(diff)}</span></p>}
          {err && <p className="no" role="alert">⚠ {err}</p>}
          <button className="btn primary big" disabled={!started || !agree || busy} onClick={start}>{busy ? t("loading") : t("start")}</button>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ running exam (EDAY-03 .. EDAY-12) */
const stateKey = (id: number) => `amani_state_${id}`;

function beep() {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new Ctx(), o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination); o.frequency.value = 880; g.gain.value = 0.15;
    o.start(); o.stop(ctx.currentTime + 0.35);
  } catch { /* no sound on this phone */ }
}

function Runner({ attemptId }: { attemptId: number }) {
  const { t, lang } = useSession();
  const [st, setSt] = useState<AttemptState | null>(null);
  const [offset, setOffset] = useState(0);
  const [value, setValue] = useState<any>(undefined);
  const [busy, setBusy] = useState(false), [waiting, setWaiting] = useState(false), [offline, setOffline] = useState(false);
  const [msg, setMsg] = useState(""), [loadErr, setLoadErr] = useState("");
  const [confirm, setConfirm] = useState<null | "skip" | "finish">(null);
  const [banner, setBanner] = useState(""), [timeOver, setTimeOver] = useState(false);
  const [sound, setSound] = useState(true);
  const flushing = useRef(false), fired = useRef<Set<number>>(new Set()), finishing = useRef(false);
  const now = useNow(250);

  useEffect(() => { setSound(localStorage.getItem("amani_sound") !== "off"); }, []);

  const applyState = useCallback((s: AttemptState) => {
    setSt(s); setOffset(makeOffset(s.server_time)); setMsg(""); setWaiting(readQueue(attemptId).length > 0);
    if (s.finished) { clearAttempt(attemptId); localStorage.removeItem(stateKey(attemptId)); return; }
    try { localStorage.setItem(stateKey(attemptId), JSON.stringify({ s, offset: makeOffset(s.server_time) })); } catch { /* ignore */ }
    if (s.question) setValue(readDraft(attemptId, s.question.id) ?? initialValue(s.question));
  }, [attemptId]);

  const reload = useCallback(async () => {
    try { applyState(await api<AttemptState>(`/attempts/${attemptId}/`)); setOffline(false); setLoadErr(""); }
    catch (e: any) {
      if (e instanceof ApiError && e.isNetwork) {  // EDAY-06: resume from the copy kept on the phone while offline
        try { const c = JSON.parse(localStorage.getItem(stateKey(attemptId)) || ""); setSt(c.s); setOffset(c.offset); setOffline(true);
          if (c.s.question) setValue(readDraft(attemptId, c.s.question.id) ?? initialValue(c.s.question)); setWaiting(readQueue(attemptId).length > 0); return; } catch { /* nothing cached */ }
      }
      setLoadErr(e.message);
    }
  }, [attemptId, applyState]);

  /** Send queued answers to the server in order. Returns false if the network is down. */
  const flush = useCallback(async (): Promise<boolean> => {
    if (flushing.current) return false;
    flushing.current = true;
    try {
      let q = readQueue(attemptId);
      while (q.length) {
        const p = q[0];
        try {
          applyState(await api<AttemptState>(`/attempts/${attemptId}/answer/`, { body: { question_id: p.qid, response: p.response, skip: p.skip } }));
          dequeue(attemptId, p.qid); setOffline(false); setWaiting(false);
        } catch (e: any) {
          if (!(e instanceof ApiError) || e.isNetwork || e.status >= 500) { setOffline(true); return false; }
          dequeue(attemptId, p.qid);
          if (e.code === "time_over" && e.data?.finished) { applyState(e.data); return true; }
          if (e.code === "out_of_order" || e.code === "submitted") { await reload(); return true; }
          setMsg(e.message); setWaiting(false);
          return true;
        }
        q = readQueue(attemptId);
      }
      return true;
    } finally { flushing.current = false; }
  }, [attemptId, applyState, reload]);

  useEffect(() => { (async () => { await flush(); await reload(); })(); }, [flush, reload]);

  // Keep trying while offline, and the moment the phone reconnects.
  useEffect(() => {
    const go = () => { flush().then(() => { if (readQueue(attemptId).length === 0) reload(); }); };
    window.addEventListener("online", go);
    const i = offline ? setInterval(go, 4000) : undefined;
    return () => { window.removeEventListener("online", go); if (i) clearInterval(i); };
  }, [offline, flush, reload, attemptId]);

  const finishNow = useCallback(async () => {
    if (finishing.current) return;
    finishing.current = true;
    for (;;) {
      try { await flush(); applyState(await api<AttemptState>(`/attempts/${attemptId}/finish/`, { body: {} })); break; }
      catch (e: any) { if (e instanceof ApiError && !e.isNetwork && e.status < 500) { setMsg(e.message); break; } await new Promise((r) => setTimeout(r, 3000)); }
    }
    finishing.current = false;
  }, [attemptId, flush, applyState]);

  // EDAY-05: the countdown is only a display of server time; at zero we ask the server to close the attempt.
  const remainingMs = st && !st.finished ? new Date(st.deadline_at).getTime() - (now + offset) : 0;
  useEffect(() => { if (st && !st.finished && remainingMs <= 0) { setTimeOver(true); finishNow(); } }, [st, remainingMs, finishNow]);

  // EDAY-08: warnings with sound and vibration.
  useEffect(() => {
    if (!st || st.finished) return;
    for (const w of [...(st.warnings || [10, 5, 1])].sort((a, b) => b - a)) {
      if (!fired.current.has(w) && remainingMs <= w * 60_000) {
        fired.current.add(w);
        if (remainingMs > w * 60_000 - 15_000) {
          setBanner(w === 1 ? t("warn_one_minute") : t("warn_minutes", { n: w }));
          if (sound) beep();
          navigator.vibrate?.([250, 120, 250]);
          setTimeout(() => setBanner(""), 7000);
        }
      }
    }
  }, [remainingMs, st, sound, t]);

  // EDAY-11: leaving the exam screen is logged as information for staff. Copy/paste/right-click are blocked below.
  useEffect(() => {
    if (!st || st.finished) return;
    const onVis = () => { api(`/attempts/${attemptId}/event/`, { body: { kind: document.hidden ? "left_screen" : "returned" }, keepalive: true }).catch(() => {}); };
    document.addEventListener("visibilitychange", onVis);
    // EDAY-04: the back button must not take her to earlier questions or out of the exam by accident.
    history.pushState(null, "", location.href);
    const onPop = () => history.pushState(null, "", location.href);
    const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("popstate", onPop); window.addEventListener("beforeunload", onUnload);
    return () => { document.removeEventListener("visibilitychange", onVis); window.removeEventListener("popstate", onPop); window.removeEventListener("beforeunload", onUnload); };
  }, [attemptId, st?.finished, !!st]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(skip = false) {
    if (!st?.question) return;
    const q = st.question;
    if (!skip && !hasAnswer(q, value)) { setMsg(t("answer_first")); return; }
    setBusy(true); setMsg(""); setConfirm(null);
    enqueue(attemptId, { qid: q.id, response: skip ? null : value, skip });
    setWaiting(true);
    await flush();
    setBusy(false);
  }

  if (loadErr && !st) return <ErrorNote error={loadErr} retry={reload} />;
  if (!st) return <Loading />;

  /* ---- finished (EDAY-09, EDAY-10) ---- */
  if (st.finished) {
    return (
      <div className="slide-in">
        <div className="card hero center">
          <span className="big-num" aria-hidden>{st.time_over ? "⏰" : "🎉"}</span>
          <h1>{st.time_over ? t("time_over") : t("exam_submitted")}</h1>
          <p>{st.message}</p>
          <p><b>{st.results_note}</b></p>
        </div>
        {st.tips && st.tips.length > 0 && (
          <div className="card"><h2>{t("tips_title")}</h2>
            <ul className="list tips">{st.tips.map((tip, i) => <li key={i}><div className="tip-tag">{t(`tip_${tip.kind}`)}</div>{tip.text}</li>)}</ul>
          </div>
        )}
        <Link className="btn primary big" href="/">{t("back_home")}</Link>
      </div>
    );
  }

  if (timeOver) {
    return <div className="overlay fade-in-late" role="alert"><div><span className="big-num" aria-hidden>⏰</span><h1>{t("time_over")}</h1><p className="muted">{t("submitting_saved")}</p><div className="spinner" style={{ margin: "1rem auto" }} /></div></div>;
  }

  const q = st.question!;
  const total = st.total_questions, idx = st.index || 1;
  const low = remainingMs < 5 * 60_000;
  return (
    <div className="no-select" onCopy={(e) => e.preventDefault()} onCut={(e) => e.preventDefault()} onPaste={(e) => e.preventDefault()}
      onContextMenu={(e) => e.preventDefault()} onDragStart={(e) => e.preventDefault()}>
      {offline && <div className="offline-banner" role="status">📡 {t("offline_banner")}</div>}
      {banner && <div className="warn-banner" role="alert">⏳ {banner}</div>}
      <div className="exam-head">
        <div className="row">
          <div className="grow"><b>{st.title}</b><div className="small muted" aria-live="polite">{t("question_x_of_y", { x: idx, y: total })}</div></div>
          <button className="btn icon" aria-pressed={sound} aria-label={t("sound")} onClick={() => { const v = !sound; setSound(v); localStorage.setItem("amani_sound", v ? "on" : "off"); }}>{sound ? "🔔" : "🔕"}</button>
          <div className={`timer ${low ? "low" : ""}`} role="timer" aria-label={t("time_left")}>{low ? "⏳ " : ""}{clock(remainingMs)}</div>
        </div>
        <Bar value={((idx - 1) / total) * 100} label={t("progress")} />
      </div>
      <div key={q.id} className="card slide-in" style={{ marginTop: ".9rem" }}>
        <QuestionView q={q} value={value} disabled={waiting || busy}
          onChange={(v) => { setValue(v); saveDraft(attemptId, q.id, v); setMsg(""); }} />
        <div className="row" style={{ marginTop: ".6rem" }}><Listen q={q} /></div>
        {waiting && <p className="hint" role="status">💾 {offline ? t("saved_on_phone") : t("saving")}</p>}
        {msg && <p className="no" role="alert">⚠ {msg}</p>}
        <div className="row" style={{ marginTop: "1rem" }}>
          <button className="btn primary big" style={{ flex: 1 }} disabled={waiting || busy} onClick={() => submit(false)}>{t("submit_answer")}</button>
        </div>
        <div className="row" style={{ marginTop: ".6rem", justifyContent: "space-between" }}>
          {st.can_skip ? <button className="btn" disabled={waiting || busy} onClick={() => setConfirm("skip")}>{t("skip")}</button> : <span />}
          <button className="btn danger" disabled={waiting || busy} onClick={() => setConfirm("finish")}>{t("finish_exam")}</button>
        </div>
      </div>
      {confirm && (
        <Modal label={t("are_you_sure")} onClose={() => setConfirm(null)}>
          <h2>{t("are_you_sure")}</h2>
          <p>{confirm === "skip" ? t("skip_warning") : t("finish_warning")}</p>
          <div className="row">
            <button className="btn" onClick={() => setConfirm(null)}>{t("go_back")}</button>
            <button className="btn primary" onClick={() => (confirm === "skip" ? submit(true) : (setConfirm(null), finishNow()))}>{confirm === "skip" ? t("yes_skip") : t("yes_finish")}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default function ExamPage() {
  const [p, setP] = useState<{ id: string | null; attempt: string | null } | null>(null);
  useEffect(() => { const q = new URLSearchParams(location.search); setP({ id: q.get("id"), attempt: q.get("attempt") }); }, []);
  return (
    <Shell bare>
      {!p ? <Loading /> : p.attempt ? <Runner attemptId={Number(p.attempt)} /> : p.id ? <PreExam examId={Number(p.id)} /> : <Link href="/">←</Link>}
    </Shell>
  );
}
