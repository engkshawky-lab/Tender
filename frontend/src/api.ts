const TOKEN_KEY = "tp_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

async function req(method: string, url: string, body?: any, isForm = false) {
  const headers: Record<string, string> = {};
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const r = await fetch(url, { method, headers, body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined });
  if (r.status === 401 && !url.endsWith("/auth/login")) {
    setToken(null);
    window.location.href = "/login";
  }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new ApiError(r.status, (data as any)?.detail ?? data);
  return data;
}

export const api = {
  get: (u: string) => req("GET", `/api${u}`),
  post: (u: string, b: any = {}) => req("POST", `/api${u}`, b),
  put: (u: string, b: any) => req("PUT", `/api${u}`, b),
  patch: (u: string, b: any) => req("PATCH", `/api${u}`, b),
  del: (u: string) => req("DELETE", `/api${u}`),
  upload: (u: string, file: File, fields: Record<string, any> = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(fields).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && fd.append(k, String(v)));
    return req("POST", `/api${u}`, fd, true);
  },
  login: async (username: string, password: string) => {
    const fd = new URLSearchParams({ username, password });
    const r = await fetch("/api/auth/login", { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) throw new ApiError(r.status, d.detail);
    setToken(d.access_token);
  },
  download: async (u: string, fallbackName = "download") => {
    const r = await fetch(`/api${u}`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!r.ok) {
      let d: any = await r.text();
      try { d = JSON.parse(d).detail; } catch { /* text */ }
      throw new ApiError(r.status, d);
    }
    const blob = await r.blob();
    const cd = r.headers.get("content-disposition") || "";
    const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || fallbackName;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  },
};
