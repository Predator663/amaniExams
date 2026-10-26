"use client";
import { useEffect } from "react";

/** NFR-02: registers the service worker (app shell cache, push). */
export default function SwRegister() {
  useEffect(() => {
    const keep = (e: any) => { e.preventDefault(); (window as any).__installPrompt = e; };
    window.addEventListener("beforeinstallprompt", keep);
    if ("serviceWorker" in navigator && location.protocol !== "file:") {
      if (process.env.NODE_ENV === "development") {
        // npm run dev: file names are not hashed, so a cache-first worker would keep serving OLD code after every edit.
        navigator.serviceWorker.getRegistrations().then((rs) => rs.forEach((r) => r.unregister())).catch(() => {});
        if ("caches" in window) caches.keys().then((ks) => ks.forEach((k) => caches.delete(k))).catch(() => {});
      } else {
        navigator.serviceWorker.register("/sw.js").catch(() => {});
      }
    }
    return () => window.removeEventListener("beforeinstallprompt", keep);
  }, []);
  return null;
}
