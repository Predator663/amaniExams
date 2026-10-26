"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import { dict } from "./i18n";
import type { User } from "./types";

type Ctx = {
  user: User | null; ready: boolean; lang: "en" | "sw";
  login: (u: string, p: string) => Promise<User>;
  logout: (reason?: string) => Promise<void>;
  refresh: () => Promise<void>;
  savePrefs: (patch: Record<string, any>) => Promise<void>;
  t: (key: string, vars?: Record<string, string | number>) => string;
  notice: string;
};
const C = createContext<Ctx>(null as any);
export const useSession = () => useContext(C);

const LOCAL = "amani_prefs";
type Local = { language?: "en" | "sw"; theme?: string; text_size?: number; line_spacing?: number; dyslexia_font?: boolean; reduce_motion?: boolean; hc?: "dark" | "light" };
const readLocal = (): Local => { try { return JSON.parse(localStorage.getItem(LOCAL) || "{}"); } catch { return {}; } };

/** ACC-01/02/06: put the student's choices on the page. Remembered on the phone too, so the login screen looks right. */
export function applyPrefs(p: Local) {
  const h = document.documentElement;
  h.dataset.theme = p.theme || "light";
  h.dataset.hc = p.hc || "dark";
  h.style.fontSize = `${p.text_size || 100}%`;
  h.style.setProperty("--ls", String(p.line_spacing || 1.5));
  h.classList.toggle("dyslexia", !!p.dyslexia_font);
  h.classList.toggle("reduce-motion", !!p.reduce_motion);
  h.lang = p.language || "en";
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState("");
  const [localLang, setLocalLang] = useState<"en" | "sw">("en");
  const lang = user?.language || localLang;

  const push = useCallback((u: User | null) => {
    setUser(u);
    const l = readLocal();
    if (u) {
      const merged: Local = { ...l, language: u.language, theme: u.theme, text_size: u.accessibility.text_size,
        line_spacing: u.accessibility.line_spacing, dyslexia_font: u.accessibility.dyslexia_font, reduce_motion: u.accessibility.reduce_motion };
      localStorage.setItem(LOCAL, JSON.stringify(merged));
      applyPrefs(merged);
    }
  }, []);

  useEffect(() => {
    const l = readLocal();
    applyPrefs(l);
    setLocalLang(l.language || (navigator.language?.startsWith("sw") ? "sw" : "en"));
    if (!l.reduce_motion && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) document.documentElement.classList.add("reduce-motion");
    if (!getToken()) { setReady(true); return; }
    api<User>("/me/").then(push).catch(() => {}).finally(() => setReady(true));
  }, [push]);

  const logout = useCallback(async (reason?: string) => {
    try { if (getToken()) await api("/auth/logout/", { method: "POST", body: {} }); } catch { /* already out */ }
    setToken(null); setUser(null);
    if (reason) setNotice(reason);
    if (!location.pathname.startsWith("/login")) location.href = "/login/";
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      if (!getToken()) return;
      setToken(null); setUser(null);
      sessionStorage.setItem("amani_notice", dict[lang].session_ended);  // AUTH-09: logged in on another device
      if (!location.pathname.startsWith("/login")) location.href = "/login/";
    };
    const onMust = () => { if (!location.pathname.startsWith("/change-password")) location.href = "/change-password/"; };
    window.addEventListener("amani:unauthorized", onUnauthorized);
    window.addEventListener("amani:must-change-password", onMust);
    return () => { window.removeEventListener("amani:unauthorized", onUnauthorized); window.removeEventListener("amani:must-change-password", onMust); };
  }, [lang]);

  const value = useMemo<Ctx>(() => ({
    user, ready, lang, notice,
    login: async (username, password) => {
      const r = await api<{ token: string; user: User }>("/auth/login/", { body: { username, password }, auth: false });
      setToken(r.token); push(r.user); return r.user;
    },
    logout,
    refresh: async () => { push(await api<User>("/me/")); },
    savePrefs: async (patch) => {
      const l = readLocal();
      if ("hc" in patch) { localStorage.setItem(LOCAL, JSON.stringify({ ...l, hc: patch.hc })); applyPrefs({ ...l, hc: patch.hc, ...user && { theme: user.theme } }); delete patch.hc; }
      if (Object.keys(patch).length === 0) return;
      if (!user) { const m = { ...l, ...patch }; localStorage.setItem(LOCAL, JSON.stringify(m)); applyPrefs(m); if (patch.language) setLocalLang(patch.language); return; }
      push(await api<User>("/me/", { method: "PATCH", body: patch }));
    },
    t: (key, vars) => {
      let s = dict[lang][key] ?? dict.en[key] ?? key;
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
      return s;
    },
  }), [user, ready, lang, notice, logout, push]);

  return <C.Provider value={value}>{children}</C.Provider>;
}
