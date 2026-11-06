import { useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Badge, Card, Empty, Field, FileButton, Modal, Select, useAction, useCan, useFmt, useLoad } from "../ui";

const STATUS: Record<string, [string, string, string]> = {
  approved: ["معتمد", "Approved", "ok"], pending: ["تحت الاعتماد", "Pending", "warn"],
  suspended: ["موقوف", "Suspended", "warn"], blacklisted: ["قائمة سوداء", "Blacklisted", "err"],
};
const DOC_KINDS: Record<string, [string, string]> = {
  commercial_register: ["سجل تجاري", "Commercial register"], tax_card: ["بطاقة ضريبية", "Tax card"], iso: ["شهادة ISO", "ISO certificate"],
  catalogue: ["كتالوج / بيانات فنية", "Catalogue / data sheet"], approval_letter: ["خطاب اعتماد من مالك / استشاري", "Owner / consultant approval"], other: ["أخرى", "Other"],
};

function VendorForm({ v, onClose, onSaved }: { v: any; onClose: () => void; onSaved: () => void }) {
  const { L } = useI18n();
  const { run } = useAction();
  const [f, setF] = useState<any>({ kind: "supplier", trades: [], project_types: [], ...v });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e?.target ? e.target.value : e });
  const save = () => run(async () => {
    if (f.id) await api.patch(`/suppliers/${f.id}`, f); else await api.post("/suppliers", f);
    onSaved(); onClose();
  }, L("تم الحفظ", "Saved"));
  const toggle = (pt: string) => setF({ ...f, project_types: f.project_types.includes(pt) ? f.project_types.filter((x: string) => x !== pt) : [...f.project_types, pt] });
  return (
    <Modal wide title={f.id ? f.name : L("إضافة مورد / مقاول باطن", "Add supplier / subcontractor")} onClose={onClose}>
      <div className="form">
        <Field label={L("الاسم", "Name")}><input value={f.name || ""} onChange={set("name")} /></Field>
        <Field label={L("النوع", "Kind")}><Select value={f.kind} onChange={set("kind")} options={[["supplier", L("مورد", "Supplier")], ["subcontractor", L("مقاول باطن", "Subcontractor")], ["both", L("مورد ومقاول", "Both")]]} /></Field>
        <Field label={L("التخصصات (مفصولة بفاصلة)", "Trades (comma separated)")}><input value={(f.trades || []).join(", ")} onChange={(e) => setF({ ...f, trades: e.target.value.split(/[,،]/).map((x) => x.trim()).filter(Boolean) })} placeholder="HVAC, Electrical, Finishes…" /></Field>
        <Field label={L("نوع المشاريع", "Project types")}><div className="row gap">
          <label className="row gap"><input type="checkbox" checked={f.project_types.includes("building")} onChange={() => toggle("building")} />{L("متكامل", "Integrated")}</label>
          <label className="row gap"><input type="checkbox" checked={f.project_types.includes("infra")} onChange={() => toggle("infra")} />{L("بنية تحتية", "Infra")}</label></div></Field>
        <Field label={L("الماركات / المصانع", "Brands / manufacturers")}><input value={f.brands || ""} onChange={set("brands")} /></Field>
        <Field label={L("مسؤول التواصل", "Contact")}><input value={f.contact_name || ""} onChange={set("contact_name")} /></Field>
        <Field label={L("الهاتف", "Phone")}><input value={f.phone || ""} onChange={set("phone")} /></Field>
        <Field label={L("البريد", "E-mail")}><input value={f.email || ""} onChange={set("email")} /></Field>
        <Field label={L("السجل التجاري", "Commercial register")}><input value={f.commercial_register || ""} onChange={set("commercial_register")} /></Field>
        <Field label={L("البطاقة الضريبية", "Tax card")}><input value={f.tax_card || ""} onChange={set("tax_card")} /></Field>
        <Field label={L("معتمد لدى (ملاك / استشاريين)", "Approved by owners / consultants")}><input value={f.approved_by || ""} onChange={set("approved_by")} /></Field>
        <Field label={L("شروط الدفع المعتادة", "Usual payment terms")}><input value={f.payment_terms || ""} onChange={set("payment_terms")} /></Field>
        <Field label={L("العنوان", "Address")} wide><input value={f.address || ""} onChange={set("address")} /></Field>
        <Field label={L("ملاحظات", "Notes")} wide><textarea value={f.notes || ""} onChange={set("notes")} /></Field>
      </div>
      <button className="primary" style={{ marginTop: 10 }} disabled={!f.name} onClick={save}>{L("حفظ", "Save")}</button>
      {!f.id && <p className="muted small">{L("المورد الجديد يُسجل «تحت الاعتماد» حتى تعتمده الإدارة.", "New vendors start as Pending until management approves them.")}</p>}
    </Modal>
  );
}

