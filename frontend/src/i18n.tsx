import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Lang = "ar" | "en";
interface Ctx { lang: Lang; setLang: (l: Lang) => void; L: (ar: string, en: string) => string }
const I18n = createContext<Ctx>({ lang: "ar", setLang: () => {}, L: (a) => a });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    try { return (localStorage.getItem("tp_lang") as Lang) || "ar"; } catch { return "ar"; }
  });
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  const setLang = (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("tp_lang", l); } catch { /* ignore */ }
  };
  return <I18n.Provider value={{ lang, setLang, L: (ar, en) => (lang === "ar" ? ar : en) }}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);

/** Shared labels so every screen names things the same way. */
export const LABELS: Record<string, [string, string]> = {
  intake: ["استلام", "Intake"], go_no_go: ["قرار الدخول", "Go / No-Go"], study: ["دراسة المستندات", "Study"],
  pricing: ["تسعير", "Pricing"], review: ["مراجعة", "Review"], approved: ["معتمد", "Approved"],
  submitted: ["مقدَّم", "Submitted"], won: ["فزنا", "Won"], lost: ["خسرنا", "Lost"], cancelled: ["ملغاة", "Cancelled"],
  declined: ["اعتذار", "Declined"], historical: ["أرشيف سابق", "Historical"],
  draft: ["مسودة", "Draft"], in_review: ["قيد المراجعة", "In review"], rejected: ["مرفوض", "Rejected"],
  building: ["متكامل", "Integrated"], infra: ["بنية تحتية", "Infrastructure"],
  supply: ["توريد", "Supply"], apply: ["تركيب", "Apply"], supply_apply: ["توريد وتركيب", "Supply + Apply"],
  material: ["خامات", "Material"], labor: ["عمالة", "Labour"], equipment: ["معدات", "Equipment"], subcontract: ["مقاول باطن", "Subcontract"],
  quotation: ["عرض سعر", "Quotation"], library: ["مكتبة الأسعار", "Library"], history: ["مشروع سابق", "Previous project"],
  manual: ["يدوي", "Manual"], ai: ["AI", "AI"],
  self: ["تنفيذ ذاتي", "Self-perform"], supply_only: ["توريد فقط", "Supply only"], mixed: ["مختلط", "Mixed"],
  time: ["زمني", "Time-related"], fixed: ["ثابت", "Fixed"],
  error: ["خطأ", "Error"], warning: ["تنبيه", "Warning"], info: ["ملاحظة", "Info"],
  invitation: ["خطاب الدعوة", "Invitation"], drawings: ["اللوحات", "Drawings"], specs: ["المواصفات", "Specifications"],
  boq: ["المقايسة", "BOQ"], general_conditions: ["الشروط العامة", "General conditions"],
  particular_conditions: ["الشروط الخاصة", "Particular conditions"], addendum: ["ملحق", "Addendum"],
  site_photo: ["صورة موقع", "Site photo"], submission: ["تقديم", "Submission"], other: ["أخرى", "Other"],
  contractual: ["تعاقدية", "Contractual"], financial: ["مالية", "Financial"], technical: ["فنية", "Technical"],
  schedule: ["زمنية", "Schedule"], site: ["موقع", "Site"], procurement: ["مشتريات", "Procurement"], fx: ["سعر صرف", "FX"],
};

export function useLabel() {
  const { lang } = useI18n();
  return (k?: string | null) => (k && LABELS[k] ? LABELS[k][lang === "ar" ? 0 : 1] : k || "");
}
