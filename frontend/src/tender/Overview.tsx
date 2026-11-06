import { useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Badge, Card, Empty, Field, Select, TextIn, useAction, useCan, useFmt, useLoad } from "../ui";
import { useTender } from "./TenderPage";

function Intake() {
  const { tender, reload } = useTender();
  const { L } = useI18n();
  const can = useCan();
  const { run } = useAction();
  const dis = !can("tender.manage");
  const save = (k: string) => (v: any) => run(async () => { await api.patch(`/tenders/${tender.id}`, { [k]: v }); reload(); });
  const txt = (k: string, label: string) => <Field label={label}><TextIn value={tender[k]} onCommit={save(k)} disabled={dis} /></Field>;
  const dt = (k: string, label: string) => <Field label={label}><input type="date" value={tender[k] || ""} disabled={dis} onChange={(e) => save(k)(e.target.value || null)} /></Field>;
  return (
    <Card title={L("1) بيانات المناقصة والمواعيد", "1) Tender data & dates")}>
      <div className="form">
        {txt("name", L("الاسم", "Name"))}
        {txt("owner", L("المالك", "Owner"))}
        {txt("consultant", L("الاستشاري", "Consultant"))}
        {txt("location", L("الموقع", "Location"))}
        <Field label={L("نوع المشروع", "Project type")}>
          <Select value={tender.project_type} disabled={dis} onChange={save("project_type")} options={[["building", L("متكامل", "Integrated")], ["infra", L("بنية تحتية", "Infrastructure")]]} />
        </Field>
        <Field label={L("نوع العميل", "Client")}>
          <Select value={tender.client_type} disabled={dis} onChange={save("client_type")} options={[["private", L("قطاع خاص", "Private")], ["government", L("حكومي", "Government")]]} />
        </Field>
        {dt("invitation_date", L("تاريخ الدعوة", "Invitation date"))}
        {dt("site_visit_date", L("زيارة الموقع", "Site visit"))}
        {dt("rfi_deadline", L("آخر موعد للاستفسارات", "Clarification deadline"))}
        {dt("submission_date", L("موعد التقديم", "Submission date"))}
        <Field label={L("التأمين الابتدائي", "Bid bond")}><input type="number" defaultValue={tender.bid_bond_amount ?? ""} disabled={dis} onBlur={(e) => save("bid_bond_amount")(e.target.value || null)} /></Field>
        <Field label={L("صلاحية العرض (يوم)", "Bid validity (days)")}><input type="number" defaultValue={tender.bid_validity_days ?? ""} disabled={dis} onBlur={(e) => save("bid_validity_days")(e.target.value || null)} /></Field>
        <Field label={L("مدة التنفيذ (شهر)", "Duration (months)")}><input type="number" defaultValue={tender.duration_months ?? ""} disabled={dis} onBlur={(e) => save("duration_months")(e.target.value || null)} /></Field>
        <Field label={L("عملة التسعير", "Base currency")}><TextIn value={tender.base_currency} onCommit={save("base_currency")} disabled={dis} /></Field>
        <Field label={L("وصف", "Description")} wide><TextIn multiline value={tender.description} onCommit={save("description")} disabled={dis} /></Field>
      </div>
    </Card>
  );
}

