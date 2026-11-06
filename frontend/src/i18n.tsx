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
  // roles
  admin: ["مدير النظام", "Administrator"], tender_manager: ["مدير العطاءات", "Tender manager"], estimator: ["مُسعِّر / مهندس حصر", "Estimator / QS"],
  planner: ["مخطط", "Planner"], technical_office: ["المكتب الفني", "Technical office"], management: ["الإدارة العليا", "Management"],
  // document text status & origins
  extracted: ["تم استخراج النص", "Text extracted"], needs_ocr: ["يحتاج OCR", "Needs OCR"], failed: ["فشل القراءة", "Read failed"], none: ["بدون نص", "No text"],
  excel: ["Excel", "Excel"], site_visit: ["زيارة الموقع", "Site visit"], similarity: ["تشابه", "Similarity"],
  // vendors
  pending: ["تحت الاعتماد", "Pending"], suspended: ["موقوف", "Suspended"], blacklisted: ["قائمة سوداء", "Blacklisted"],
  supplier: ["مورد", "Supplier"], subcontractor: ["مقاول باطن", "Subcontractor"], both: ["مورد ومقاول", "Both"],
};

export const PERMISSION_LABELS: Record<string, [string, string]> = {
  "tender.manage": ["تسجيل المناقصات والمواعيد وتوزيع المهام", "Register tenders, dates, assignments"],
  "gonogo.decide": ["اتخاذ قرار الدخول", "Take the Go / No-Go decision"],
  "documents.manage": ["رفع وتصنيف المستندات", "Upload and classify documents"],
  "analysis.manage": ["ملخص المناقصة والمخاطر والاستفسارات وزيارة الموقع", "Tender summary, risks, RFIs, site visit"],
  "boq.edit": ["استيراد وتعديل المقايسة والحزم والتكويد", "Import / edit the BOQ, packages, cost codes"],
  "pricing.edit": ["تحليل الأسعار وغير المباشر والطوارئ", "Rate build-up, indirects, contingency"],
  "procurement.manage": ["الموردون وطلبات وعروض الأسعار والمقارنة", "Suppliers, RFQs, quotations, comparison"],
  "schedule.edit": ["البرنامج الزمني ومدخلات التدفق النقدي", "Preliminary schedule & cash-flow inputs"],
  "markup.view": ["رؤية نسبة الربح والأسعار النهائية", "See markup, profit and final prices"],
  "markup.edit": ["تحديد نسبة الربح والتوزيع", "Set markup and price spreading"],
  "estimate.approve": ["اعتماد / رفض نسخة التسعير", "Approve / reject an estimate version"],
  "proposal.manage": ["قائمة التقديم والتصدير والنتائج", "Submission checklist, exports, results"],
  "library.manage": ["مكتبة الأسعار والقوالب والتكويد والمرجعية", "Resource library, templates, cost codes, price references"],
  "vendors.approve": ["اعتماد / إيقاف الموردين", "Approve / suspend / blacklist vendors"],
  "settings.manage": ["إعدادات الشركة (الضرائب والأوزان والنسب)", "Company settings (taxes, weights, ratios)"],
  "users.manage": ["المستخدمون والصلاحيات", "Users and permissions"],
  "audit.view": ["قراءة سجل التعديلات", "Read the audit log"],
};

/** Name of a record that stores an Arabic and an optional English name. */
export function useName() {
  const { lang } = useContext(I18n);
  return (ar?: string | null, en?: string | null) => (lang === "en" ? en || ar || "" : ar || en || "");
}

export function useLabel() {
  const { lang } = useI18n();
  return (k?: string | null) => (k && LABELS[k] ? LABELS[k][lang === "ar" ? 0 : 1] : k || "");
}
