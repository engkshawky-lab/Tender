import { useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { AIBadge, Badge, Card, Empty, Modal, NumIn, Select, SourceRef, TextIn, useAction, useCan, useFmt, useLoad } from "../ui";
import { useTender } from "./TenderPage";

const FIELD_LABELS: Record<string, [string, string]> = {
  owner: ["المالك", "Owner"], consultant: ["الاستشاري", "Consultant"], scope: ["نطاق العمل", "Scope"], duration: ["مدة التنفيذ", "Duration"],
  delay_penalty: ["غرامة التأخير", "Delay penalty"], advance_payment: ["الدفعة المقدمة", "Advance payment"], retention: ["نسبة الاستقطاع", "Retention"],
  payment_terms: ["شروط ومدد الدفع", "Payment terms"], bid_bond: ["التأمين الابتدائي", "Bid bond"], performance_bond: ["التأمين النهائي", "Performance bond"],
  insurance: ["التأمينات", "Insurance"], price_escalation: ["فروق الأسعار", "Price escalation"], currency: ["العملة", "Currency"],
  bid_validity: ["صلاحية العرض", "Bid validity"], approved_vendors: ["الموردين المعتمدين", "Approved vendors"],
  maintenance_period: ["فترة الصيانة", "Defects liability"], site_visit_date: ["زيارة الموقع", "Site visit"],
  rfi_deadline: ["آخر موعد للاستفسارات", "RFI deadline"], submission_date: ["موعد التقديم", "Submission"],
};

function Suggestions({ onChange }: { onChange: () => void }) {
  const { tender, reload } = useTender();
  const { L, lang } = useI18n();
  const lab = useLabel();
  const can = useCan();
  const { run, busy } = useAction();
  const [sugg, reloadS] = useLoad<any[]>(`/tenders/${tender.id}/suggestions?status=pending`);
  const [edit, setEdit] = useState<any>(null);
  const list = (sugg || []).filter((s) => ["summary_field", "risk", "rfi"].includes(s.kind));
  const decide = (s: any, action: string, payload?: any) => run(async () => {
    await api.post(`/suggestions/${s.id}/decide`, { action, payload });
    reloadS(); reload(); onChange();
  });
  const acceptAll = () => run(async () => {
    for (const s of list) await api.post(`/suggestions/${s.id}/decide`, { action: "accept" });
    reloadS(); reload(); onChange();
  }, L("تم اعتماد كل الاقتراحات", "All suggestions accepted"));
  const analyze = () => run(async () => {
    const r = await api.post(`/tenders/${tender.id}/analyze`, {});
    reloadS();
    return r;
  }, L("تم تحليل المستندات", "Documents analysed"));
  const fl = (k: string) => FIELD_LABELS[k]?.[lang === "ar" ? 0 : 1] || k;
  const kindLabel: Record<string, string> = { summary_field: L("شرط", "Term"), risk: L("مخاطرة", "Risk"), rfi: L("استفسار", "RFI") };
  return (
    <Card className="" title={L("4) استخراج الشروط والمخاطر من المستندات", "4) Extract terms & risks from the documents")} actions={<>
      {can("analysis.manage") && <button className="ai-btn" disabled={busy} onClick={analyze}>✦ {L("تحليل المستندات بالـ AI", "Analyse documents with AI")}</button>}
      {can("analysis.manage") && list.length > 0 && <button className="sm" disabled={busy} onClick={acceptAll}>{L("اعتماد الكل", "Accept all")}</button>}
    </>}>
      <p className="muted small">{L("الـ AI يقرأ ويستخرج ويقترح فقط. كل اقتراح يظهر بلون مختلف مع اسم الملف ورقم الصفحة ولا يدخل الملف إلا بعد اعتمادك.", "The AI only reads, extracts and suggests. Each suggestion is highlighted with its file and page and enters the tender only after you accept it.")}</p>
      {!list.length ? <Empty>{L("لا اقتراحات معلقة — ارفع المستندات ثم اضغط تحليل", "No pending suggestions — upload documents, then analyse")}</Empty> : (
        <div className="tbl-wrap"><table>
          <thead><tr><th>{L("النوع", "Kind")}</th><th>{L("البند", "Field")}</th><th>{L("المستخرج", "Extracted")}</th><th>{L("المصدر", "Source")}</th><th /></tr></thead>
          <tbody>{list.map((s) => (
            <tr key={s.id} className="ai-row">
              <td><Badge>{kindLabel[s.kind]}</Badge></td>
              <td>{s.kind === "summary_field" ? fl(s.target) : s.kind === "risk" ? lab(s.payload.category) : ""}</td>
              <td className="desc">{s.payload.value || s.payload.description || s.payload.question}
                {s.payload.numeric != null && <b> → {s.payload.numeric}</b>}{s.payload.date && <b> → {s.payload.date}</b>}</td>
              <td><SourceRef file={s.source.file} page={s.source.page} quote={s.source.quote} /> <AIBadge conf={s.confidence} /></td>
              <td>{can("analysis.manage") && <div className="row gap">
                <button className="sm ok" onClick={() => decide(s, "accept")}>{L("اعتماد", "Accept")}</button>
                <button className="sm" onClick={() => setEdit({ s, payload: { ...s.payload } })}>{L("تعديل", "Edit")}</button>
                <button className="sm danger" onClick={() => decide(s, "reject")}>{L("رفض", "Reject")}</button></div>}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {edit && (
        <Modal title={L("تعديل ثم اعتماد", "Edit & accept")} onClose={() => setEdit(null)}>
          <div className="stack">
            {Object.keys(edit.payload).filter((k) => ["value", "numeric", "date", "description", "probability_pct", "question", "reference", "mitigation"].includes(k)).map((k) => (
              <label key={k} className="field"><span className="lbl">{k}</span>
                <textarea value={edit.payload[k] ?? ""} onChange={(e) => setEdit({ ...edit, payload: { ...edit.payload, [k]: ["numeric", "probability_pct"].includes(k) ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value } })} /></label>))}
            <button className="primary" onClick={() => { decide(edit.s, "accept", edit.payload); setEdit(null); }}>{L("حفظ واعتماد", "Save & accept")}</button>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function Summary() {
  const { tender } = useTender();
  const { L, lang } = useI18n();
  const s = tender.summary || {};
  const keys = Object.keys(FIELD_LABELS).filter((k) => s[k]);
  return (
    <Card title={L("ملخص المناقصة المعتمد (Tender Summary)", "Approved Tender Summary")}>
      {!keys.length ? <Empty>{L("لم تُعتمد شروط بعد", "No approved terms yet")}</Empty> : (
        <table><tbody>{keys.map((k) => (
          <tr key={k}><td style={{ width: 170 }} className="muted">{FIELD_LABELS[k][lang === "ar" ? 0 : 1]}</td>
            <td className="desc">{s[k].value}{s[k].numeric != null && <b> ({s[k].numeric})</b>}</td>
            <td><SourceRef file={s[k].file} page={s[k].page} /></td><td className="muted small">{s[k].approved_by}</td></tr>))}</tbody></table>
      )}
    </Card>
  );
}

function Risks({ n }: { n: number }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [risks, reload] = useLoad<any[]>(`/tenders/${tender.id}/risks`, [n]);
  const [docs] = useLoad<any[]>(`/tenders/${tender.id}/documents`);
  const dname = Object.fromEntries((docs || []).map((d) => [d.id, d.filename]));
  const dis = !can("analysis.manage");
  const upd = (r: any, k: string) => (v: any) => run(async () => { await api.patch(`/risks/${r.id}`, { [k]: v }); reload(); });
  const total = (risks || []).filter((r) => r.include_in_contingency).reduce((s, r) => s + r.expected_value, 0);
  return (
    <Card title={L("سجل المخاطر (احتمال × أثر)", "Risk register (probability × impact)")} actions={!dis && (
      <button className="sm" onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/risks`, { description: L("مخاطرة جديدة", "New risk"), probability_pct: 20 }); reload(); })}>+ {L("مخاطرة", "Risk")}</button>)}>
      {!risks?.length ? <Empty>{L("لا مخاطر مسجلة", "No risks")}</Empty> : (
        <div className="tbl-wrap"><table>
          <thead><tr><th>{L("الوصف", "Description")}</th><th>{L("الفئة", "Category")}</th><th className="n">{L("الاحتمال %", "Prob. %")}</th><th className="n">{L("الأثر", "Impact")}</th>
            <th className="n">{L("القيمة", "Value")}</th><th>{L("في الطوارئ", "In contingency")}</th><th>{L("المصدر", "Source")}</th><th /></tr></thead>
          <tbody>{risks.map((r) => (
            <tr key={r.id}>
              <td style={{ minWidth: 260 }}><TextIn value={r.description} onCommit={upd(r, "description")} disabled={dis} className="grow" /></td>
              <td><Select value={r.category} disabled={dis} onChange={upd(r, "category")} options={["contractual", "financial", "technical", "schedule", "site", "procurement", "fx", "other"].map((c) => [c, lab(c)])} /></td>
              <td className="n"><NumIn className="sm" value={r.probability_pct} onCommit={upd(r, "probability_pct")} disabled={dis} /></td>
              <td className="n"><NumIn value={r.impact_amount} onCommit={upd(r, "impact_amount")} disabled={dis} /></td>
              <td className="n">{fmt.m(r.expected_value)}</td>
              <td><input type="checkbox" checked={r.include_in_contingency} disabled={dis} onChange={(e) => upd(r, "include_in_contingency")(e.target.checked)} /></td>
              <td>{r.source_document_id ? <SourceRef file={dname[r.source_document_id]} page={r.source_page} /> : <Badge>{lab(r.origin)}</Badge>}</td>
              <td>{!dis && <button className="sm ghost" onClick={() => run(async () => { await api.del(`/risks/${r.id}`); reload(); })}>✕</button>}</td>
            </tr>))}
            <tr className="tot"><td colSpan={4}>{L("إجمالي قيمة المخاطر المحملة على الطوارئ", "Total risk value into contingency")}</td><td className="n">{fmt.m(total)}</td><td colSpan={3} /></tr>
          </tbody>
        </table></div>
      )}
    </Card>
  );
}

function Rfis({ n }: { n: number }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const can = useCan();
  const { run } = useAction();
  const [rfis, reload] = useLoad<any[]>(`/tenders/${tender.id}/rfis`, [n]);
  const [letter, setLetter] = useState<string | null>(null);
  const dis = !can("analysis.manage");
  const upd = (r: any, k: string) => (v: any) => run(async () => { await api.patch(`/rfis/${r.id}`, { [k]: v }); reload(); });
  return (
    <Card title={L("5) الاستفسارات (RFIs) وأثرها على التسعير", "5) Clarifications (RFIs) & pricing impact")} actions={<>
      {!dis && <button className="sm" onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/rfis`, { question: L("سؤال جديد", "New question") }); reload(); })}>+ {L("استفسار", "RFI")}</button>}
      <button className="sm" onClick={() => run(async () => setLetter((await api.get(`/tenders/${tender.id}/rfis/letter`)).text))}>{L("خطاب الاستفسارات", "RFI letter")}</button></>}>
      {!rfis?.length ? <Empty>{L("لا استفسارات", "No RFIs")}</Empty> : (
        <div className="tbl-wrap"><table>
          <thead><tr><th>#</th><th>{L("السؤال", "Question")}</th><th>{L("المرجع", "Reference")}</th><th>{L("الحالة", "Status")}</th><th>{L("الرد", "Answer")}</th><th>{L("الأثر على التسعير", "Pricing impact")}</th></tr></thead>
          <tbody>{rfis.map((r) => (
            <tr key={r.id} className={r.origin === "ai" && r.status === "draft" ? "ai-row" : ""}>
              <td>{r.number}</td>
              <td style={{ minWidth: 280 }}><TextIn multiline value={r.question} onCommit={upd(r, "question")} disabled={dis} /></td>
              <td className="small">{r.reference}</td>
              <td><Select value={r.status} disabled={dis} onChange={upd(r, "status")} options={[["draft", L("مسودة", "Draft")], ["sent", L("أُرسل", "Sent")], ["answered", L("تم الرد", "Answered")]]} /></td>
              <td style={{ minWidth: 200 }}><TextIn multiline value={r.answer} onCommit={upd(r, "answer")} disabled={dis} /></td>
              <td style={{ minWidth: 180 }}><TextIn value={r.pricing_impact} onCommit={upd(r, "pricing_impact")} disabled={dis} placeholder={L("مثال: زيادة سمك البلاطة", "e.g. thicker slab")} /></td>
            </tr>))}</tbody>
        </table></div>
      )}
      {letter && <Modal title={L("خطاب الاستفسارات", "Clarification letter")} onClose={() => setLetter(null)}><pre className="letter">{letter}</pre>
        <button onClick={() => navigator.clipboard?.writeText(letter)}>{L("نسخ", "Copy")}</button></Modal>}
    </Card>
  );
}

function Chat() {
  const { tender } = useTender();
  const { L } = useI18n();
  const { run, busy } = useAction();
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<any[]>([]);
  const ask = async () => {
    const question = q;
    setQ("");
    setMsgs((m) => [...m, { me: true, text: question }]);
    const r = await run(() => api.post(`/tenders/${tender.id}/chat`, { question }));
    if (r) setMsgs((m) => [...m, { text: r.answer, sources: r.sources, engine: r.engine }]);
  };
  return (
    <Card title={L("مساعد المحادثة على مستندات المناقصة", "Ask the tender documents")}>
      <div className="chat">
        {!msgs.length && <p className="muted">{L("مثال: كم غرامة التأخير؟ — ما مواصفات العزل؟", "e.g. What is the delay penalty? — What are the insulation specs?")}</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.me ? "me" : ""}`}>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
            {m.sources?.map((s: any, j: number) => <div key={j} className="small" style={{ marginTop: 6 }}><SourceRef file={s.file} page={s.page} /> <span className="muted">{s.quote}</span></div>)}
          </div>))}
      </div>
      <div className="row gap" style={{ marginTop: 10 }}>
        <input className="grow" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && q && ask()} placeholder={L("اكتب سؤالك بالعربي أو الإنجليزي", "Ask in Arabic or English")} />
        <button className="primary" disabled={!q || busy} onClick={ask}>{L("اسأل", "Ask")}</button>
      </div>
    </Card>
  );
}

export default function Analysis() {
  const [n, setN] = useState(0);
  return (
    <div className="stack">
      <Suggestions onChange={() => setN((x) => x + 1)} />
      <div className="grid2"><Summary /><Chat /></div>
      <Risks n={n} />
      <Rfis n={n} />
    </div>
  );
}
