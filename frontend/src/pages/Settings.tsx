import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Card, Field, Modal, NumIn, Tabs, useAction, useAuth, useCan, useLoad } from "../ui";

const PARAM_LABELS: Record<string, [string, string]> = {
  markup_pct: ["نسبة الربح الافتراضية %", "Default markup %"], ho_overhead_pct: ["مصاريف المكتب الرئيسي %", "HO overheads %"],
  general_contingency_pct: ["طوارئ عامة %", "General contingency %"], material_escalation_pct: ["زيادة الخامات %", "Material escalation %"],
  fx_buffer_pct: ["هامش سعر الصرف %", "FX buffer %"], performance_bond_pct: ["الضمان النهائي %", "Performance bond %"],
  advance_guarantee_pct: ["ضمان الدفعة المقدمة %", "Advance guarantee %"], bond_commission_pa_pct: ["عمولة البنك السنوية %", "Bank commission % p.a."],
  insurance_pct: ["التأمين %", "Insurance %"], maintenance_months: ["فترة الصيانة (شهر)", "Maintenance (months)"], bid_validity_days: ["صلاحية العرض (يوم)", "Bid validity (days)"],
  advance_payment_pct: ["الدفعة المقدمة %", "Advance payment %"], retention_pct: ["الاستقطاع %", "Retention %"], payment_delay_months: ["تأخر الصرف (شهر)", "Payment delay (months)"],
  finance_rate_pa_pct: ["تكلفة التمويل السنوية %", "Finance rate % p.a."], rate_decimals: ["عدد الكسور في الأسعار", "Rate decimals"],
};

