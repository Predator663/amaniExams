/* Amani Exams service worker (NFR-02: installable, app shell cached, opens fast, tolerates short offline periods).
   Rules that must never change:
   - Anything from the API (a different address, or /api/) is NEVER cached: exam questions, results and answers
     always come live from the server, so nothing stale or private is ever kept here.
   - Pages and files of the app itself are cached so the app opens instantly and still opens with no signal. */
const VERSION = "amani-v2";
const SHELL = ["/", "/login/", "/exam/", "/results/", "/practice/", "/badges/", "/settings/", "/notifications/", "/install/", "/demo/", "/manifest.webmanifest", "/icons/icon-192.png", "/logo.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const req = event.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  // Page loads: network first (fresh app after a new release), cached copy when there is no signal.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).then((res) => { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res; })
        .catch(() => caches.match(req).then((hit) => hit || caches.match(url.pathname) || caches.match("/")))
    );
    return;
  }
  // Built files (hashed names never change) and icons: cache first. Everything else: show cached, refresh quietly.
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res; })));
    return;
  }
  event.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req).then((res) => { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res; }).catch(() => hit);
      return hit || net;
    })
  );
});

// NOT-02: Web Push (results ready, exam reminders, announcements).
self.addEventListener("push", (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (e) { d = { title: "Amani Exams", body: event.data ? event.data.text() : "" }; }
  event.waitUntil(self.registration.showNotification(d.title || "Amani Exams", {
    body: d.body || "", icon: "/icons/icon-192.png", badge: "/icons/icon-192.png", data: { url: d.url || "/notifications/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(target); return c.focus(); } }
    return self.clients.openWindow(target);
  }));
});
