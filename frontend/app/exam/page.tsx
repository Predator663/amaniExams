"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Listen from "@/components/Listen";
import QuestionView, { hasAnswer, initialValue } from "@/components/QuestionView";
import ResultsWaiting from "@/components/ResultsWaiting";
import Shell from "@/components/Shell";
import { Bar, ErrorNote, Loading, Modal, useLoad, useNow } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { clock, eatDate, makeOffset } from "@/lib/clock";
import { clearAttempt, dequeue, enqueue, readDraft, readQueue, saveDraft } from "@/lib/offlineQueue";
import { getFix, readSensors, startMotion, useProctor, type Fix, type FixError, type Sensors, deviceId } from "@/lib/proctor";
import { useSession } from "@/lib/session";
import type { AttemptState, ExamCard } from "@/lib/types";

/* ------------------------------------------------------------------ pre-exam screen (EDAY-01, EDAY-02) */
function PreExam({ examId }: { examId: number }) {
  const { t, lang } = useSession();
  const { data, error, loading, reload } = useLoad(() => api<ExamCard[]>("/student/exams/"), [examId]);
  const [agree, setAgree] = useState(false), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [legal, setLegal] = useState(false), [confirmWb, setConfirmWb] = useState(false);
  const [chk, setChk] = useState<{ busy: boolean; fix?: Fix; err?: FixError; sensors?: Sensors; done: boolean }>({ busy: false, done: false });
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

  /** Anti-cheat device check: location is verified for real (a position must come back); Wi-Fi and Bluetooth are confirmed
      by the student where the browser cannot tell. See lib/proctor.ts for what a web page can and cannot read. */
  async function checkDevice() {
    setChk({ busy: true, done: false }); setErr("");
    await startMotion().catch(() => {});  // on iPhone this is the moment iOS asks for motion permission (needs a tap)
    const sensors = await readSensors();
    try { const fix = await getFix(20000); setChk({ busy: false, done: true, fix, sensors }); }
    catch (e: any) { setChk({ busy: false, done: true, err: e as FixError, sensors }); }
  }

  async function start() {
    setErr(""); setBusy(true);
    try {
      const fix = await getFix(20000);  // a fresh position at the moment she starts proves Location is on
      const sensors = await readSensors();
      const st = await api<AttemptState>(`/student/exams/${examId}/start/`, { body: { agree_rules: true, accept_legal: true, location: fix, sensors, device: deviceId() } });
      location.replace(`/exam/?attempt=${st.attempt_id}`);
    } catch (e: any) {
      setErr(typeof e === "string" ? t(`dev_loc_${e}`) : e.message); setChk((c) => ({ ...c, fix: undefined, err: typeof e === "string" ? e as FixError : c.err, done: true })); setBusy(false);
    }
  }

  const bleOff = chk.sensors?.ble === "off";
  const locOk = !!chk.fix && !chk.err;
  const ready = agree && legal && locOk && confirmWb && !bleOff;
  const legalText = t("legal_accept").split(/(\{terms\}|\{privacy\})/).map((part, i) =>
    part === "{terms}" ? <a key={i} href="/terms/" target="_blank" rel="noopener">{t("foot_terms")}</a>
      : part === "{privacy}" ? <a key={i} href="/privacy/" target="_blank" rel="noopener">{t("foot_privacy")}</a> : part);

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
          <section className="dev-check" aria-labelledby="dev-h">
            <h2 id="dev-h">📍 {t("dev_title")}</h2>
            <p className="muted small">{t("dev_intro")}</p>
            <ul className="dev-list">
              <li className={locOk ? "ok" : chk.err ? "bad" : ""}><b>{t("dev_location")}</b><span>
                {locOk ? t("dev_loc_ok", { n: Math.round(chk.fix!.accuracy) }) : chk.err ? t(`dev_loc_${chk.err}`) : t("dev_loc_idle")}</span></li>
              <li className={chk.sensors?.net === "wifi" ? "ok" : ""}><b>{t("dev_wifi")}</b><span>{chk.sensors?.net === "wifi" ? t("dev_wifi_net") : t("dev_unknown")}</span></li>
              <li className={chk.sensors?.ble === "on" ? "ok" : bleOff ? "bad" : ""}><b>{t("dev_bt")}</b><span>
                {chk.sensors?.ble === "on" ? t("dev_bt_on") : bleOff ? t("dev_bt_off") : t("dev_unknown")}</span></li>
              <li><b>{t("dev_motion")}</b><span>{chk.sensors && (chk.sensors.motion === "still" || chk.sensors.motion === "moving") ? t("dev_motion_ok") : t("dev_motion_na")}</span></li>
            </ul>
            <button className="btn" disabled={chk.busy || busy} onClick={checkDevice}>{chk.busy ? t("dev_checking") : t("dev_check")}</button>
            <label className="switch"><input type="checkbox" checked={confirmWb} onChange={(e) => setConfirmWb(e.target.checked)} /> {t("dev_confirm")}</label>
          </section>
          <label className="switch"><input type="checkbox" checked={legal} onChange={(e) => setLegal(e.target.checked)} /> <span>{legalText}</span></label>
          {!started && <p className="center-text" role="timer"><span className="muted">{t("starts_in")}</span><span className="big-num" style={{ display: "block" }}>{clock(diff)}</span></p>}
          {err && <p className="no" role="alert">⚠ {err}</p>}
          {started && !ready && <p className="muted small" role="status">{t("dev_need_all")}</p>}
          <button className="btn primary big" disabled={!started || !ready || busy} onClick={start}>{busy ? t("loading") : t("start")}</button>
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
  const proctor = useProctor(st && !st.finished ? attemptId : null);  // sends the position every few seconds while the exam runs
  const { markLocked, applyLock } = proctor;
  const locked = proctor.locked ?? !!st?.locked;  // too close to another student, left the screen too often, or locked by hand: an administrator must unlock; the clock keeps running
  const lockReason = proctor.lockReason || st?.lock_reason || "close";  // close | leaves | manual
  const [leaveMsg, setLeaveMsg] = useState("");

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
          if (e.code === "locked") { markLocked(); return false; }  // keep the answer on the phone; it is sent again after the unlock
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
  }, [attemptId, applyState, reload, markLocked]);

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

  // When an administrator unlocks the exam: send any answer that was waiting, then fetch the current question.
  const wasLocked = useRef(false);
  useEffect(() => {
    if (wasLocked.current && !locked) flush().then(() => reload());
    wasLocked.current = locked;
  }, [locked, flush, reload]);

  // The server withholds the question while locked; if the screen is not locked but has no question yet, fetch it.
  useEffect(() => {
    if (st && !st.finished && !st.question && !locked) reload();
  }, [st, locked, reload]);

  // While locked, ask the server every few seconds whether an administrator has unlocked us (works even if location reports are off).
  useEffect(() => {
    if (!locked || !attemptId) return;
    const iv = setInterval(async () => {
      try { const s = await api<AttemptState>(`/attempts/${attemptId}/`); if (s && !s.locked) { applyLock(false); setLeaveMsg(""); } } catch { /* offline: try again */ }
    }, 5000);
    return () => clearInterval(iv);
  }, [locked, attemptId, applyLock]);

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
    // The server counts every exit. Over the allowed number it locks the exam and says so in the reply; the reply also tells
    // her how many exits she has used, so she is warned before the lock and not only after it.
    // Hidden tab, minimised app and (as extra signals) the window losing focus or being hidden: split-screen and floating windows do
    // not always fire visibilitychange. `away` makes sure each exit is reported once, and a short delay on blur ignores a blink.
    let away = false, blurTimer: ReturnType<typeof setTimeout> | undefined;
    const send = (kind: "left_screen" | "returned") => {
      if ((kind === "left_screen") === away) return;  // already reported
      away = kind === "left_screen";
      api<{ locked?: boolean; lock_reason?: string; left?: number; limit?: number; auto_lock?: boolean }>(`/attempts/${attemptId}/event/`, { body: { kind }, keepalive: true })
        .then((r) => {
          if (!r) return;
          if (r.locked) { markLocked(r.lock_reason || "leaves"); setLeaveMsg(""); return; }
          if (r.auto_lock && (r.left ?? 0) > 0 && !document.hidden) {
            const n = r.left ?? 0, max = r.limit ?? 3;
            setLeaveMsg(n >= max ? t("leave_warn_last", { n }) : t("leave_warn", { n, max }));
          }
        }).catch(() => {});
    };
    const onVis = () => send(document.hidden ? "left_screen" : "returned");
    const onBlur = () => { clearTimeout(blurTimer); blurTimer = setTimeout(() => { if (!document.hasFocus()) send("left_screen"); }, 1500); };
    const onFocus = () => { clearTimeout(blurTimer); if (!document.hidden) send("returned"); };
    const onHide = () => send("left_screen");
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("blur", onBlur); window.addEventListener("focus", onFocus); window.addEventListener("pagehide", onHide);
    // EDAY-04: the back button must not take her to earlier questions or out of the exam by accident.
    history.pushState(null, "", location.href);
    const onPop = () => history.pushState(null, "", location.href);
    const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("popstate", onPop); window.addEventListener("beforeunload", onUnload);
    return () => { clearTimeout(blurTimer); document.removeEventListener("visibilitychange", onVis); window.removeEventListener("blur", onBlur); window.removeEventListener("focus", onFocus); window.removeEventListener("pagehide", onHide); window.removeEventListener("popstate", onPop); window.removeEventListener("beforeunload", onUnload); };
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
        </div>
        {st.results_at && <ResultsWaiting attemptId={st.attempt_id} title={st.title} resultsAt={st.results_at} serverTime={st.server_time} />}
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

  const q = st.question as NonNullable<typeof st.question>;  // null while locked: the server withholds the question text
  const total = st.total_questions, idx = st.index || 1;
  const low = remainingMs < 5 * 60_000;
  if (proctor.state === "denied" || proctor.state === "lost") {
    // Location was switched off: the question is hidden until it is back. The timer keeps running on the server.
    return (
      <div className="overlay" role="alertdialog" aria-labelledby="loc-h"><div>
        <span className="big-num" aria-hidden>📍</span>
        <h1 id="loc-h">{t("loc_lost_title")}</h1>
        <p>{proctor.state === "denied" ? t("loc_denied_body") : t("loc_lost_body")}</p>
        <p className={`timer ${low ? "low" : ""}`} role="timer" aria-label={t("time_left")}>{clock(remainingMs)}</p>
        <button className="btn primary big" onClick={() => proctor.retry()}>{t("loc_retry")}</button>
      </div></div>
    );
  }
  if (locked) {
    // Sitting too close to another student: the question is hidden until an administrator unlocks. The timer keeps running on the server.
    return (
      <div className="overlay lock-overlay" role="alertdialog" aria-labelledby="lock-h" aria-describedby="lock-b"><div>
        <div className="lock-banner" role="alert"><span aria-hidden>⚠️</span> {t(lockReason === "leaves" ? "lock_banner_leaves" : lockReason === "manual" ? "lock_banner_manual" : "lock_banner")}</div>
        <span className="big-num" aria-hidden>🔒</span>
        <h1 id="lock-h">{t("lock_title")}</h1>
        <p id="lock-b">{t(lockReason === "leaves" ? "lock_body_leaves" : lockReason === "manual" ? "lock_body_manual" : "lock_body")}</p>
        <p className={`timer ${low ? "low" : ""}`} role="timer" aria-label={t("time_left")}>{clock(remainingMs)}</p>
        <p className="muted small" role="status">{t("lock_wait")}</p>
      </div></div>
    );
  }
  if (!st.question) return <Loading />;  // the question is fetched again by the effect above
  return (
    <div className="no-select" onCopy={(e) => e.preventDefault()} onCut={(e) => e.preventDefault()} onPaste={(e) => e.preventDefault()}
      onContextMenu={(e) => e.preventDefault()} onDragStart={(e) => e.preventDefault()}>
      {offline && <div className="offline-banner" role="status">📡 {t("offline_banner")}</div>}
      {banner && <div className="warn-banner" role="alert">⏳ {banner}</div>}
      {leaveMsg && <div className="warn-banner leave-banner" role="alert">⚠️ {leaveMsg} <button className="btn small" onClick={() => setLeaveMsg("")}>OK</button></div>}
      {proctor.bleOff && <div className="offline-banner" role="status">📶 {t("bt_warn")}</div>}
      <div className="exam-head">
        <div className="row">
          <div className="grow"><b>{st.title}</b><div className="small muted" aria-live="polite">{t("question_x_of_y", { x: idx, y: total })} · <span title={proctor.accuracy ? `±${proctor.accuracy} m` : ""}>📍 {t("loc_on")}</span></div></div>
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
