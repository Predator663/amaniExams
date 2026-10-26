"use client";
import { FormEvent, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

/** AUTH-05: on first login the student must choose a new password. */
export default function ChangePassword() {
  const { user, refresh, t } = useSession();
  const [o, setO] = useState(""), [n, setN] = useState(""), [n2, setN2] = useState(""), [show, setShow] = useState(false);
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr("");
    if (n !== n2) return setErr(t("passwords_differ"));
    setBusy(true);
    try { await api("/auth/change-password/", { body: { old_password: o, new_password: n } }); await refresh(); location.replace("/"); }
    catch (x: any) { setErr(x.message); setBusy(false); }
  }
  return (
    <Shell bare title={user?.must_change_password ? t("choose_new_password") : t("change_password")}>
      {user?.must_change_password && <p className="hint">{t("first_login_hint")}</p>}
      <form className="card" onSubmit={submit}>
        <label className="field"><span>{t("current_password")}</span><input className="input" type={show ? "text" : "password"} value={o} onChange={(e) => setO(e.target.value)} autoComplete="current-password" required /></label>
        <label className="field"><span>{t("new_password")}</span><input className="input" type={show ? "text" : "password"} value={n} onChange={(e) => setN(e.target.value)} autoComplete="new-password" required minLength={8} /></label>
        <label className="field"><span>{t("repeat_password")}</span><input className="input" type={show ? "text" : "password"} value={n2} onChange={(e) => setN2(e.target.value)} autoComplete="new-password" required /></label>
        <p className="muted small">{t("password_rules")}</p>
        <label className="switch"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> {t("show_password")}</label>
        {err && <p className="no" role="alert">⚠ {err}</p>}
        <button className="btn primary big" disabled={busy}>{t("save")}</button>
      </form>
    </Shell>
  );
}
