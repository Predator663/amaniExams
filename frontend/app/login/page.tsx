"use client";
import { FormEvent, useEffect, useState } from "react";
import { useSession } from "@/lib/session";
import { Loading } from "@/components/ui";
import { diagnose, Diagnosis } from "@/lib/diagnose";
import Footer from "@/components/Footer";
import Logo from "@/components/Logo";

/** AUTH-01, AUTH-10: big inputs, show-password, friendly errors. */
export default function Login() {
  const { login, user, ready, t, lang, savePrefs } = useSession();
  const [u, setU] = useState(""), [p, setP] = useState(""), [show, setShow] = useState(false);
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false), [note, setNote] = useState(""), [diag, setDiag] = useState<Diagnosis | null>(null), [testing, setTesting] = useState(false);
  useEffect(() => { setNote(sessionStorage.getItem("amani_notice") || ""); sessionStorage.removeItem("amani_notice"); }, []);
  useEffect(() => { if (ready && user) location.replace(user.must_change_password ? "/change-password/" : "/"); }, [ready, user]);
  if (!ready) return <Loading />;

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const me = await login(u.trim(), p);
      location.replace(me.must_change_password ? "/change-password/" : "/");
    } catch (x: any) { setErr(x.message + (x.status ? ` (HTTP ${x.status})` : "")); setBusy(false); }
  }
  return (
    <div className="login-split">
      <div className="login-art" aria-hidden="true"><Logo size={150} /><h2>{t("app_name")}</h2><p>Amani Girls Secondary School</p><p>{t("login_sub")}</p></div>
      <div className="login-wrap"><div className="login-stack">
      <form className="card login" onSubmit={submit}>
        <div className="center"><Logo size={96} label="Amani Girls Secondary School" /><h1>{t("app_name")}</h1><p className="muted">{t("login_sub")}</p></div>
        {note && <p className="hint" role="status">{note}</p>}
        <label className="field"><span>{t("username")}</span>
          <input className="input" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoCapitalize="none" autoCorrect="off" required /></label>
        <label className="field"><span>{t("password")}</span>
          <input className="input" type={show ? "text" : "password"} value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
        <label className="switch"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> {t("show_password")}</label>
        {err && <p className="no" role="alert">⚠ {err}</p>}
        {err.startsWith("Cannot reach") && <button type="button" className="btn" onClick={async () => { setTesting(true); setDiag(await diagnose()); setTesting(false); }}>{testing ? t("loading") : t("test_connection")}</button>}
        {diag && <div className={`hint ${diag.ok ? "ok" : ""}`} role="status">{diag.lines.map((l, i) => <p key={i} style={{ margin: ".2rem 0" }}>{l}</p>)}</div>}
        <button className="btn primary big" disabled={busy || !u || !p}>{busy ? t("loading") : t("log_in")}</button>
        <p className="center-text"><button type="button" className="btn" onClick={() => savePrefs({ language: lang === "en" ? "sw" : "en" })}>{lang === "en" ? "Kiswahili" : "English"}</button></p>
      </form>
      <Footer compact />
      </div></div>
    </div>
  );
}
