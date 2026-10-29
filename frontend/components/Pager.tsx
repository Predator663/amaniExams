"use client";
import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

/** Props every list passes to <Pager>. The hooks below build them. */
export type PagerProps = { page: number; pages: number; count: number; size: number; onPage: (p: number) => void; onSize?: (n: number) => void; busy?: boolean };

export const SIZES = [10, 20, 50];

/** Page buttons for any list: Prev, 1 … 4 5 6 … 20, Next, "Showing 21–40 of 312", and an optional "per page" box.
 *  It only moves the list: the page itself is never reloaded. */
export function Pager({ page, pages, count, size, onPage, onSize, busy }: PagerProps) {
  const { t } = useSession();
  const small = count <= Math.min(...SIZES);
  if (pages <= 1 && (!onSize || small)) return null;
  const set = new Set([1, pages, page - 1, page, page + 1]);
  const nums = [...set].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  nums.forEach((n, i) => { if (i && n - nums[i - 1] > 1) out.push("…"); out.push(n); });
  const a = count ? (page - 1) * size + 1 : 0, b = Math.min(count, page * size);
  return (
    <div className="pager-wrap" aria-busy={busy || undefined}>
      <p className="muted small pager-count" aria-live="polite">{t("pg_showing", { a, b, n: count })}</p>
      <nav className="pager" aria-label={t("pg_pages")}>
        <button type="button" className="btn" disabled={page <= 1 || busy} onClick={() => onPage(page - 1)} aria-label={t("pg_prev")}>‹ {t("pg_prev")}</button>
        {out.map((n, i) => n === "…"
          ? <span key={`e${i}`} className="muted" aria-hidden>…</span>
          : <button type="button" key={n} className={`btn pg ${n === page ? "primary" : ""}`} disabled={busy && n !== page} aria-current={n === page ? "page" : undefined} aria-label={t("pg_page_x", { n })} onClick={() => n !== page && onPage(n)}>{n}</button>)}
        <button type="button" className="btn" disabled={page >= pages || busy} onClick={() => onPage(page + 1)} aria-label={t("pg_next")}>{t("pg_next")} ›</button>
        {onSize && (
          <label className="pager-size muted small">{t("pg_per_page")}
            <select className="input" value={size} onChange={(e) => onSize(Number(e.target.value))}>
              {(SIZES.includes(size) ? SIZES : [...SIZES, size].sort((x, y) => x - y)).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
      </nav>
    </div>
  );
}

/** Bring the top of a list back into view after the person changes page, but only when it has scrolled off screen. */
function reveal(el: HTMLElement | null) {
  if (!el || typeof window === "undefined") return;
  if (el.getBoundingClientRect().top < 0) el.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

type Params = Record<string, string | number | boolean | null | undefined>;

/** A list the server pages (?page=&page_size=). Changing page or size fetches only that page and keeps the rows on
 *  screen while it loads, so nothing flashes and the page is never reloaded. Changing a filter (any value in `params`)
 *  goes back to page 1. Rows come from {results}, {items} (notifications) or the field named in opts.field (leaderboard: "entries"). */
export function usePaged<T = any>(path: string | null, params: Params = {}, opts: { size?: number; field?: string } = {}) {
  const base = opts.size ?? 20;
  const query = useMemo(() => {
    const u = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== "" && v != null && v !== false && u.set(k, String(v)));
    return u.toString();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);
  const key = `${path}?${query}`;
  const [st, setSt] = useState({ key, page: 1, size: base });
  const page = st.key === key ? st.page : 1;  // a new filter always starts on page 1
  const size = st.size;
  const [box, setBox] = useState<{ p: string | null; r: any }>({ p: path, r: null });
  const data = box.p === path ? box.r : null;  // rows of another list (teachers -> admins) are never shown under this one
  const setData = (r: any) => setBox({ p: path, r });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const top = useRef<any>(null);
  const seq = useRef(0);
  const quiet = useRef(false);  // a refresh the person did not ask for (polling, after an edit): no dimming

  useEffect(() => {
    if (!path) { setLoading(false); return; }
    const mine = ++seq.current;
    if (!quiet.current) setLoading(true);
    quiet.current = false;
    const qs = new URLSearchParams(query);
    qs.set("page", String(page)); qs.set("page_size", String(size));
    api<any>(`${path}${path.includes("?") ? "&" : "?"}${qs}`)
      .then((r) => {
        if (mine !== seq.current) return;  // an older answer arriving late
        setBox({ p: path, r }); setError("");
        if (r?.page && r.page !== page) setSt({ key, page: r.page, size });  // the last row of the last page was removed
      })
      .catch((e) => mine === seq.current && setError(e.message || "Error"))
      .finally(() => mine === seq.current && setLoading(false));
  }, [path, query, page, size, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = useCallback((p: number) => { setSt({ key, page: p, size }); reveal(top.current); }, [key, size]);
  const setSize = useCallback((n: number) => setSt({ key, page: 1, size: n }), [key]);
  const rows: T[] = (opts.field && data?.[opts.field]) || data?.results || data?.items || (Array.isArray(data) ? data : []);
  const count: number = data?.count ?? rows.length;
  const pages: number = data?.pages ?? 1;
  return {
    rows, count, page: data?.page ?? page, pages, size, data, error, top,
    loading: loading && !data,          // first load only: show the spinner once
    busy: loading && !!data,            // moving between pages: keep the rows, dim them
    reload: () => { quiet.current = true; setTick((x) => x + 1); }, setData,
    pager: { page: data?.page ?? page, pages, count, size, onPage: go, onSize: setSize, busy: loading && !!data } as PagerProps,
  };
}

/** The same buttons for a list the page already holds in full (small lists, or lists the screen filters and sorts itself). */
export function useClientPage<T>(items: T[] | null | undefined, initial = 10, resetKey: string = "") {
  const [st, setSt] = useState({ key: resetKey, page: 1, size: initial });
  const list = items || [];
  const size = st.size;
  const pages = Math.max(1, Math.ceil(list.length / size));
  const page = Math.min(st.key === resetKey ? st.page : 1, pages);
  const top = useRef<any>(null);
  const go = (p: number) => { setSt({ key: resetKey, page: p, size }); reveal(top.current); };
  return {
    rows: list.slice((page - 1) * size, page * size), top, page, pages, count: list.length,
    pager: { page, pages, count: list.length, size, onPage: go, onSize: (n: number) => setSt({ key: resetKey, page: 1, size: n }) } as PagerProps,
  };
}

/** A list inside a card or a loop (where a hook cannot go): <PagedList items={...} size={10} render={(x) => <li>…</li>} /> */
export function PagedList<T>({ items, size = 10, render, as = "ul", className = "list" }: { items: T[]; size?: number; render: (x: T, i: number) => ReactNode; as?: "ul" | "ol" | "div"; className?: string }) {
  const pg = useClientPage(items, size);
  const Tag = as as any;
  const first = (pg.page - 1) * pg.pager.size;
  return (
    <>
      <Tag className={className} ref={pg.top}>{pg.rows.map((x, i) => render(x, first + i))}</Tag>
      <Pager {...pg.pager} onSize={undefined} />
    </>
  );
}
