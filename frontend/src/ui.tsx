import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { useI18n, useLabel } from "./i18n";

// ---------------------------------------------------------------- auth context
export interface Me { id: number; username: string; full_name: string; roles: string[]; permissions: string[] }
export const AuthCtx = createContext<{ me: Me | null; reload: () => void }>({ me: null, reload: () => {} });
export const useAuth = () => useContext(AuthCtx);
export function useCan() {
  const { me } = useAuth();
  return (p: string) => !!me?.permissions.includes(p);
}

// ---------------------------------------------------------------- toast
const ToastCtx = createContext<(msg: string, kind?: "ok" | "err") => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string; kind: string }[]>([]);
  const push = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, msg, kind }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === "err" ? 7000 : 3000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts">{items.map((i) => <div key={i.id} className={`toast ${i.kind}`}>{i.msg}</div>)}</div>
    </ToastCtx.Provider>
  );
}

const ERR_AR: [RegExp, string][] = [
  [/^Missing permission: (.*)$/, "ليس لديك صلاحية: $1"],
  [/^Wrong username or password$/, "اسم المستخدم أو كلمة المرور غير صحيحة"],
  [/^Not authenticated$|^Invalid or expired token$/, "انتهت الجلسة — سجّل الدخول مرة أخرى"],
  [/is (\w+) and locked — create a new version to change it$/, "النسخة مقفولة — أنشئ نسخة جديدة للتعديل"],
  [/^Fix blocking checks before review$|^Blocking checks$/, "يوجد أخطاء تمنع الإرسال للمراجعة"],
  [/^Only versions in review can be (approved|rejected)$/, "يمكن الاعتماد أو الرفض للنسخ قيد المراجعة فقط"],
  [/^A documented reason is required for the decision$|^A reason is required$/, "يلزم كتابة السبب"],
  [/^No readable documents/, "لا توجد مستندات مقروءة — ارفع مستندات المناقصة أولًا"],
  [/^Approve the AI-extracted quotation lines first$/, "اعتمد بنود العرض المفرغة بالـ AI أولًا"],
  [/^Complete the submission checklist first$/, "أكمل قائمة تدقيق التقديم أولًا"],
  [/^No approved estimate version$/, "لا توجد نسخة تسعير معتمدة"],
  [/^No BOQ header found/, "لم يتم التعرف على صف العناوين في المقايسة (يلزم عمودا الوصف والكمية على الأقل)"],
  [/^Upload the (owner's BOQ|priced BOQ) as \.xlsx/, "ارفع المقايسة بصيغة xlsx"],
  [/^The rate column is empty/, "عمود الأسعار فارغ — هل هذه النسخة المسعرة من الملف؟"],
  [/^No rate \/ price column found/, "لم يتم العثور على عمود السعر في الملف"],
  [/^Reading PDF \/ e-mail quotations needs the AI service/, "قراءة عروض PDF والإيميل تحتاج تفعيل الـ AI (مفتاح API). بدون AI استخدم ملف RFQ Excel."],
  [/^Supplier unknown/, "المورد غير معروف — اختر المورد"],
  [/^Username already exists$/, "اسم المستخدم موجود بالفعل"],
  [/^Old password is wrong$/, "كلمة المرور الحالية غير صحيحة"],
  [/^Quotation belongs to another package$/, "العرض يخص حزمة أخرى"],
  [/^The item has no build-up lines$/, "البند ليس له تحليل سعر"],
  [/^Cannot reach the AI service$/, "تعذر الاتصال بخدمة الـ AI"],
  [/^AI authentication failed/, "مفتاح الـ AI غير صحيح — راجع ANTHROPIC_API_KEY"],
  [/^AI rate limit reached/, "تم تجاوز حد الاستخدام للـ AI — أعد المحاولة بعد دقيقة"],
  [/^Price-based percentages/, "نسب الضمانات والتأمين والضرائب ضمن السعر مرتفعة جدًا ولا يمكن حساب السعر"],
];

function localise(msg: string): string {
  if (document.documentElement.lang !== "ar") return msg;
  for (const [re, ar] of ERR_AR) if (re.test(msg)) return msg.replace(re, ar);
  return msg;
}

export function errText(e: any): string {
  const ar = document.documentElement.lang === "ar";
  if (e instanceof ApiError) {
    if (e.detail?.checks) return `${localise(e.detail.message)}: ${e.detail.checks.map((c: any) => (ar ? c.message_ar : c.message) || c.message).join(" · ")}`;
    return localise(e.message);
  }
  return localise(String(e?.message || e));
}

/** Run an async action with toast on error/success. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async <T,>(fn: () => Promise<T>, okMsg?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      if (okMsg) toast(okMsg);
      return r;
    } catch (e) {
      toast(errText(e), "err");
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { run, busy };
}

export function useLoad<T>(url: string | null, deps: any[] = []): [T | undefined, () => void, boolean, any] {
  const [data, setData] = useState<T>();
  const [err, setErr] = useState<any>();
  const [loading, setLoading] = useState(false);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    setLoading(true);
    api.get(url).then((d) => alive && (setData(d), setErr(undefined))).catch((e) => alive && setErr(e)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, n, ...deps]);
  return [data, () => setN((x) => x + 1), loading, err];
}

// ---------------------------------------------------------------- formatting
export function useFmt() {
  const { lang } = useI18n();
  const loc = lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
  return {
    n: (v: any, d = 2) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? "—" : Number(v).toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: d })),
    m: (v: any) => (v === null || v === undefined || isNaN(Number(v)) ? "—" : Number(v).toLocaleString(loc, { maximumFractionDigits: 0 })),
    p: (v: any, d = 1) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(d)}%`),
    d: (v: any) => (v ? new Date(v).toLocaleDateString(loc, { year: "numeric", month: "short", day: "numeric" }) : "—"),
  };
}

// ---------------------------------------------------------------- primitives
export function Card({ title, actions, children, className = "" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && <header className="card-h"><h3>{title}</h3><div className="row gap">{actions}</div></header>}
      <div className="card-b">{children}</div>
    </section>
  );
}

export function Badge({ k, children, tone }: { k?: string; children?: ReactNode; tone?: string }) {
  const lab = useLabel();
  return <span className={`badge ${tone || k || ""}`}>{children ?? lab(k)}</span>;
}

export function AIBadge({ conf, src }: { conf?: number | null; src?: string }) {
  const { L } = useI18n();
  return <span className="badge ai" title={src}>{L("اقتراح AI", "AI suggestion")}{conf != null ? ` · ${Math.round(conf * 100)}%` : ""}</span>;
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: ReactNode; hidden?: boolean }[]; active: string; onChange: (k: string) => void }) {
  return (
    <nav className="tabs" role="tablist">
      {tabs.filter((t) => !t.hidden).map((t) => (
        <button key={t.key} role="tab" aria-selected={active === t.key} className={active === t.key ? "on" : ""} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </nav>
  );
}

export function Field({ label, children, hint, wide }: { label: ReactNode; children: ReactNode; hint?: ReactNode; wide?: boolean }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span className="lbl">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

export function Modal({ title, onClose, children, wide }: { title: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} ref={ref} role="dialog" aria-modal="true">
        <header className="card-h"><h3>{title}</h3><button className="ghost" onClick={onClose} aria-label="close">✕</button></header>
        <div className="card-b">{children}</div>
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Stat({ label, value, sub, tone }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className={`stat ${tone || ""}`}>
      <div className="stat-l">{label}</div>
      <div className="stat-v">{value}</div>
      {sub && <div className="stat-s">{sub}</div>}
    </div>
  );
}

export function FileButton({ label, accept, onFile, disabled, className = "" }: { label: ReactNode; accept?: string; onFile: (f: File) => void; disabled?: boolean; className?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button className={className} disabled={disabled} onClick={() => ref.current?.click()}>{label}</button>
      <input ref={ref} type="file" hidden accept={accept} onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
    </>
  );
}

/** Number input that commits on blur / enter (keeps typing smooth for big tables). */
export function NumIn({ value, onCommit, step = "any", disabled, className = "", placeholder }: { value: any; onCommit: (v: number | null) => void; step?: string; disabled?: boolean; className?: string; placeholder?: string }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const commit = () => {
    const nv = v === "" ? null : Number(v);
    if (nv !== (value ?? null) && !(nv !== null && isNaN(nv))) onCommit(nv);
  };
  return <input className={`num ${className}`} type="number" step={step} value={v} disabled={disabled} placeholder={placeholder}
    onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />;
}

export function TextIn({ value, onCommit, disabled, className = "", placeholder, multiline }: { value: any; onCommit: (v: string) => void; disabled?: boolean; className?: string; placeholder?: string; multiline?: boolean }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const commit = () => v !== (value ?? "") && onCommit(v);
  return multiline
    ? <textarea className={className} value={v} disabled={disabled} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit} />
    : <input className={className} value={v} disabled={disabled} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />;
}

export function Select({ value, onChange, options, disabled, className = "" }: { value: any; onChange: (v: string) => void; options: [string | number, string][]; disabled?: boolean; className?: string }) {
  return (
    <select className={className} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {options.map(([k, l]) => <option key={String(k)} value={k}>{l}</option>)}
    </select>
  );
}

export function SourceRef({ file, page, quote }: { file?: string; page?: number; quote?: string }) {
  const { L } = useI18n();
  if (!file) return null;
  return <span className="src" title={quote}>📄 {file}{page ? ` · ${L("ص", "p.")} ${page}` : ""}</span>;
}
