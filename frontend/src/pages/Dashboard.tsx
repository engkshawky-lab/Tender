import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { Badge, Card, Empty, Field, Modal, Select, Stat, useAction, useCan, useFmt, useLoad } from "../ui";

function NewTender({ onClose }: { onClose: () => void }) {
  const { L } = useI18n();
  const nav = useNavigate();
  const { run, busy } = useAction();
  const [f, setF] = useState<any>({ project_type: "building", client_type: "private", base_currency: "EGP" });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e?.target ? e.target.value : e });
  const save = async () => {
    const t = await run(() => api.post("/tenders", f));
    if (t) nav(`/tenders/${t.id}`);
  };
  return (
    <Modal title={L("تسجيل مناقصة جديدة", "Register a new tender")} onClose={onClose}>
      <div className="form">
        <Field label={L("اسم المناقصة / المشروع", "Tender / project name")} wide><input value={f.name || ""} onChange={set("name")} /></Field>
        <Field label={L("نوع المشروع", "Project type")}>
          <Select value={f.project_type} onChange={set("project_type")} options={[
            ["building", L("متكامل (حفر وخرسانات + تشطيبات + MEP + فرش)", "Integrated (structure + finishes + MEP + FF&E)")],
            ["infra", L("بنية تحتية (ميكانيكا + كهرباء + شبكات + طرق)", "Infrastructure (mech + elec + networks + roads)")]]} />
        </Field>
        <Field label={L("المالك", "Owner")}><input value={f.owner || ""} onChange={set("owner")} /></Field>
        <Field label={L("الاستشاري", "Consultant")}><input value={f.consultant || ""} onChange={set("consultant")} /></Field>
        <Field label={L("الموقع", "Location")}><input value={f.location || ""} onChange={set("location")} /></Field>
        <Field label={L("موعد التقديم", "Submission date")}><input type="date" value={f.submission_date || ""} onChange={set("submission_date")} /></Field>
        <Field label={L("زيارة الموقع", "Site visit")}><input type="date" value={f.site_visit_date || ""} onChange={set("site_visit_date")} /></Field>
        <Field label={L("آخر موعد للاستفسارات", "Clarification deadline")}><input type="date" value={f.rfi_deadline || ""} onChange={set("rfi_deadline")} /></Field>
        <Field label={L("قيمة التأمين الابتدائي", "Bid bond amount")}><input type="number" value={f.bid_bond_amount || ""} onChange={set("bid_bond_amount")} /></Field>
      </div>
      <p className="muted small">{L("يمكن ملء باقي البيانات تلقائيًا من خطاب الدعوة أو الشروط عبر تحليل المستندات.", "Remaining fields can be auto-filled from the invitation / conditions via document analysis.")}</p>
      <div className="row gap"><button className="primary" disabled={!f.name || busy} onClick={save}>{L("حفظ وفتح الملف", "Save & open")}</button></div>
    </Modal>
  );
}

