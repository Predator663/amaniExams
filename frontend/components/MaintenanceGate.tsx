"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Status = { maintenance: boolean; blocked: boolean; message: string; back_at: string };

/** Full-screen "under maintenance" notice while the owner has switched the site off (Django: /controlroom/).
 *  The owner (signed in) is not blocked and only sees a thin red bar as a reminder. */
export default function MaintenanceGate() {
  const [s, setS] = useState<Status | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () => api<Status>("/site-status/").then((d) => alive && setS(d)).catch(() => {});
    check();
    const onMaint = (e: Event) => {
      const d: any = (e as CustomEvent).detail || {};
      if (alive) setS({ maintenance: true, blocked: true, message: d.message || "", back_at: d.back_at || "" });
    };
    window.addEventListener("amani:maintenance", onMaint);
    const t = setInterval(check, 30_000); // comes back by itself when the owner switches the site on again
    return () => { alive = false; clearInterval(t); window.removeEventListener("amani:maintenance", onMaint); };
  }, []);

  if (!s || !s.maintenance) return null;
  if (!s.blocked) {
    return (
      <div role="status" style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 9999, background: "#991b1b", color: "#fff", textAlign: "center", padding: ".35rem", fontSize: ".85rem" }}>
        Maintenance mode is ON: only you can see the site.
      </div>
    );
  }
  return (
    <div role="alertdialog" aria-live="assertive" style={{ position: "fixed", inset: 0, zIndex: 10000, background: "#0f172a", color: "#e2e8f0", display: "grid", placeItems: "center", padding: "1.2rem", textAlign: "center" }}>
      <div style={{ maxWidth: 520 }}>
        <div style={{ fontSize: "3.2rem" }} aria-hidden>🛠️</div>
        <h1 style={{ margin: ".3rem 0" }}>Mfumo uko kwenye matengenezo</h1>
        <p>Tunafanya maboresho kwa muda mfupi. Tafadhali jaribu tena baadaye.</p>
        <hr style={{ border: 0, borderTop: "1px solid #334155", margin: "1.2rem 0" }} />
        <h2 style={{ margin: ".3rem 0" }}>Down for maintenance</h2>
        <p>We are making improvements and will be back shortly.</p>
        {s.message && <p><b>{s.message}</b></p>}
        {s.back_at && <p style={{ color: "#fbbf24" }}>Back: {s.back_at}</p>}
      </div>
    </div>
  );
}
