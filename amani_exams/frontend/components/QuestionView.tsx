"use client";
import { ItemContent, RichHtml } from "./Rich";
import { useSession } from "@/lib/session";
import type { Question } from "@/lib/types";

/** The six auto-marked question types (QB-01). `value` is exactly what the API expects as the response. */
export function initialValue(q: Question): any {
  if (q.type === "ordering") return ((q.content?.items || []) as any[]).map((i) => i.id);
  if (q.type === "mcq_multi") return [];
  if (q.type === "matching") return {};
  if (q.type === "fill_blank") return "";
  return undefined;
}
export function hasAnswer(q: Question, v: any): boolean {
  if (q.type === "mcq_multi") return Array.isArray(v) && v.length > 0;
  if (q.type === "matching") return v && Object.keys(v).length > 0;
  if (q.type === "fill_blank") return typeof v === "string" && v.trim() !== "";
  if (q.type === "ordering") return Array.isArray(v) && v.length > 0;
  return v !== undefined && v !== null;
}

export default function QuestionView({ q, value, onChange, disabled }: { q: Question; value: any; onChange: (v: any) => void; disabled?: boolean }) {
  const { t } = useSession();
  const c = q.content || {};
  // Ordering: `value` can be undefined (builder preview) or stale (items edited). Always rebuild a valid order.
  const items: any[] = c.items || [];
  const itemIds: string[] = items.map((x: any) => x.id);
  const order: string[] = q.type === "ordering"
    ? [...(Array.isArray(value) ? (value as string[]).filter((id) => itemIds.includes(id)) : []), ...itemIds.filter((id) => !(Array.isArray(value) ? value : []).includes(id))]
    : [];
  return (
    <div className="question">
      <RichHtml html={q.prompt} className="prompt" />
      <p className="muted small">{q.marks === 1 ? t("mark_one") : t("marks_n", { n: q.marks })}</p>

      {q.type === "mcq_single" && (
        <div role="radiogroup" aria-label={t("choose_one")} className="options">
          {c.options.map((o: any) => (
            <label key={o.id} className={`opt ${value === o.id ? "on" : ""}`}>
              <input type="radio" name={`q${q.id}`} checked={value === o.id} disabled={disabled} onChange={() => onChange(o.id)} />
              <ItemContent item={o} />
            </label>
          ))}
        </div>
      )}

      {q.type === "mcq_multi" && (
        <div role="group" aria-label={t("choose_many")} className="options">
          <p className="muted small">{t("choose_many")}</p>
          {c.options.map((o: any) => {
            const on = (value || []).includes(o.id);
            return (
              <label key={o.id} className={`opt ${on ? "on" : ""}`}>
                <input type="checkbox" checked={on} disabled={disabled}
                  onChange={() => onChange(on ? value.filter((x: string) => x !== o.id) : [...(value || []), o.id])} />
                <ItemContent item={o} />
              </label>
            );
          })}
        </div>
      )}

      {q.type === "true_false" && (
        <div role="radiogroup" aria-label={t("true_or_false")} className="options row2">
          {[true, false].map((b) => (
            <label key={String(b)} className={`opt center-text ${value === b ? "on" : ""}`}>
              <input type="radio" name={`q${q.id}`} checked={value === b} disabled={disabled} onChange={() => onChange(b)} />
              <span>{b ? t("true") : t("false")}</span>
            </label>
          ))}
        </div>
      )}

      {q.type === "fill_blank" && (
        <input className="input" value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}
          aria-label={t("your_answer")} placeholder={t("type_answer")} autoComplete="off" autoCapitalize="off" spellCheck={false} inputMode="text" />
      )}

      {q.type === "matching" && (
        <div className="matching">
          <p className="muted small">{t("match_help")}</p>
          {c.left.map((l: any) => (
            <div key={l.id} className="match-row">
              <div className="match-left"><ItemContent item={l} /></div>
              <select className="input" value={(value || {})[l.id] || ""} disabled={disabled} aria-label={t("match_with")}
                onChange={(e) => onChange({ ...(value || {}), [l.id]: e.target.value })}>
                <option value="">{t("choose")}</option>
                {c.right.map((r: any) => <option key={r.id} value={r.id}>{(r.text || "").replace(/<[^>]+>/g, "") || r.alt_text || r.id}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}

      {q.type === "ordering" && (
        <ol className="ordering" aria-label={t("order_help")}>
          <p className="muted small">{t("order_help")}</p>
          {order.map((id, i) => {
            const it = items.find((x: any) => x.id === id);
            const move = (d: number) => { const n = [...order]; const j = i + d; if (j < 0 || j >= n.length) return; [n[i], n[j]] = [n[j], n[i]]; onChange(n); };
            return (
              <li key={id} className="order-row">
                <span className="num">{i + 1}</span>
                <span className="grow"><ItemContent item={it} /></span>
                <button className="btn icon" disabled={disabled || i === 0} onClick={() => move(-1)} aria-label={t("move_up")}>↑</button>
                <button className="btn icon" disabled={disabled || i === order.length - 1} onClick={() => move(1)} aria-label={t("move_down")}>↓</button>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
