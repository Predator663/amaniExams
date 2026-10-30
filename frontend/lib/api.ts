/** "" = same address as the web page (development: Next.js forwards /api to Django). Otherwise the full address of the API. */
export const API = (process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "" : "http://localhost:8000")).replace(/\/$/, "");
export const apiBase = () => API || (typeof location !== "undefined" ? location.origin : "");
const TOKEN_KEY = "amani_token";

export class ApiError extends Error {
  status: number;
  code: string;
  data: any;
  constructor(message: string, status: number, code = "error", data: any = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.data = data;
  }
  /** status 0 = the phone could not reach the server (offline, or the server is down). */
  get isNetwork() { return this.status === 0; }
}

export const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY));
export const setToken = (t: string | null) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

function firstMessage(data: any, status: number): string {
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") return data.detail;
    for (const v of Object.values(data)) {
      if (typeof v === "string") return v;
      if (Array.isArray(v) && typeof v[0] === "string") return v[0];
    }
  }
  return status === 429 ? "Too many tries. Please wait a moment." : "Something went wrong. Please try again.";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; auth?: boolean; keepalive?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token && opts.auth !== false) headers.Authorization = `Token ${token}`;
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  if (opts.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${API}/api${path}`, {
      method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
      headers, body: opts.body === undefined ? undefined : isForm ? opts.body : JSON.stringify(opts.body), keepalive: opts.keepalive,
    });
  } catch {
    throw new ApiError(`Cannot reach the server (${apiBase()}). Check your internet. If you run it yourself, make sure the Django server is running.`, 0, "network");
  }
  let data: any = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok && data === null && res.status >= 500) {
    // Not JSON from our API: a proxy or gateway answered because Django behind it is down or crashed.
    throw new ApiError(`Cannot reach the server (${apiBase()}). Check your internet. If you run it yourself, make sure the Django server is running.`, 0, "network");
  }
  if (!res.ok) {
    if (res.status === 503 && data?.code === "maintenance") window.dispatchEvent(new CustomEvent("amani:maintenance", { detail: data }));
    if (res.status === 401 && opts.auth !== false) window.dispatchEvent(new CustomEvent("amani:unauthorized"));
    if (res.status === 403 && data?.code === "password_change_required") window.dispatchEvent(new CustomEvent("amani:must-change-password"));
    throw new ApiError(firstMessage(data, res.status), res.status, data?.code || "error", data);
  }
  return data as T;
}

/** Download a file (PDF slip) with the login token, then hand it to the browser. */
export async function downloadFile(path: string, filename: string) {
  const res = await fetch(`${API}/api${path}`, { headers: { Authorization: `Token ${getToken()}` } });
  if (!res.ok) throw new ApiError("The file is not available yet.", res.status);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const mediaUrl = (u?: string | null) => (!u ? "" : /^https?:/i.test(u) ? u : `${API}${u.startsWith("/") ? "" : "/"}${u}`);