function CompanySettings() {
  const { L, lang } = useI18n();
  const can = useCan();
  const { run } = useAction();
  const [s, reload] = useLoad<any>("/settings");
  const [json, setJson] = useState<{ key: string; text: string } | null>(null);
  const dis = !can("settings.manage");
  if (!s) return null;
  const put = (key: string, value: any) => run(async () => { await api.put(`/settings/${key}`, value); reload(); }, L("تم الحفظ", "Saved"));
  return (
    <div className="stack">
      <Card title={L("النسب الافتراضية لكل تسعير جديد", "Default ratios for new estimates")}>
        <div className="form">{Object.entries(PARAM_LABELS).map(([k, l]) => (
          <Field key={k} label={l[lang === "ar" ? 0 : 1]}><NumIn value={s.pricing_defaults[k]} disabled={dis} onCommit={(v) => put("pricing_defaults", { ...s.pricing_defaults, [k]: v })} /></Field>))}</div>
      </Card>
      <div className="grid2">
        <Card title={L("الضرائب والرسوم (تُضبط حسب القانون الساري)", "Taxes & duties (set per current law)")}>
          <table><tbody>{s.taxes.map((t: any, i: number) => (
            <tr key={i}><td><input value={t.name} disabled={dis} onChange={(e) => { const x = [...s.taxes]; x[i] = { ...t, name: e.target.value }; s.taxes = x; }} onBlur={() => put("taxes", s.taxes)} /></td>
              <td><NumIn className="sm" value={t.rate_pct} disabled={dis} onCommit={(v) => { const x = [...s.taxes]; x[i] = { ...t, rate_pct: v }; put("taxes", x); }} /></td>
              <td><select value={t.mode} disabled={dis} onChange={(e) => { const x = [...s.taxes]; x[i] = { ...t, mode: e.target.value }; put("taxes", x); }}>
                <option value="on_top">{L("تضاف على الإجمالي", "On top")}</option><option value="in_price">{L("ضمن السعر", "In price")}</option></select></td></tr>))}</tbody></table>
          {!dis && <button className="sm" onClick={() => put("taxes", [...s.taxes, { name: L("ضريبة", "Tax"), rate_pct: 0, mode: "in_price" }])}>+ {L("ضريبة", "Tax")}</button>}
        </Card>
        <Card title={L("أسعار الصرف الافتراضية وحدود التنبيه", "Default FX rates & alert thresholds")}>
          <div className="form">
            {Object.keys(s.fx_rates).filter((k) => k !== "as_of").map((c) => <Field key={c} label={`1 ${c} =`}><NumIn value={s.fx_rates[c]} disabled={dis} onCommit={(v) => put("fx_rates", { ...s.fx_rates, [c]: v, as_of: new Date().toISOString().slice(0, 10) })} /></Field>)}
            <Field label={L("تنبيه السعر الأقدم من (يوم)", "Flag prices older than (days)")}><NumIn value={s.price_age_days} disabled={dis} onCommit={(v) => put("price_age_days", v)} /></Field>
            <Field label={L("تنبيه الانحراف عن الأسعار السابقة %", "Flag deviation from history %")}><NumIn value={s.outlier_pct} disabled={dis} onCommit={(v) => put("outlier_pct", v)} /></Field>
          </div>
          <p className="muted small">{L("آخر تحديث", "Updated")}: {s.fx_rates.as_of}</p>
        </Card>
      </div>
      <Card title={L("معايير قرار الدخول وأوزانها", "Go / No-Go criteria & weights")}>
        <table><tbody>{s.gonogo.criteria.map((c: any, i: number) => (
          <tr key={c.key}><td>{lang === "ar" ? c.ar : c.en}</td><td><NumIn className="sm" value={c.weight} disabled={dis} onCommit={(v) => { const cr = [...s.gonogo.criteria]; cr[i] = { ...c, weight: v }; put("gonogo", { ...s.gonogo, criteria: cr }); }} /></td></tr>))}
          <tr className="tot"><td>{L("حد القبول %", "Threshold %")}</td><td><NumIn className="sm" value={s.gonogo.threshold_pct} disabled={dis} onCommit={(v) => put("gonogo", { ...s.gonogo, threshold_pct: v })} /></td></tr></tbody></table>
      </Card>
      <div className="grid2">
        <Card title={L("تقييم عروض الموردين: فني مقابل مالي", "Quotation evaluation: technical vs financial")}>
          <div className="form">
            <Field label={L("وزن الفني %", "Technical weight %")}><NumIn value={s.quote_evaluation.technical_weight} disabled={dis} onCommit={(v) => put("quote_evaluation", { ...s.quote_evaluation, technical_weight: v })} /></Field>
            <Field label={L("وزن المالي %", "Financial weight %")}><NumIn value={s.quote_evaluation.financial_weight} disabled={dis} onCommit={(v) => put("quote_evaluation", { ...s.quote_evaluation, financial_weight: v })} /></Field>
            <Field label={L("حد النجاح الفني %", "Technical pass mark %")}><NumIn value={s.quote_evaluation.technical_pass_pct} disabled={dis} onCommit={(v) => put("quote_evaluation", { ...s.quote_evaluation, technical_pass_pct: v })} /></Field>
          </div>
          <table style={{ marginTop: 10 }}><tbody>{s.quote_evaluation.criteria.map((c: any, i: number) => (
            <tr key={c.key}><td>{lang === "ar" ? c.ar : c.en}</td><td><NumIn className="sm" value={c.weight} disabled={dis} onCommit={(v) => { const cr = [...s.quote_evaluation.criteria]; cr[i] = { ...c, weight: v }; put("quote_evaluation", { ...s.quote_evaluation, criteria: cr }); }} /></td></tr>))}</tbody></table>
        </Card>
        <Card title={L("مؤشر تكلفة البناء الشهري (لتعديل الأسعار القديمة)", "Monthly construction cost index (to adjust old prices)")}>
          <p className="muted small">{L("مثال: نشرة الجهاز المركزي للتعبئة العامة والإحصاء لأسعار مواد البناء. الصيغة: شهر (YYYY-MM) = قيمة المؤشر.", "e.g. CAPMAS building-materials bulletin. Format: month (YYYY-MM) = index value.")}</p>
          <Field label={L("المصدر", "Source")}><input defaultValue={s.cost_indices.source} disabled={dis} onBlur={(e) => put("cost_indices", { ...s.cost_indices, source: e.target.value })} /></Field>
          <textarea style={{ marginTop: 8, direction: "ltr", fontFamily: "monospace", minHeight: 140 }} disabled={dis}
            defaultValue={Object.entries(s.cost_indices.values || {}).map(([k, v]) => `${k} = ${v}`).join("\n")}
            onBlur={(e) => put("cost_indices", { ...s.cost_indices, values: Object.fromEntries(e.target.value.split("\n").map((l) => l.split("=").map((x) => x.trim())).filter((p) => /^\d{4}-\d{2}$/.test(p[0]) && Number(p[1]) > 0).map((p) => [p[0], Number(p[1])])) })} />
        </Card>
      </div>
      <Card title={L("قوائم وقوالب متقدمة (JSON)", "Advanced lists & templates (JSON)")}>
        <div className="row gap wrap">{["clarifications_library", "site_visit_templates", "indirect_templates", "submission_checklist", "waste_defaults", "company"].map((k) => (
          <button key={k} onClick={() => setJson({ key: k, text: JSON.stringify(s[k], null, 2) })}>{k}</button>))}</div>
      </Card>
      {json && (
        <Modal wide title={json.key} onClose={() => setJson(null)}>
          <textarea style={{ minHeight: 420, fontFamily: "monospace", direction: "ltr" }} value={json.text} onChange={(e) => setJson({ ...json, text: e.target.value })} />
          {!dis && <button className="primary" onClick={() => { try { put(json.key, JSON.parse(json.text)); setJson(null); } catch { alert("JSON error"); } }}>{L("حفظ", "Save")}</button>}
        </Modal>
      )}
    </div>
  );
}

