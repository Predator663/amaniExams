"use client";
/* Anti-cheat support on the student's phone (proximity check, see the Privacy policy, section "Location during exams").
 *
 * What a web app can and cannot do, honestly:
 *  - Location: navigator.geolocation. With "high accuracy" the phone's operating system fuses GNSS (GPS), Wi-Fi positioning and
 *    mobile-network positioning by itself. A web page cannot read those sources separately, it only receives the fused position
 *    and its accuracy in metres. This is the real position source.
 *  - Motion: the accelerometer through DeviceMotionEvent. It only tells whether the phone itself is being moved.
 *  - Bluetooth / Wi-Fi: browsers do not let a page scan nearby devices or Wi-Fi networks. A page can only read whether a Bluetooth
 *    adapter is available (Chrome on Android) and what kind of network is in use (Chrome on Android). Where the browser cannot tell,
 *    the student must confirm that she turned them on, and the status is reported to administrators as "unknown".
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

export type Fix = { lat: number; lng: number; accuracy: number; speed?: number | null; heading?: number | null };
export type Sensors = { perm?: string; ble?: string; net?: string; motion?: string };
export type FixError = "denied" | "unavailable" | "timeout" | "unsupported";

/** One position reading, or a short error word. */
/**
 * A random code this browser made for itself the first time (kept in its own storage; it is not a phone number, IMEI or anything
 * from the hardware). It only lets the school see if one student's exam is suddenly sent from another device.
 */
export function deviceId(): string {
  try {
    let id = localStorage.getItem("amani_device") || "";
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
      id = typeof crypto.randomUUID === "function" ? crypto.randomUUID()
        : Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
      localStorage.setItem("amani_device", id);
    }
    return id;
  } catch { return ""; }  // storage blocked: the check is simply skipped for this phone
}

export function getFix(timeoutMs = 15000, maxAgeMs = 0): Promise<Fix> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return reject("unsupported" as FixError);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy, speed: p.coords.speed, heading: p.coords.heading }),
      (e) => reject((e.code === 1 ? "denied" : e.code === 3 ? "timeout" : "unavailable") as FixError),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: maxAgeMs },
    );
  });
}

/* ---- motion: rolling spread of the acceleration over ~3 s. A phone lying on a desk has almost none. ---- */
let motionState: "unknown" | "denied" | "unsupported" | "still" | "moving" = "unknown";
let motionOn = false;
const win: number[] = [];

function onMotion(e: DeviceMotionEvent) {
  const a = e.accelerationIncludingGravity;
  if (!a || a.x == null || a.y == null || a.z == null) return;
  win.push(Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z));
  if (win.length > 45) win.shift();  // ~3 s at 15 Hz
  if (win.length < 15) return;
  const m = win.reduce((s, v) => s + v, 0) / win.length;
  const sd = Math.sqrt(win.reduce((s, v) => s + (v - m) ** 2, 0) / win.length);
  motionState = sd > 1.1 ? "moving" : "still";
}

/** Start listening. On iPhone this must run from a tap, because iOS asks the student for permission. */
export async function startMotion(): Promise<string> {
  if (typeof window === "undefined" || !("DeviceMotionEvent" in window)) return (motionState = "unsupported");
  if (motionOn) return motionState;
  try {
    const D: any = (window as any).DeviceMotionEvent;
    if (typeof D.requestPermission === "function") {
      if ((await D.requestPermission()) !== "granted") return (motionState = "denied");
    }
  } catch { return (motionState = "denied"); }
  window.addEventListener("devicemotion", onMotion);
  motionOn = true;
  return motionState === "unknown" ? "still" : motionState;
}

export async function readSensors(): Promise<Sensors> {
  const s: Sensors = { motion: motionState };
  const nav: any = typeof navigator === "undefined" ? {} : navigator;
  try { s.perm = (await nav.permissions?.query({ name: "geolocation" }))?.state ?? "unknown"; } catch { s.perm = "unknown"; }
  try { s.ble = nav.bluetooth?.getAvailability ? ((await nav.bluetooth.getAvailability()) ? "on" : "off") : "unsupported"; } catch { s.ble = "unknown"; }
  const t = nav.connection?.type;
  s.net = t === "wifi" || t === "cellular" || t === "ethernet" || t === "none" ? t : "unknown";
  return s;
}

export type ProctorState = "starting" | "ok" | "denied" | "lost";

/** While an exam attempt is running: send the position every few seconds, and tell the page when location is switched off. */
export function useProctor(attemptId: number | null, every = 6000) {
  const [state, setState] = useState<ProctorState>("starting");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [bleOff, setBleOff] = useState(false);
  const [locked, setLocked] = useState<boolean | null>(null);  // null = the server has not said yet
  const [lockReason, setLockReason] = useState<string>("");  // close | leaves | manual
  const lastMsgs = useRef(0);
  const markLocked = useCallback((reason = "") => { setLocked(true); if (reason) setLockReason(reason); }, []);
  const applyLock = useCallback((v: boolean, reason = "") => { setLocked(v); setLockReason(v ? reason : ""); }, []);
  const fails = useRef(0), stop = useRef(false), busy = useRef(false);

  const tick = useCallback(async () => {
    if (!attemptId || stop.current || busy.current) return;
    busy.current = true;
    try {
      const fix = await getFix(10000, 3000);
      fails.current = 0; setState("ok"); setAccuracy(Math.round(fix.accuracy));
      const sensors = await readSensors();
      setBleOff(sensors.ble === "off");
      try { const r = await api<{ locked?: boolean; lock_reason?: string; messages?: number }>(`/attempts/${attemptId}/location/`, { body: { ...fix, sensors, device: deviceId() } }); setLocked(!!r?.locked); setLockReason(r?.locked ? r?.lock_reason || "close" : "");
        const m = r?.messages ?? 0;
        if (m > lastMsgs.current) window.dispatchEvent(new Event("amani:messages"));  // a message from the school arrived: show its banner now
        lastMsgs.current = m; }
      catch (e) { if (e instanceof ApiError && e.code === "finished") stop.current = true; /* offline: the next report catches up */ }
    } catch (e) {
      if (e === "denied") { fails.current = 99; setState("denied"); }
      else if (++fails.current >= 4) setState("lost");  // no position for ~30 s: services off or no sky/Wi-Fi view
    } finally { busy.current = false; }
  }, [attemptId]);

  useEffect(() => {
    if (!attemptId) return;
    stop.current = false; fails.current = 0; setState("starting");
    startMotion().catch(() => {});  // works on Android / already-granted iOS; otherwise motion stays "unknown", which is fine
    tick();
    const iv = setInterval(tick, every);
    const vis = () => { if (!document.hidden) tick(); };
    document.addEventListener("visibilitychange", vis);
    return () => { stop.current = true; clearInterval(iv); document.removeEventListener("visibilitychange", vis); };
  }, [attemptId, every, tick]);

  /** `locked`: an administrator has to unlock this exam because the student sits too close to another one. The next report overrides `markLocked`. */
  return { state, accuracy, bleOff, locked, lockReason, markLocked, applyLock, retry: tick };
}
