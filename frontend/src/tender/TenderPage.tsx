import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useI18n, useLabel } from "../i18n";
import { Badge, Tabs, useFmt, useLoad } from "../ui";
import Analysis from "./Analysis";
import Boq from "./Boq";
import Documents from "./Documents";
import Overview from "./Overview";
import Pricing from "./Pricing";
import Procurement from "./Procurement";
import SiteVisit from "./SiteVisit";
import Submission from "./Submission";

export interface TenderCtxT {
  tender: any;
  reload: () => void;
  estimates: any[];
  reloadEstimates: () => void;
  estimateId: number | null;
  setEstimateId: (id: number | null) => void;
  estimate: any | null;
}
export const TenderCtx = createContext<TenderCtxT>(null as any);
export const useTender = () => useContext(TenderCtx);

const STEPS: Record<string, string> = { overview: "1–2", documents: "3", analysis: "4–5", site: "6", boq: "7–8", procurement: "9", pricing: "10–17", submission: "18–20" };

export default function TenderPage() {
  const { id, "*": rest } = useParams();
  const nav = useNavigate();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const [tender, reload] = useLoad<any>(`/tenders/${id}`);
  const [estimates, reloadEstimates] = useLoad<any[]>(`/tenders/${id}/estimates`);
  const [estimateId, setEstimateId] = useState<number | null>(null);
  useEffect(() => {
    if (estimates?.length && !estimates.find((e) => e.id === estimateId)) setEstimateId(estimates[estimates.length - 1].id);
  }, [estimates]);
  const tab = rest?.split("/")[0] || "overview";
  if (!tender) return null;
  const tabs = [
    { key: "overview", label: L("الاستلام والقرار", "Intake & decision") },
    { key: "documents", label: L("المستندات", "Documents") },
    { key: "analysis", label: L("الشروط والمخاطر والاستفسارات", "Terms, risks & RFIs") },
    { key: "site", label: L("زيارة الموقع", "Site visit") },
    { key: "boq", label: L("المقايسة والحزم", "BOQ & packages") },
    { key: "procurement", label: L("عروض الأسعار", "Quotations") },
    { key: "pricing", label: L("التسعير والاعتماد", "Pricing & approval") },
    { key: "submission", label: L("التقديم والنتيجة", "Submission & result") },
  ].map((t) => ({ ...t, label: <span>{t.label} <span className="muted small">{STEPS[t.key]}</span></span> }));
  const estimate = estimates?.find((e) => e.id === estimateId) || null;
  return (
    <TenderCtx.Provider value={{ tender, reload, estimates: estimates || [], reloadEstimates, estimateId, setEstimateId, estimate }}>
      <div className="page-h">
        <div>
          <div className="row gap wrap"><h1>{tender.name}</h1><Badge k={tender.status} /><Badge>{lab(tender.project_type)}</Badge></div>
          <div className="sub">{tender.code} · {tender.owner || L("المالك غير محدد", "owner not set")}{tender.consultant ? ` · ${tender.consultant}` : ""}
            {tender.submission_date && ` · ${L("التقديم", "submission")} ${fmt.d(tender.submission_date)}`}
            {tender.days_to_submission != null && tender.days_to_submission >= 0 && ` (${tender.days_to_submission} ${L("يوم", "days")})`}</div>
        </div>
      </div>
      <Tabs tabs={tabs} active={tab} onChange={(k) => nav(`/tenders/${id}/${k === "overview" ? "" : k}`)} />
      {tab === "overview" && <Overview />}
      {tab === "documents" && <Documents />}
      {tab === "analysis" && <Analysis />}
      {tab === "site" && <SiteVisit />}
      {tab === "boq" && <Boq />}
      {tab === "procurement" && <Procurement />}
      {tab === "pricing" && <Pricing />}
      {tab === "submission" && <Submission />}
    </TenderCtx.Provider>
  );
}

export function EstimatePicker({ allowCreate = true }: { allowCreate?: boolean }) {
  const { estimates, estimateId, setEstimateId } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  if (!estimates.length) return <span className="muted">{L("لا توجد نسخة تسعير بعد", "No estimate version yet")}</span>;
  return (
    <label className="row gap">
      <span className="muted small">{L("نسخة التسعير", "Estimate version")}</span>
      <select value={estimateId ?? ""} onChange={(e) => setEstimateId(Number(e.target.value))}>
        {estimates.map((e) => <option key={e.id} value={e.id}>V{e.version_no} — {lab(e.status)}{e.name && e.name !== `V${e.version_no}` ? ` — ${e.name}` : ""}</option>)}
      </select>
    </label>
  );
}
