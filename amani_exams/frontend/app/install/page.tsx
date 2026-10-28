"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { useSession } from "@/lib/session";

/** HOME-05: how to install the app on Android and iPhone. */
export default function Install() {
  const { t } = useSession();
  const [evt, setEvt] = useState<any>(null), [done, setDone] = useState(false);
  useEffect(() => {
    setEvt((window as any).__installPrompt || null);
    const h = (e: any) => { e.preventDefault(); (window as any).__installPrompt = e; setEvt(e); };
    window.addEventListener("beforeinstallprompt", h);
    setDone(window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone === true);
    return () => window.removeEventListener("beforeinstallprompt", h);
  }, []);
  return (
    <Shell title={t("install_app")}>
      {done && <p className="hint ok" role="status">✓ {t("already_installed")}</p>}
      <p>{t("install_intro")}</p>
      {evt && <button className="btn primary big" onClick={async () => { evt.prompt(); await evt.userChoice; setEvt(null); }}>📲 {t("install_now")}</button>}
      <div className="card"><h2>🤖 Android (Chrome)</h2>
        <ol><li>{t("and_1")}</li><li>{t("and_2")}</li><li>{t("and_3")}</li></ol></div>
      <div className="card"><h2>🍎 iPhone (Safari)</h2>
        <ol><li>{t("ios_1")}</li><li>{t("ios_2")}</li><li>{t("ios_3")}</li></ol>
        <p className="muted small">{t("ios_note")}</p></div>
      <div className="card"><h2>💻 {t("computer")}</h2><p>{t("desktop_install")}</p></div>
    </Shell>
  );
}
