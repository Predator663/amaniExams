/** Helpers for the staff screens. All dates the school types are East Africa Time (UTC+3, no daylight saving). */
export const EAT = "+03:00";
/** "2026-11-03T08:30" (typed in a datetime-local box, EAT) -> ISO string the API understands. */
export const toIso = (local: string) => (local ? `${local}:00${EAT}` : null);
/** ISO from the API -> "2026-11-03T08:30" in EAT for a datetime-local box. */
export function fromIso(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() + 3 * 3600_000);
  return d.toISOString().slice(0, 16);
}
export const plain = (html: string) => (html || "").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim();
export const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
export const unesc = (s: string) => plain(s);
export const uid = () => Math.random().toString(36).slice(2, 10);
export const QTYPES: [string, string][] = [
  ["mcq_single", "Multiple choice (one answer)"], ["mcq_multi", "Multiple choice (several answers)"], ["true_false", "True or false"],
  ["matching", "Matching"], ["fill_blank", "Fill in the blank"], ["ordering", "Ordering"],
];
export const qtypeName = (k: string) => QTYPES.find((x) => x[0] === k)?.[1] || k;
/** DRF errors come as {field: [msg]} or {detail}. Flatten to readable lines. */
export function errorLines(data: any, fallback: string): string[] {
  if (!data || typeof data !== "object") return [fallback];
  const out: string[] = [];
  const walk = (k: string, v: any) => {
    if (typeof v === "string") out.push(k && k !== "detail" ? `${k}: ${v}` : v);
    else if (Array.isArray(v)) v.forEach((x) => walk(k, x));
    else if (v && typeof v === "object") Object.entries(v).forEach(([kk, vv]) => walk(kk, vv));
  };
  Object.entries(data).forEach(([k, v]) => walk(k, v));
  return out.length ? out : [fallback];
}
