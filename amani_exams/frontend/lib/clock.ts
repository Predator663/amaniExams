/** BR-03: the server owns the clock. We only measure how far this phone is from the server and display the difference. */
export function makeOffset(serverTimeIso: string): number {
  return new Date(serverTimeIso).getTime() - Date.now();
}
export const serverNow = (offset: number) => Date.now() + offset;
export function pad(n: number) { return String(Math.floor(n)).padStart(2, "0"); }
export function clock(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}
export function eatDate(iso: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }, lang = "en") {
  return new Intl.DateTimeFormat(lang === "sw" ? "sw-TZ" : "en-GB", { timeZone: "Africa/Dar_es_Salaam", ...opts }).format(new Date(iso));
}
