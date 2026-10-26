import type { Question } from "./types";

const plain = (s?: string) => (s || "").replace(/<[^>]+>/g, "").trim();
const label = (o: any) => plain(o?.text) || (o?.alt_text ? `[${o.alt_text}]` : String(o?.id ?? ""));

/** Turn a stored response or answer into words a student can read (review mode and practice feedback). */
export function describe(type: Question["type"], content: any, a: any, t: (k: string) => string): string {
  if (a === null || a === undefined || a === "" || (Array.isArray(a) && !a.length)) return "—";
  const find = (list: any[], id: string) => label(list.find((x) => x.id === id) || { id });
  switch (type) {
    case "mcq_single": return find(content.options, typeof a === "object" ? a.correct : a);
    case "mcq_multi": return (Array.isArray(a) ? a : a.correct).map((id: string) => find(content.options, id)).join(", ");
    case "true_false": { const v = typeof a === "object" ? a.correct : a; return v === true || v === "true" ? t("true") : t("false"); }
    case "fill_blank": return typeof a === "object" ? [...(a.accepted || []), ...(a.numeric ? [String(a.numeric.value)] : [])].join(" / ") : String(a);
    case "matching": { const pairs = a.pairs || a; return content.left.map((l: any) => `${label(l)} → ${pairs[l.id] ? find(content.right, pairs[l.id]) : "—"}`).join("; "); }
    case "ordering": return (a.order || a).map((id: string, i: number) => `${i + 1}. ${find(content.items, id)}`).join("  ");
  }
  return "";
}