function Users() {
  const { L } = useI18n();
  const can = useCan();
  const { run } = useAction();
  const [users, reload] = useLoad<any[]>("/users");
  const [meta] = useLoad<any>("/meta");
  const [edit, setEdit] = useState<any>(null);
  const dis = !can("users.manage");
  const save = () => run(async () => {
    if (edit.id) await api.patch(`/users/${edit.id}`, edit); else await api.post("/users", edit);
    setEdit(null); reload();
  }, L("تم الحفظ", "Saved"));
  const toggle = (arr: string[] = [], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <Card title={L("المستخدمون — للمستخدم الواحد أكثر من دور، والصلاحيات قابلة للتعديل لكل مستخدم", "Users — one user can hold several roles; permissions are adjustable per user")} actions={!dis && <button onClick={() => setEdit({ roles: [], extra_permissions: [], revoked_permissions: [], is_active: true })}>+ {L("مستخدم", "User")}</button>}>
      <table><thead><tr><th>{L("المستخدم", "User")}</th><th>{L("الأدوار", "Roles")}</th><th>{L("الصلاحيات الفعلية", "Effective permissions")}</th><th /></tr></thead>
        <tbody>{(users || []).map((u) => (
          <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}><td>{u.full_name || u.username}<div className="small muted">{u.username}</div></td>
            <td>{u.roles.join("، ")}</td><td className="small muted">{u.permissions.join(" · ")}</td>
            <td>{!dis && <button className="sm" onClick={() => setEdit({ ...u })}>{L("تعديل", "Edit")}</button>}</td></tr>))}</tbody></table>
      {edit && meta && (
        <Modal wide title={edit.id ? edit.username : L("مستخدم جديد", "New user")} onClose={() => setEdit(null)}>
          <div className="form">
            {!edit.id && <Field label={L("اسم الدخول", "Username")}><input value={edit.username || ""} onChange={(e) => setEdit({ ...edit, username: e.target.value })} /></Field>}
            <Field label={L("الاسم", "Full name")}><input value={edit.full_name || ""} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} /></Field>
            <Field label={L("البريد", "E-mail")}><input value={edit.email || ""} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
            <Field label={L("كلمة المرور", "Password")}><input type="password" value={edit.password || ""} onChange={(e) => setEdit({ ...edit, password: e.target.value })} placeholder={edit.id ? L("اتركه فارغًا لعدم التغيير", "leave empty to keep") : ""} /></Field>
            <Field label={L("نشط", "Active")}><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /></Field>
          </div>
          <h4 style={{ margin: "12px 0 6px" }}>{L("الأدوار", "Roles")}</h4>
          <div className="row gap wrap">{Object.keys(meta.roles).map((r) => (
            <label key={r} className="row gap"><input type="checkbox" checked={edit.roles.includes(r)} onChange={() => setEdit({ ...edit, roles: toggle(edit.roles, r) })} />{r}</label>))}</div>
          <h4 style={{ margin: "12px 0 6px" }}>{L("تعديل صلاحيات هذا المستخدم", "Per-user permission overrides")}</h4>
          <table><thead><tr><th>{L("الصلاحية", "Permission")}</th><th>{L("منح إضافي", "Grant")}</th><th>{L("سحب", "Revoke")}</th></tr></thead>
            <tbody>{Object.entries(meta.permissions).map(([p, desc]: any) => (
              <tr key={p}><td>{p} <span className="muted small">{desc}</span></td>
                <td><input type="checkbox" checked={edit.extra_permissions?.includes(p)} onChange={() => setEdit({ ...edit, extra_permissions: toggle(edit.extra_permissions, p) })} /></td>
                <td><input type="checkbox" checked={edit.revoked_permissions?.includes(p)} onChange={() => setEdit({ ...edit, revoked_permissions: toggle(edit.revoked_permissions, p) })} /></td></tr>))}</tbody></table>
          <button className="primary" style={{ marginTop: 10 }} onClick={save}>{L("حفظ", "Save")}</button>
        </Modal>
      )}
    </Card>
  );
}

function Password() {
  const { L } = useI18n();
  const { run } = useAction();
  const [f, setF] = useState({ old: "", new: "" });
  return (
    <Card title={L("تغيير كلمة المرور", "Change password")}>
      <div className="row gap wrap">
        <input type="password" placeholder={L("الحالية", "Current")} value={f.old} onChange={(e) => setF({ ...f, old: e.target.value })} />
        <input type="password" placeholder={L("الجديدة", "New")} value={f.new} onChange={(e) => setF({ ...f, new: e.target.value })} />
        <button className="primary" disabled={f.new.length < 6} onClick={() => run(() => api.post("/auth/password", f), L("تم التغيير", "Changed"))}>{L("تغيير", "Change")}</button>
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const { L } = useI18n();
  const { me } = useAuth();
  const [tab, setTab] = useState("company");
  useEffect(() => {}, [me]);
  return (
    <div>
      <div className="page-h"><h1>{L("الإعدادات والمستخدمون", "Settings & users")}</h1><div className="sub">{L("النسب والمعايير هنا وليست في الكود", "Ratios and criteria live here, not in code")}</div></div>
      <Tabs tabs={[{ key: "company", label: L("إعدادات الشركة", "Company settings") }, { key: "users", label: L("المستخدمون والصلاحيات", "Users & permissions") }, { key: "me", label: L("حسابي", "My account") }]} active={tab} onChange={setTab} />
      {tab === "company" && <CompanySettings />}
      {tab === "users" && <Users />}
      {tab === "me" && <Password />}
    </div>
  );
}
