import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Badge, Card, Field, Select, useAction, useCan, useFmt, useLoad } from "../ui";
import { EstimatePicker, useTender } from "./TenderPage";

function OfferLetter({ estimateId }: { estimateId: number }) {
  const { L, lang } = useI18n();
  const { run } = useAction();
  const [settings] = useLoad<any>("/settings");
  const [sel, setSel] = useState<number[]>([]);
  const [extra, setExtra] = useState("");
  const [text, setText] = useState("");
  const lib = settings?.clarifications_library || [];
  const gen = () => run(async () => setText((await api.post(`/estimates/${estimateId}/offer-letter`, { clarifications: sel, extra: extra.split("\n") })).text));
  return (
    <Card title={L("خطاب العرض المالي والتحفظات", "Financial offer letter & clarifications")}>
      <p className="muted small">{L("اختر من مكتبة التحفظات (تُعدَّل من الإعدادات) وأضف تحفظات خاصة بهذه المناقصة.", "Pick from the clarifications library (editable in Settings) and add tender-specific ones.")}</p>
      {lib.map((c: any, i: number) => (
        <label key={i} className="check-row"><input type="checkbox" checked={sel.includes(i)} onChange={(e) => setSel(e.target.checked ? [...sel, i] : sel.filter((x) => x !== i))} /><span>{lang === "ar" ? c.ar : c.en}</span></label>))}
      <textarea placeholder={L("تحفظات إضافية (سطر لكل تحفظ)", "Additional clarifications (one per line)")} value={extra} onChange={(e) => setExtra(e.target.value)} style={{ marginTop: 8 }} />
      <div className="row gap" style={{ marginTop: 8 }}><button className="primary" onClick={gen}>{L("إنشاء الخطاب", "Generate letter")}</button>
        {text && <button onClick={() => navigator.clipboard?.writeText(text)}>{L("نسخ", "Copy")}</button>}</div>
      {text && <pre className="letter" style={{ marginTop: 10 }}>{text}</pre>}
    </Card>
  );
}