export default function Dashboard() {
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const [d] = useLoad<any>("/dashboard");
  const [tenders] = useLoad<any[]>("/tenders");
  const [show, setShow] = useState(false);
  const [filter, setFilter] = useState("active");
  const active = ["intake", "go_no_go", "study", "pricing", "review", "approved"];
  const list = (tenders || []).filter((t) => filter === "all" || (filter === "active" ? active.includes(t.status) : t.status === filter));
  const typeLbl: Record<string, string> = { site_visit: L("زيارة موقع", "Site visit"), rfi_deadline: L("آخر موعد استفسارات", "Clarification deadline"), submission: L("موعد تقديم", "Submission") };
  return (
    <div className="stack">
      <div className="page-h">
        <div><h1>{L("لوحة متابعة العطاءات", "Tenders dashboard")}</h1><div className="sub">{L("كل مناقصة من الاستلام حتى تحليل النتيجة — 5 مراحل، 20 خطوة", "Each tender from invitation to result — 5 stages, 20 steps")}</div></div>
        {can("tender.manage") && <button className="primary" onClick={() => setShow(true)}>+ {L("مناقصة جديدة", "New tender")}</button>}
      </div>
      {d && (
        <div className="grid4">
          <Stat label={L("مناقصات جارية", "Active tenders")} value={d.active} tone="hl" />
          <Stat label={L("نسبة الفوز", "Win rate")} value={d.win_rate == null ? "—" : fmt.p(d.win_rate, 0)} sub={`${d.won} ${L("فوز", "won")} · ${d.lost} ${L("خسارة", "lost")}`} />
          <Stat label={L("قبول اقتراحات الـ AI", "AI suggestion acceptance")} value={d.ai_acceptance_rate == null ? "—" : fmt.p(d.ai_acceptance_rate, 0)} sub={`${d.ai_decided} ${L("قرار", "decisions")} · ${d.ai_engine}`} />
          <Stat label={L("مواعيد خلال 3 أسابيع", "Deadlines in 3 weeks")} value={d.alerts.length} tone={d.alerts.some((a: any) => a.days <= 3) ? "hl" : ""} />
        </div>
      )}
      <div className="grid2">
        <Card title={L("تنبيهات المواعيد", "Deadline alerts")}>
          {!d?.alerts.length ? <Empty>{L("لا مواعيد قريبة", "No upcoming deadlines")}</Empty> : (
            <table><tbody>{d.alerts.map((a: any, i: number) => (
              <tr key={i}><td><Badge tone={a.days <= 3 ? "err" : a.days <= 7 ? "warn" : ""}>{a.days < 0 ? L("أمس", "yesterday") : a.days === 0 ? L("اليوم", "today") : `${a.days} ${L("يوم", "days")}`}</Badge></td>
                <td>{typeLbl[a.type]}</td><td><Link to={`/tenders/${a.tender_id}`}>{a.code}</Link> — {a.name}</td><td className="n">{fmt.d(a.date)}</td></tr>))}</tbody></table>
          )}
        </Card>
        <Card title={L("مهامي", "My tasks")}>
          {!d?.my_tasks.length ? <Empty>{L("لا مهام مفتوحة", "No open tasks")}</Empty> : (
            <table><tbody>{d.my_tasks.map((t: any) => (
              <tr key={t.id}><td><Link to={`/tenders/${t.tender_id}`}>{t.tender_code}</Link></td><td>{t.title}</td><td className="n">{fmt.d(t.due_date)}</td></tr>))}</tbody></table>
          )}
        </Card>
      </div>
      <Card title={L("سجل المناقصات", "Tender register")} actions={
        <Select value={filter} onChange={setFilter} options={[["active", L("الجارية", "Active")], ["all", L("الكل", "All")],
          ...["submitted", "won", "lost", "declined", "historical"].map((s) => [s, lab(s)] as [string, string])]} />}>
        <div className="tbl-wrap card-b flush">
          {!list.length ? <Empty>{L("لا توجد مناقصات", "No tenders")}</Empty> : (
            <table>
              <thead><tr><th>{L("الكود", "Code")}</th><th>{L("المناقصة", "Tender")}</th><th>{L("النوع", "Type")}</th><th>{L("المالك", "Owner")}</th>
                <th>{L("الحالة", "Status")}</th><th>{L("التقديم", "Submission")}</th>{can("markup.view") && <th className="n">{L("الإجمالي المعتمد", "Approved total")}</th>}</tr></thead>
              <tbody>{list.map((t) => (
                <tr key={t.id}>
                  <td><Link to={`/tenders/${t.id}`}>{t.code}</Link></td><td>{t.name}</td><td>{lab(t.project_type)}</td><td>{t.owner}</td>
                  <td><Badge k={t.status} /></td>
                  <td>{fmt.d(t.submission_date)} {t.days_to_submission != null && t.days_to_submission >= 0 && active.includes(t.status) && <span className="muted small">({t.days_to_submission} {L("يوم", "d")})</span>}</td>
                  {can("markup.view") && <td className="n">{t.approved_total ? `${fmt.m(t.approved_total)} (V${t.approved_version})` : "—"}</td>}
                </tr>))}</tbody>
            </table>
          )}
        </div>
      </Card>
      {show && <NewTender onClose={() => setShow(false)} />}
    </div>
  );
}