function VendorFile({ v, onClose, onChanged }: { v: any; onClose: () => void; onChanged: () => void }) {
  const { L, lang } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [docs, reloadD] = useLoad<any[]>(`/suppliers/${v.id}/documents`);
  const [evals, reloadE] = useLoad<any[]>(`/suppliers/${v.id}/evaluations`);
  const [tenders] = useLoad<any[]>("/tenders");
  const [kind, setKind] = useState("commercial_register");
  const [exp, setExp] = useState("");
  const [ev, setEv] = useState<any>({ quality: 4, delivery: 4, price: 4, cooperation: 4 });
  const [reason, setReason] = useState("");
  const [months, setMonths] = useState(12);
  const status = (st: string) => run(async () => { await api.post(`/suppliers/${v.id}/status`, { status: st, reason, valid_months: months }); onChanged(); onClose(); }, L("تم تحديث الحالة", "Status updated"));
  return (
    <Modal wide title={<span>{v.name} <Badge tone={STATUS[v.status][2]}>{STATUS[v.status][lang === "ar" ? 0 : 1]}</Badge></span>} onClose={onClose}>
      <div className="stack">
        {can("vendors.approve") && (
          <Card title={L("قرار الاعتماد", "Approval decision")}>
            <div className="row gap wrap">
              <label className="row gap small">{L("صلاحية الاعتماد (شهر)", "Valid for (months)")}<input className="num sm" type="number" value={months} onChange={(e) => setMonths(Number(e.target.value))} /></label>
              <input className="grow" placeholder={L("السبب / الملاحظة (إلزامي للإيقاف والقائمة السوداء)", "Reason (required to suspend / blacklist)")} value={reason} onChange={(e) => setReason(e.target.value)} />
              <button className="ok" onClick={() => status("approved")}>{L("اعتماد", "Approve")}</button>
              <button onClick={() => status("suspended")} disabled={!reason}>{L("إيقاف", "Suspend")}</button>
              <button className="danger" onClick={() => status("blacklisted")} disabled={!reason}>{L("قائمة سوداء", "Blacklist")}</button>
            </div>
            {v.approval_date && <p className="muted small">{L("معتمد منذ", "Approved on")} {fmt.d(v.approval_date)} · {L("حتى", "until")} {fmt.d(v.approval_expiry)}</p>}
          </Card>
        )}
        <Card title={L("المستندات (بتاريخ انتهاء)", "Documents (with expiry)")} actions={can("procurement.manage") && <>
          <Select value={kind} onChange={setKind} options={Object.entries(DOC_KINDS).map(([k, l]) => [k, l[lang === "ar" ? 0 : 1]])} />
          <input type="date" value={exp} onChange={(e) => setExp(e.target.value)} title={L("تاريخ الانتهاء", "Expiry")} />
          <FileButton label={L("رفع", "Upload")} onFile={(file) => run(async () => { await api.upload(`/suppliers/${v.id}/documents`, file, { kind, expiry_date: exp }); reloadD(); onChanged(); })} /></>}>
          {!docs?.length ? <Empty>{L("لا مستندات", "No documents")}</Empty> : (
            <table><tbody>{docs.map((d) => {
              const expired = d.expiry_date && new Date(d.expiry_date) < new Date();
              return (
                <tr key={d.id}><td>{DOC_KINDS[d.kind]?.[lang === "ar" ? 0 : 1]}</td><td>{d.filename}</td>
                  <td style={{ color: expired ? "var(--err)" : "" }}>{d.expiry_date ? `${L("ينتهي", "expires")} ${fmt.d(d.expiry_date)}` : "—"}</td>
                  <td><button className="sm" onClick={() => api.download(`/supplier-documents/${d.id}/file`, d.filename)}>{L("تنزيل", "Download")}</button></td></tr>);
            })}</tbody></table>
          )}
        </Card>
        <Card title={L("تقييم الأداء بعد التوريد / التنفيذ", "Performance evaluations")}>
          {evals?.length ? (
            <table><thead><tr><th>{L("التاريخ", "Date")}</th><th>{L("المشروع", "Project")}</th><th>{L("الجودة", "Quality")}</th><th>{L("الالتزام بالمواعيد", "Delivery")}</th><th>{L("السعر", "Price")}</th><th>{L("التعاون", "Cooperation")}</th><th>{L("المتوسط", "Avg")}</th><th>{L("تعليق", "Comment")}</th></tr></thead>
              <tbody>{evals.map((e) => <tr key={e.id}><td>{fmt.d(e.eval_date)}</td><td>{e.tender_code || "—"}</td><td>{e.quality}</td><td>{e.delivery}</td><td>{e.price}</td><td>{e.cooperation}</td><td><b>{e.average.toFixed(1)}</b></td><td>{e.comment}</td></tr>)}</tbody></table>
          ) : <Empty>{L("لا تقييمات", "No evaluations")}</Empty>}
          {can("procurement.manage") && (
            <div className="row gap wrap" style={{ marginTop: 10 }}>
              <select value={ev.tender_id || ""} onChange={(e) => setEv({ ...ev, tender_id: e.target.value || null })}><option value="">{L("المشروع", "Project")}</option>{(tenders || []).map((t) => <option key={t.id} value={t.id}>{t.code}</option>)}</select>
              {(["quality", "delivery", "price", "cooperation"] as const).map((k) => (
                <label key={k} className="row gap small">{{ quality: L("الجودة", "Quality"), delivery: L("المواعيد", "Delivery"), price: L("السعر", "Price"), cooperation: L("التعاون", "Coop.") }[k]}
                  <select value={ev[k]} onChange={(e) => setEv({ ...ev, [k]: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}</select></label>))}
              <input placeholder={L("تعليق", "Comment")} value={ev.comment || ""} onChange={(e) => setEv({ ...ev, comment: e.target.value })} />
              <button className="primary" onClick={() => run(async () => { await api.post(`/suppliers/${v.id}/evaluations`, ev); reloadE(); onChanged(); }, L("تم حفظ التقييم", "Evaluation saved"))}>{L("إضافة تقييم", "Add evaluation")}</button>
            </div>
          )}
        </Card>
      </div>
    </Modal>
  );
}

export default function Vendors() {
  const { L, lang } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const [f, setF] = useState({ q: "", status: "", trade: "", project_type: "" });
  const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  const [rows, reload] = useLoad<any[]>(`/suppliers${qs ? `?${qs}` : ""}`);
  const [alerts] = useLoad<any[]>("/suppliers-alerts?days=45");
  const [edit, setEdit] = useState<any>(null);
  const [open, setOpen] = useState<any>(null);
  const counts = Object.keys(STATUS).map((s) => [s, (rows || []).filter((r) => r.status === s).length]);
  return (
    <div className="stack">
      <div className="page-h">
        <div><h1>{L("سجل الموردين ومقاولي الباطن المعتمدين", "Approved vendor list")}</h1><div className="sub">{L("الاعتماد والمستندات وتقييم الأداء — ويظهر تنبيه في جدول المقارنة إذا كان المورد غير معتمد", "Approval, documents and performance — the comparison sheet warns when a vendor is not approved")}</div></div>
        {can("procurement.manage") && <button className="primary" onClick={() => setEdit({})}>+ {L("إضافة مورد", "Add vendor")}</button>}
      </div>
      {!!alerts?.length && (
        <div className="alert">{L("تنبيهات انتهاء الاعتماد والمستندات:", "Expiring approvals & documents:")} {alerts.map((a, i) => (
          <span key={i} className="badge warn" style={{ margin: 3 }}>{a.supplier} — {a.type === "approval" ? L("الاعتماد", "approval") : a.title || a.type} {fmt.d(a.date)}{a.expired ? ` (${L("منتهي", "expired")})` : ""}</span>))}</div>
      )}
      <Card actions={null} title={<div className="row gap wrap">{counts.map(([s, n]) => <Badge key={s} tone={STATUS[s as string][2]}>{STATUS[s as string][lang === "ar" ? 0 : 1]}: {n}</Badge>)}</div>}>
        <div className="row gap wrap" style={{ marginBottom: 10 }}>
          <input placeholder={L("بحث بالاسم أو الماركة", "Search name or brand")} value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
          <Select value={f.status} onChange={(v) => setF({ ...f, status: v })} options={[["", L("كل الحالات", "All statuses")], ...Object.entries(STATUS).map(([k, l]) => [k, l[lang === "ar" ? 0 : 1]] as [string, string])]} />
          <input placeholder={L("التخصص", "Trade")} value={f.trade} onChange={(e) => setF({ ...f, trade: e.target.value })} />
          <Select value={f.project_type} onChange={(v) => setF({ ...f, project_type: v })} options={[["", L("كل أنواع المشاريع", "All project types")], ["building", L("متكامل", "Integrated")], ["infra", L("بنية تحتية", "Infra")]]} />
        </div>
        {!rows?.length ? <Empty>{L("لا موردين", "No vendors")}</Empty> : (
          <div className="tbl-wrap"><table>
            <thead><tr><th>{L("الاسم", "Name")}</th><th>{L("الحالة", "Status")}</th><th>{L("النوع", "Kind")}</th><th>{L("التخصصات", "Trades")}</th><th>{L("التقييم", "Rating")}</th>
              <th>{L("الاعتماد حتى", "Approved until")}</th><th>{L("معتمد لدى", "Approved by")}</th><th className="n">{L("مستندات", "Docs")}</th><th className="n">{L("عروض", "Quotes")}</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td><b>{r.name}</b><div className="small muted">{r.contact_name} {r.phone}</div></td>
                <td><Badge tone={STATUS[r.status][2]}>{STATUS[r.status][lang === "ar" ? 0 : 1]}</Badge>{r.status === "approved" && !r.approval_valid && <Badge tone="err">{L("منتهي", "expired")}</Badge>}</td>
                <td>{r.kind === "subcontractor" ? L("مقاول باطن", "Subcontractor") : r.kind === "both" ? L("الاثنين", "Both") : L("مورد", "Supplier")}</td>
                <td className="small">{(r.trades || []).join("، ")}</td>
                <td>{"★".repeat(Math.round(r.rating))}<span className="muted small"> {r.rating}</span></td>
                <td>{fmt.d(r.approval_expiry)}</td><td className="small">{r.approved_by}</td><td className="n">{r.documents}</td><td className="n">{r.quotations}</td>
                <td className="row gap"><button className="sm" onClick={() => setOpen(r)}>{L("الملف", "File")}</button>
                  {can("procurement.manage") && <button className="sm ghost" onClick={() => setEdit(r)}>{L("تعديل", "Edit")}</button>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
      {edit && <VendorForm v={edit} onClose={() => setEdit(null)} onSaved={reload} />}
      {open && <VendorFile v={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  );
}