export default function Submission() {
  const { tender, reload, estimate, estimates } = useTender();
  const { L, lang } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [list, setList] = useState<any[]>(tender.submission_checklist || []);
  const [res, reloadR] = useLoad<any>(`/tenders/${tender.id}/result`);
  const [f, setF] = useState<any>({ outcome: "won", competitors: [] });
  useEffect(() => setList(tender.submission_checklist || []), [tender]);
  useEffect(() => { if (res?.result?.outcome) setF({ ...res.result, competitors: res.competitors }); }, [res]);
  const approved = estimates.filter((e) => e.status === "approved").slice(-1)[0];
  const saveList = (next: any[], mark = false) => run(async () => { await api.put(`/tenders/${tender.id}/submission`, { checklist: next, mark_submitted: mark }); reload(); }, mark ? L("تم تسجيل التقديم", "Marked as submitted") : undefined);
  const saveResult = () => run(async () => { await api.put(`/tenders/${tender.id}/result`, f); reload(); reloadR(); }, L("تم تسجيل النتيجة — تغذي الاقتراحات القادمة", "Result recorded — it feeds future suggestions"));
  const dl = (path: string) => run(() => api.download(path));
  return (
    <div className="stack">
      <Card title={L("18) ملفات العرض", "18) Proposal files")} actions={<EstimatePicker />}>
        <div className="row gap wrap">
          {can("markup.view") && <button className="primary" disabled={!estimate} onClick={() => dl(`/estimates/${estimate.id}/export/owner.xlsx`)}>⬇ {L("المقايسة المسعرة بنموذج المالك", "Priced BOQ in owner format")}</button>}
          <button disabled={!estimate} onClick={() => dl(`/estimates/${estimate.id}/export/internal.xlsx`)}>⬇ {L("ملف التسعير الداخلي (تحليل + غير مباشر + تدفق)", "Internal estimate workbook")}</button>
        </div>
        {estimate && estimate.status !== "approved" && <p className="alert" style={{ marginTop: 10 }}>{L("هذه النسخة غير معتمدة — الملف يحمل علامة DRAFT. للتقديم استخدم النسخة المعتمدة.", "This version is not approved — the file is marked DRAFT. Submit the approved version.")}</p>}
        <p className="muted small">{L("الملف المسعر يُكتب داخل ملف Excel الأصلي للمالك نفسه، فيحتفظ بالترقيم والخلايا المدمجة والأقسام والمعادلات. العرض الفني (طرق التنفيذ والهيكل والسير الذاتية) مجدول في الإصدار 4.", "Prices are written into the owner's original workbook, preserving numbering, merged cells, sections and formulas. Technical proposal drafting is planned for release 4.")}</p>
      </Card>
      {estimate && <OfferLetter estimateId={estimate.id} />}
      <Card title={L("19) قائمة تدقيق التقديم", "19) Submission checklist")} actions={<Badge k={tender.status} />}>
        {list.map((x, i) => (
          <label key={i} className="check-row">
            <input type="checkbox" checked={!!x.done} disabled={!can("proposal.manage")} onChange={(e) => { const nx = list.map((y, j) => j === i ? { ...y, done: e.target.checked } : y); setList(nx); saveList(nx); }} />
            <span>{lang === "ar" ? x.ar : x.en}</span>
          </label>))}
        {can("proposal.manage") && !["submitted", "won", "lost"].includes(tender.status) && (
          <button className="primary" style={{ marginTop: 10 }} disabled={busy || !approved || list.some((x) => !x.done)} onClick={() => saveList(list, true)}>
            {L("تسجيل التقديم", "Mark as submitted")} {approved ? `(V${approved.version_no})` : ""}</button>)}
        {!approved && <p className="muted small">{L("يلزم نسخة تسعير معتمدة قبل التقديم", "An approved estimate is required before submission")}</p>}
      </Card>
      <Card title={L("20) ما بعد التقديم — النتيجة وأسعار المنافسين والدروس المستفادة", "20) Post-tender — result, competitor prices & lessons")}>
        <div className="form">
          <Field label={L("النتيجة", "Outcome")}><Select value={f.outcome} onChange={(v) => setF({ ...f, outcome: v })} options={[["won", L("فزنا", "Won")], ["lost", L("خسرنا", "Lost")], ["cancelled", L("ألغيت", "Cancelled")]]} /></Field>
          <Field label={L("تاريخ فتح المظاريف", "Opening date")}><input type="date" value={f.date || ""} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          {can("markup.view") && <Field label={L("سعرنا المقدم", "Our price")}><input type="number" value={f.our_price ?? res?.our_total ?? ""} onChange={(e) => setF({ ...f, our_price: Number(e.target.value) })} /></Field>}
          <Field label={L("الفائز", "Winner")}><input value={f.winner || ""} onChange={(e) => setF({ ...f, winner: e.target.value })} /></Field>
          <Field label={L("أسباب الفوز / الخسارة", "Win / loss reasons")} wide><textarea value={f.reasons || ""} onChange={(e) => setF({ ...f, reasons: e.target.value })} /></Field>
          <Field label={L("الدروس المستفادة", "Lessons learned")} wide><textarea value={f.lessons || ""} onChange={(e) => setF({ ...f, lessons: e.target.value })} /></Field>
        </div>
        <h4 style={{ margin: "12px 0 6px" }}>{L("أسعار المنافسين", "Competitor prices")}</h4>
        <table><tbody>
          {(f.competitors || []).map((c: any, i: number) => (
            <tr key={i}>
              <td><input value={c.name || ""} placeholder={L("المنافس", "Competitor")} onChange={(e) => setF({ ...f, competitors: f.competitors.map((x: any, j: number) => j === i ? { ...x, name: e.target.value } : x) })} /></td>
              <td><input type="number" value={c.price ?? ""} placeholder={L("السعر", "Price")} onChange={(e) => setF({ ...f, competitors: f.competitors.map((x: any, j: number) => j === i ? { ...x, price: Number(e.target.value) } : x) })} /></td>
              <td className="n">{c.diff_pct != null ? `${L("فرقنا", "our diff")} ${fmt.p(c.diff_pct)}` : ""}</td>
            </tr>))}
          <tr><td colSpan={3}><button className="sm" onClick={() => setF({ ...f, competitors: [...(f.competitors || []), {}] })}>+ {L("منافس", "Competitor")}</button></td></tr>
        </tbody></table>
        {can("proposal.manage") && <button className="primary" style={{ marginTop: 10 }} onClick={saveResult}>{L("حفظ النتيجة", "Save result")}</button>}
        {tender.status === "won" && approved && can("markup.view") && (
          <div className="alert info" style={{ marginTop: 12 }}>
            {L("تمت الترسية: حوّل التسعير المعتمد إلى ميزانية تنفيذ.", "Awarded: convert the approved estimate into the execution budget.")}{" "}
            <button className="sm primary" onClick={() => dl(`/estimates/${approved.id}/export/baseline.xlsx`)}>⬇ {L("ميزانية التنفيذ (Baseline)", "Baseline budget")}</button>
          </div>)}
      </Card>
    </div>
  );
}
