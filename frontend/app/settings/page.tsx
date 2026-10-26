"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import A11yPanel from "@/components/A11yPanel";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { AVATAR_EMOJI } from "@/lib/emoji";
import { useSession } from "@/lib/session";

function b64(s: string) {
  const pad = "=".repeat((4 - (s.length % 4)) % 4), raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

/** NOT-02: Web Push for installed PWAs (Android, and iPhone with iOS 16.4+ once added to the home screen). */
function PushToggle() {
  const { t } = useSession();
  const [state, setState] = useState<"unknown" | "on" | "off" | "unsupported" | "ios-install">("unknown"), [msg, setMsg] = useState("");
  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        const ios = /iPhone|iPad/.test(navigator.userAgent);
        return setState(ios && !(navigator as any).standalone ? "ios-install" : "unsupported");
      }
      const reg = await navigator.serviceWorker.ready;
      setState((await reg.pushManager.getSubscription()) ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);
  async function toggle() {
    setMsg("");
    try {
      const reg = await navigator.serviceWorker.ready;
      const existing = await reg.pushManager.getSubscription();
      if (existing) { await api("/push/unsubscribe/", { body: { endpoint: existing.endpoint } }); await existing.unsubscribe(); return setState("off"); }
      const { public_key } = await api<{ public_key: string | null }>("/push/public-key/");
      if (!public_key) return setMsg(t("push_not_ready"));
      if ((await Notification.requestPermission()) !== "granted") return setMsg(t("push_denied"));
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(public_key) });
      const j = sub.toJSON();
      await api("/push/subscribe/", { body: { endpoint: j.endpoint, keys: j.keys } });
      setState("on");
    } catch (e: any) { setMsg(e.message || t("push_not_ready")); }
  }
  if (state === "unknown") return null;
  if (state === "unsupported") return <p className="muted small">{t("push_unsupported")}</p>;
  if (state === "ios-install") return <p className="hint">{t("push_ios")}</p>;
  return <><button className="btn" onClick={toggle}>{state === "on" ? `🔕 ${t("push_off")}` : `🔔 ${t("push_on")}`}</button>{msg && <p className="no" role="alert">{msg}</p>}</>;
}

export default function Settings() {
  const { user, t, lang, savePrefs, logout } = useSession();
  const [prof, setProf] = useState<any>(null), [name, setName] = useState(""), [saved, setSaved] = useState("");
  useEffect(() => { if (user?.role === "student") api("/gamification/profile/").then((p) => { setProf(p); setName(p.display_name); }).catch(() => {}); }, [user]);
  const patch = async (b: any) => { try { setProf(await api("/gamification/profile/", { method: "PATCH", body: b })); setSaved(t("saved")); setTimeout(() => setSaved(""), 2000); } catch (e: any) { setSaved(e.message); } };
  return (
    <Shell title={t("nav_more")}>
      <div className="card"><b>{user?.first_name} {user?.last_name}</b><br /><span className="muted">@{user?.username}{user?.class ? ` · ${user.class}` : ""}</span></div>

      <div className="card"><h2>{t("language")}</h2>
        <div className="chips">{(["en", "sw"] as const).map((l) => <label key={l} className={`chip ${lang === l ? "on" : ""}`}><input type="radio" name="lang" checked={lang === l} onChange={() => savePrefs({ language: l })} />{lang === l ? "✓ " : ""}{l === "en" ? "English" : "Kiswahili"}</label>)}</div>
      </div>

      <div className="card"><h2>{t("accessibility")}</h2><A11yPanel /></div>

      {prof && (
        <div className="card"><h2>{t("my_profile")}</h2>
          <fieldset><legend>{t("avatar")}</legend>
            <div className="chips">{prof.avatars.map((a: string) => <label key={a} className={`chip ${prof.avatar === a ? "on" : ""}`}><input type="radio" name="avatar" checked={prof.avatar === a} onChange={() => patch({ avatar: a })} aria-label={a} /><span aria-hidden style={{ fontSize: "1.4rem" }}>{AVATAR_EMOJI[a]}</span></label>)}</div>
          </fieldset>
          <label className="field"><span>{t("display_name")}</span><input className="input" value={name} maxLength={30} onChange={(e) => setName(e.target.value)} onBlur={() => name !== prof.display_name && patch({ display_name: name })} placeholder={t("display_name_hint")} /></label>
          <label className="switch"><input type="checkbox" checked={prof.hide_from_leaderboard} onChange={(e) => patch({ hide_from_leaderboard: e.target.checked })} /> {t("hide_leaderboard")}</label>
          {saved && <p className="ok" role="status">{saved}</p>}
        </div>
      )}

      <div className="card"><h2>{t("notifications")}</h2><PushToggle /></div>

      <div className="grid2">
        <Link className="btn" href="/install/">📲 {t("install_app")}</Link>
        <Link className="btn" href="/change-password/">🔑 {t("change_password")}</Link>
        <Link className="btn" href="/progress/">📈 {t("my_analytics")}</Link>
        <Link className="btn" href="/leaderboard/">🏆 {t("leaderboard")}</Link>
      </div>
      <p><button className="btn danger big" onClick={() => logout()}>{t("log_out")}</button></p>
    </Shell>
  );
}
