import { API, apiBase } from "./api";

export type Diagnosis = { ok: boolean; lines: string[] };

/** Tells a person (or the developer) exactly why the app cannot reach the server. */
export async function diagnose(): Promise<Diagnosis> {
  const target = `${API}/api/i18n/en/`, lines = [`Web app address: ${location.origin}`, `Server address: ${apiBase()}`];
  if (location.protocol === "https:" && /^http:\/\//.test(API)) {
    return { ok: false, lines: [...lines, "✗ This page is secure (https) but the server address is plain http. Browsers block that. Use an https server address (NEXT_PUBLIC_API_URL)."] };
  }
  try {
    const r = await fetch(target, { cache: "no-store" });
    if (r.ok) return { ok: true, lines: [...lines, "✓ The server answered. Connection is fine."] };
    if (r.status >= 500 && !API) return { ok: false, lines: [...lines, `✗ The web app is running, but Django did not answer (error ${r.status}). Start it with: python manage.py runserver. If Django uses another port or computer, start the web app with BACKEND_URL=http://127.0.0.1:PORT npm run dev.`] };
    return { ok: false, lines: [...lines, `✗ The server answered with an error (${r.status}). ${r.status === 400 ? "Its allowed-hosts list probably does not include this address (DJANGO_ALLOWED_HOSTS)." : ""}`] };
  } catch {
    try {  // reachable but refused by CORS?  A no-cors request succeeds (opaque) whenever something is listening.
      if (API) { await fetch(target, { mode: "no-cors", cache: "no-store" }); return { ok: false, lines: [...lines, `✗ The server is running but refuses requests from ${location.origin} (CORS). On the server set CORS_ORIGINS=${location.origin}, or use npm run dev without NEXT_PUBLIC_API_URL.`] }; }
    } catch { /* falls through */ }
    return { ok: false, lines: [...lines, API ? `✗ Nothing answers at ${API}. Is the Django server running (python manage.py runserver) and is the address and port right?`
      : "✗ The web app could not reach Django. Is it running (python manage.py runserver)? If it runs on another port or computer, start the web app with BACKEND_URL=http://127.0.0.1:PORT npm run dev."] };
  }
}