function GoNoGo() {
  const { tender, reload } = useTender();
  const { L, lang } = useI18n();
  const can = useCan();
  const fmt = useFmt();
  const { run, busy } = useAction();
  const [settings] = useLoad<any>("/settings");
  const [hist] = useLoad<any>(`/tenders/${tender.id}/gonogo/history`);
  const g = tender.gonogo || {};
  const [scores, setScores] = useState<Record<string, number>>(g.scores || {});
  const [reason, setReason] = useState(g.reason || "");
  const cfg = settings?.gonogo;
  if (!cfg) return null;
  const totalW = cfg.criteria.reduce((s: number, c: any) => s + c.weight, 0) || 1;
  const weighted = cfg.criteria.reduce((s: number, c: any) => s + (c.weight * (scores[c.key] || 0)) / 5, 0) / totalW * 100;
  const decide = (decision?: string) => run(async () => {
    await api.post(`/tenders/${tender.id}/gonogo`, { scores, reason, decision });
    reload();
  }, L("تم تسجيل القرار", "Decision recorded"));
  return (
    <Card title={L("2) قرار الدخول (Go / No-Go)", "2) Go / No-Go decision")} actions={g.decision && <Badge k={g.decision === "go" ? "go" : "no_go"}>{g.decision === "go" ? "GO" : "NO-GO"} · {g.weighted}%</Badge>}>
      <table>
        <thead><tr><th>{L("المعيار", "Criterion")}</th><th className="n">{L("الوزن", "Weight")}</th><th>{L("الدرجة (1–5)", "Score (1–5)")}</th></tr></thead>
        <tbody>{cfg.criteria.map((c: any) => (
          <tr key={c.key}><td>{lang === "ar" ? c.ar : c.en}</td><td className="n">{c.weight}%</td>
            <td><div className="row gap">{[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={`sm ${scores[c.key] === n ? "primary" : ""}`} disabled={!can("gonogo.decide")} onClick={() => setScores({ ...scores, [c.key]: n })}>{n}</button>))}</div></td></tr>))}
          <tr className="tot"><td>{L("الدرجة المرجحة", "Weighted score")}</td><td className="n" colSpan={2}>{fmt.p(weighted)} <span className="muted small">({L("حد القبول", "threshold")} {cfg.threshold_pct}%)</span></td></tr>
        </tbody>
      </table>
      {hist && (hist.similar.length > 0) && (
        <div className="alert ai" style={{ marginTop: 12 }}>
          {L("مناقصات مشابهة سابقة:", "Similar past tenders:")} {hist.similar.length} · {L("نسبة الفوز", "win rate")} {hist.win_rate == null ? "—" : fmt.p(hist.win_rate, 0)}
          {hist.avg_score != null && ` · ${L("متوسط درجتها", "avg score")} ${fmt.p(hist.avg_score)}`}
        </div>
      )}
      <Field label={L("سبب القرار (إلزامي)", "Reason (required)")} wide><textarea value={reason} onChange={(e) => setReason(e.target.value)} disabled={!can("gonogo.decide")} /></Field>
      {can("gonogo.decide") && (
        <div className="row gap" style={{ marginTop: 10 }}>
          <button className="ok" disabled={busy || !reason} onClick={() => decide("go")}>GO — {L("الدخول", "Bid")}</button>
          <button className="danger" disabled={busy || !reason} onClick={() => decide("no_go")}>NO-GO — {L("اعتذار وأرشفة", "Decline & archive")}</button>
        </div>
      )}
      {g.by && <p className="muted small">{L("القرار بواسطة", "Decided by")} {g.by} · {fmt.d(g.at)}</p>}
      {g.apology_letter && <><h4 style={{ margin: "12px 0 6px" }}>{L("خطاب الاعتذار", "Apology letter")}</h4><pre className="letter">{g.apology_letter}</pre></>}
    </Card>
  );
}

function Tasks() {
  const { tender } = useTender();
  const { L } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [tasks, reload] = useLoad<any[]>(`/tenders/${tender.id}/tasks`);
  const [users] = useLoad<any[]>("/users");
  const [f, setF] = useState<any>({});
  const add = () => run(async () => { await api.post(`/tenders/${tender.id}/tasks`, f); setF({}); reload(); });
  const names = Object.fromEntries((users || []).map((u) => [u.id, u.full_name || u.username]));
  return (
    <Card title={L("توزيع المهام", "Task assignment")}>
      {!tasks?.length ? <Empty>{L("لا مهام", "No tasks")}</Empty> : (
        <table><tbody>{tasks.map((t) => (
          <tr key={t.id}>
            <td><input type="checkbox" checked={t.status === "done"} onChange={(e) => run(async () => { await api.patch(`/tasks/${t.id}`, { status: e.target.checked ? "done" : "open" }); reload(); })} /></td>
            <td style={{ textDecoration: t.status === "done" ? "line-through" : "" }}>{t.title}</td>
            <td className="muted">{t.step ? `${L("خطوة", "step")} ${t.step}` : ""}</td><td>{names[t.assignee_id] || "—"}</td><td className="n">{fmt.d(t.due_date)}</td>
          </tr>))}</tbody></table>
      )}
      {can("tender.manage") && (
        <div className="row gap wrap" style={{ marginTop: 10 }}>
          <input placeholder={L("المهمة", "Task")} value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} className="grow" />
          <select value={f.assignee_id || ""} onChange={(e) => setF({ ...f, assignee_id: e.target.value })}>
            <option value="">{L("المسؤول", "Assignee")}</option>{(users || []).map((u) => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
          </select>
          <input type="number" placeholder={L("الخطوة", "Step")} className="num sm" value={f.step || ""} onChange={(e) => setF({ ...f, step: e.target.value })} />
          <input type="date" value={f.due_date || ""} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
          <button className="primary" disabled={!f.title} onClick={add}>{L("إضافة", "Add")}</button>
        </div>
      )}
    </Card>
  );
}

export default function Overview() {
  return <div className="stack"><Intake /><div className="grid2"><GoNoGo /><Tasks /></div></div>;
}
