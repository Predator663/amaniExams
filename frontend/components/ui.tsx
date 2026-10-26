"use client";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";

export function Loading({ label }: { label?: string }) {
  const { t } = useSession();
  return <div className="center muted" role="status" aria-live="polite"><div className="spinner" aria-hidden />{label || t("loading")}</div>;
}
export function ErrorNote({ error, retry }: { error: string; retry?: () => void }) {
  const { t } = useSession();
  return (
    <div className="card error" role="alert">
      <p>⚠ {error}</p>
      {retry && <button className="btn" onClick={retry}>{t("try_again")}</button>}
    </div>
  );
}
export function Bar({ value, label }: { value: number; label?: string }) {
  const v = Math.max(0, Math.min(100, value));
  return <div className="bar" role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={label}><i style={{ width: `${v}%` }} /></div>;
}
export function Modal({ children, onClose, label }: { children: ReactNode; onClose?: () => void; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} ref={ref}
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.key === "Escape" && onClose?.()}>
        {children}
      </div>
    </div>
  );
}

/** Load data once (and again on retry). Keeps friendly error text. */
export function useLoad<T>(fn: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [err, setErr] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const run = useCallback(() => {
    setLoading(true); setError(""); setErr(null);
    fn().then(setData).catch((e) => { setError(e.message || "Error"); setErr(e); }).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { data, error, err, loading, reload: run, setData };
}

/** Read ?id=5 style values (static export has no dynamic routes). */
export function useQuery(name: string): string | null {
  const [v, setV] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  useEffect(() => { setV(new URLSearchParams(location.search).get(name)); setOk(true); }, [name]);
  return ok ? v : null;
}

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), intervalMs); return () => clearInterval(i); }, [intervalMs]);
  return now;
}

/** A button that opens a small menu (user menu, language). Closes on outside click, Escape and after a choice. */
export function Dropdown({ button, children, label, align = "right" }: { button: ReactNode; children: ReactNode; label: string; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent | TouchEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", down); document.addEventListener("touchstart", down); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("touchstart", down); document.removeEventListener("keydown", key); };
  }, [open]);
  return (
    <div className="dd" ref={ref}>
      <button type="button" className="dd-btn" aria-haspopup="menu" aria-expanded={open} aria-label={label} onClick={() => setOpen(!open)}>{button}</button>
      {open && <div className={`dd-menu ${align}`} role="menu" onClick={() => setOpen(false)}>{children}</div>}
    </div>
  );
}

/** Underlined tab bar with arrow-key support. Replaces the old chip rows. */
export function Tabs({ tabs, value, onChange }: { tabs: string[][]; value: string; onChange: (k: string) => void }) {
  const move = (e: React.KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = tabs[(i + d + tabs.length) % tabs.length][0];
    onChange(n);
    setTimeout(() => (document.getElementById(`tab-${n}`) as HTMLElement | null)?.focus(), 0);
  };
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([k, l], i) => (
        <button key={k} id={`tab-${k}`} type="button" role="tab" aria-selected={value === k} tabIndex={value === k ? 0 : -1}
          className={`tab ${value === k ? "on" : ""}`} onClick={() => onChange(k)} onKeyDown={(e) => move(e, i)}>{l}</button>
      ))}
    </div>
  );
}

/** Number that counts up to its value (skipped for people who asked for less motion). */
export function CountUp({ to, ms = 900, suffix = "" }: { to: number; ms?: number; suffix?: string }) {
  const [v, setV] = useState(to);
  useEffect(() => {
    const calm = document.documentElement.classList.contains("reduce-motion") || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm || !to) { setV(to); return; }
    let raf = 0; const t0 = performance.now();
    const step = (t: number) => { const p = Math.min(1, (t - t0) / ms); setV(Math.round(to * (1 - Math.pow(1 - p, 3)))); if (p < 1) raf = requestAnimationFrame(step); };
    setV(0); raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [to, ms]);
  return <>{v}{suffix}</>;
}

/** A short burst of confetti for good news. Pure CSS, removes itself, never blocks taps. */
export function Confetti({ n = 34, once }: { n?: number; once?: string }) {
  const [on, setOn] = useState(true);
  useEffect(() => {
    if (once) { try { if (sessionStorage.getItem(`confetti-${once}`)) { setOn(false); return; } sessionStorage.setItem(`confetti-${once}`, "1"); } catch { /* private mode: just show it */ } }
    const t = setTimeout(() => setOn(false), 5200); return () => clearTimeout(t);
  }, [once]);
  const [bits] = useState(() => Array.from({ length: n }, (_, i) => ({
    left: `${Math.round(Math.random() * 100)}%`, x: `${Math.round(Math.random() * 160 - 80)}px`, r: `${Math.round(360 + Math.random() * 540)}deg`,
    d: `${(2.4 + Math.random() * 2).toFixed(2)}s`, delay: `${(Math.random() * 0.9).toFixed(2)}s`, c: ["#0b6b4f", "#f5b301", "#e84a5f", "#2b8bd8", "#7a1a2e", "#34c38f"][i % 6],
  })));
  if (!on) return null;
  return <div className="confetti" aria-hidden>{bits.map((b, i) => <i key={i} style={{ left: b.left, background: b.c, ["--x" as any]: b.x, ["--r" as any]: b.r, ["--d" as any]: b.d, ["--delay" as any]: b.delay }} />)}</div>;
}
