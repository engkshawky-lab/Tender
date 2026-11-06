import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { Badge, Card, Empty, Field, NumIn, Select, Stat, Tabs, TextIn, useAction, useCan, useFmt, useLoad } from "../ui";
import BuildUp from "./BuildUp";
import { EstimatePicker, useTender } from "./TenderPage";

const PARTS = ["supply", "apply", "supply_apply"];

// ---------------------------------------------------------------- price analysis with Supply / Apply sub-filter
function PriceAnalysis({ est }: { est: any }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const [f, setF] = useState({ scope: "", kind: "", package_id: "", source: "" });
  const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join("&");
  const [data] = useLoad<any>(`/estimates/${est.id}/analysis${qs ? `?${qs}` : ""}`);
  const [pkgs] = useLoad<any[]>(`/tenders/${tender.id}/packages`);
  return (
    <Card title={L("تحليل الأسعار — فلتر فرعي: توريد / تركيب / توريد وتركيب", "Price analysis — sub-filter: Supply / Apply / Supply + Apply")}>
      <div className="row gap wrap" style={{ marginBottom: 12 }}>
        <div className="row gap">{[["", L("الكل", "All")], ...PARTS.map((p) => [p, lab(p)])].map(([k, l]) => (
          <button key={k} className={f.scope === k ? "primary" : ""} onClick={() => setF({ ...f, scope: k })}>{l}</button>))}</div>
        <Select value={f.kind} onChange={(v) => setF({ ...f, kind: v })} options={[["", L("كل أنواع الموارد", "All resource kinds")], ...["material", "labor", "equipment", "subcontract"].map((k) => [k, lab(k)] as [string, string])]} />
        <Select value={f.package_id} onChange={(v) => setF({ ...f, package_id: v })} options={[["", L("كل الحزم", "All packages")], ...(pkgs || []).map((p) => [String(p.id), p.name] as [string, string])]} />
        <Select value={f.source} onChange={(v) => setF({ ...f, source: v })} options={[["", L("كل مصادر السعر", "All price sources")], ...["quotation", "library", "history", "manual"].map((k) => [k, lab(k)] as [string, string])]} />
      </div>
      {data && (
        <div className="grid4" style={{ marginBottom: 12 }}>
          <Stat label={lab("supply")} value={fmt.m(data.totals.supply)} />
          <Stat label={lab("apply")} value={fmt.m(data.totals.apply)} />
          <Stat label={`${lab("supply_apply")} (${L("سعر مجمع", "combined rate")})`} value={fmt.m(data.totals.supply_apply)} />
          <Stat label={L("إجمالي المعروض", "Total shown")} value={fmt.m(data.totals.total)} tone="hl" />
        </div>
      )}
      {!data?.items.length ? <Empty>{L("لا بنود مطابقة للفلتر", "No items match the filter")}</Empty> : (
        <div className="tbl-wrap" style={{ maxHeight: "65vh" }}><table>
          <thead><tr><th>{L("رقم", "Ref")}</th><th>{L("الوصف", "Description")}</th><th>{L("النطاق", "Scope")}</th><th className="n">{L("الكمية", "Qty")}</th>
            <th className="n">{lab("supply")}</th><th className="n">{lab("apply")}</th><th className="n">{lab("supply_apply")}</th><th className="n">{L("المباشر/وحدة", "Direct/unit")}</th>
            {can("markup.view") && <th className="n">{L("السعر النهائي", "Final rate")}</th>}<th>{L("المكونات", "Lines")}</th></tr></thead>
          <tbody>{data.items.map((it: any) => (
            <tr key={it.id}>
              <td>{it.item_ref}</td><td className="desc small">{it.description.slice(0, 110)}</td><td><Badge k={it.scope} /></td><td className="n">{fmt.n(it.quantity, 0)}</td>
              {PARTS.map((p) => <td key={p} className="n">{it.subtotals[p] ? fmt.n(it.subtotals[p]) : "—"}</td>)}
              <td className="n"><b>{fmt.n(it.direct_rate)}</b></td>
              {can("markup.view") && <td className="n">{fmt.n(it.final_rate)}</td>}
              <td className="small">{it.lines.map((l: any) => <div key={l.id}>{lab(l.kind)} · {lab(l.part)} · {fmt.n(l.unit_cost_base)} <span className="muted">({lab(l.source)})</span></div>)}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- comparison with pricing references
function ReferenceCompare({ est }: { est: any }) {
  const { L } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const [sel, setSel] = useState("");
  const [data] = useLoad<any>(`/estimates/${est.id}/reference${sel ? `?tender_ids=${sel}` : ""}`);
  const [onlyFlag, setOnlyFlag] = useState("");
  const color: Record<string, string> = { green: "var(--ok-soft)", amber: "var(--warn-soft)", red: "var(--err-soft)" };
  if (!data) return null;
  const rows = data.items.filter((r: any) => !onlyFlag || r.flag === onlyFlag);
  return (
    <Card title={L("مقارنة التسعير الحالي بالمرجعية السعرية (بعد تعديل الأسعار القديمة بمؤشر التكلفة)", "Current pricing vs references (old prices index-adjusted)")} actions={<>
      <Select value={sel} onChange={setSel} options={[["", L("كل المراجع", "All references")], ...data.references.map((r: any) => [String(r[0]), `${r[1]} — ${r[2]}`] as [string, string])]} />
      <Select value={onlyFlag} onChange={setOnlyFlag} options={[["", L("كل البنود", "All items")], ["red", L("انحراف > 25%", "> 25 %")], ["amber", "10–25%"], ["green", "≤ 10%"]]} /></>}>
      <div className="grid4" style={{ marginBottom: 12 }}>
        <Stat label={L("بنود لها مرجع", "Items with a reference")} value={`${data.matched} / ${data.total}`} />
        <Stat label={L("متوسط الانحراف", "Average deviation")} value={data.avg_deviation_pct == null ? "—" : fmt.p(data.avg_deviation_pct)} />
        <Stat label={L("ضمن 10%", "Within 10 %")} value={data.flags.green} />
        <Stat label={L("انحراف كبير", "Large deviation")} value={`${data.flags.amber} · ${data.flags.red}`} sub={L("متوسط · كبير", "medium · large")} />
      </div>
      <div className="tbl-wrap" style={{ maxHeight: "65vh" }}><table>
        <thead><tr><th>{L("رقم", "Ref")}</th><th>{L("البند", "Item")}</th><th className="n">{L("المباشر الحالي", "Current direct")}</th>{can("markup.view") && <th className="n">{L("النهائي الحالي", "Current final")}</th>}
          <th>{L("أقرب مرجع", "Nearest reference")}</th><th className="n">{L("سعر المرجع (معدل)", "Reference (adjusted)")}</th><th className="n">{L("الانحراف", "Deviation")}</th></tr></thead>
        <tbody>{rows.map((r: any) => {
          const b = r.references[0];
          return (
            <tr key={r.id}>
              <td>{r.item_ref}</td><td className="small desc">{r.description.slice(0, 80)}</td>
              <td className="n">{fmt.n(r.direct_rate)}</td>{can("markup.view") && <td className="n">{fmt.n(r.final_rate)}</td>}
              <td className="small">{b ? <>{b.tender_code} / {b.item_ref} <Badge k={b.outcome} /> <span className="muted">{fmt.d(b.date)} · {Math.round(b.score * 100)}%</span></> : <span className="muted">{L("لا مرجع", "none")}</span>}</td>
              <td className="n">{b ? (r.basis === "final" ? fmt.n(b.adj_final_rate) : fmt.n(b.adj_direct_rate)) : "—"}{b?.index_factor && <div className="small muted">× {b.index_factor.toFixed(2)} {L("مؤشر", "index")}</div>}</td>
              <td className="n" style={{ background: r.flag ? color[r.flag] : "" }}>{r.deviation_pct == null ? "—" : fmt.p(r.deviation_pct)}<div className="small muted">{r.basis === "final" ? L("نهائي", "final") : r.basis ? L("مباشر", "direct") : ""}</div></td>
            </tr>);
        })}</tbody>
      </table></div>
    </Card>
  );
}

// ---------------------------------------------------------------- schedule & overheads (steps 11–12)
function Overheads({ est, onChange }: { est: any; onChange: () => void }) {
  const { tender, reload } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [ind, reloadI] = useLoad<any[]>(`/estimates/${est.id}/indirects`);
  const [sch, reloadS] = useLoad<any>(`/tenders/${tender.id}/schedule`);
  const [sugg] = useLoad<any>(`/tenders/${tender.id}/schedule/suggest`);
  const [phases, setPhases] = useState<any[]>([]);
  const [dur, setDur] = useState<number | null>(null);
  useEffect(() => { if (sch) { setPhases(sch.phases); setDur(sch.duration_months); } }, [sch]);
  const locked = !["draft", "rejected"].includes(est.status) || !can("pricing.edit");
  const months = Number(est.params?.duration_months || tender.duration_months || 12);
  const up = (x: any, k: string) => (v: any) => run(async () => { await api.patch(`/indirects/${x.id}`, { [k]: v }); reloadI(); onChange(); });
  const total = (x: any) => x.kind === "time" ? x.monthly_cost * x.quantity * (x.months ?? months) : x.amount * (x.quantity || 1);
  const saveSch = () => run(async () => { await api.put(`/tenders/${tender.id}/schedule`, { duration_months: dur, phases }); reloadS(); reload(); onChange(); }, L("تم حفظ البرنامج", "Schedule saved"));
  const wsum = phases.reduce((s, p) => s + Number(p.weight_pct || 0), 0);
  return (
    <div className="stack">
      <Card title={L("11) البرنامج الزمني المبدئي (بالأشهر)", "11) Preliminary schedule (months)")} actions={can("schedule.edit") && <button className="primary" onClick={saveSch}>{L("حفظ", "Save")}</button>}>
        <div className="row gap wrap">
          <Field label={L("مدة التنفيذ (شهر)", "Duration (months)")}><input type="number" value={dur ?? ""} onChange={(e) => setDur(Number(e.target.value))} /></Field>
          {sugg?.suggested_months && <span className="badge ai">{L("مقترح من مشاريع مشابهة", "Suggested from similar projects")}: {sugg.suggested_months} {L("شهر", "months")} ({sugg.based_on})</span>}
        </div>
        <table style={{ marginTop: 10 }}>
          <thead><tr><th>{L("المرحلة", "Phase")}</th><th>{L("شهر البداية", "Start month")}</th><th>{L("المدة", "Duration")}</th><th>{L("الوزن % من التكلفة", "Weight % of cost")}</th><th>{L("الشكل", "Bar")}</th><th /></tr></thead>
          <tbody>
            {phases.map((p, i) => (
              <tr key={i}>
                <td><input value={p.name} onChange={(e) => setPhases(phases.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} /></td>
                {["start_month", "duration_months", "weight_pct"].map((k) => <td key={k}><input className="num sm" type="number" value={p[k]} onChange={(e) => setPhases(phases.map((x, j) => j === i ? { ...x, [k]: Number(e.target.value) } : x))} /></td>)}
                <td style={{ width: "35%" }}><div style={{ position: "relative", height: 12, background: "var(--surface-2)", borderRadius: 4 }}>
                  <i style={{ position: "absolute", insetInlineStart: `${((p.start_month - 1) / (dur || 12)) * 100}%`, width: `${(p.duration_months / (dur || 12)) * 100}%`, top: 0, bottom: 0, background: "var(--primary-2)", borderRadius: 4 }} /></div></td>
                <td><button className="sm ghost" onClick={() => setPhases(phases.filter((_, j) => j !== i))}>✕</button></td>
              </tr>))}
            <tr><td colSpan={3}><button className="sm" onClick={() => setPhases([...phases, { name: L("مرحلة", "Phase"), start_month: 1, duration_months: 3, weight_pct: 0 }])}>+ {L("مرحلة", "Phase")}</button></td>
              <td><Badge tone={phases.length && Math.abs(wsum - 100) > 0.01 ? "warn" : ""}>{wsum}%</Badge></td><td colSpan={2} className="muted small">{L("بدون مراحل يُستخدم منحنى S قياسي", "Without phases a standard S-curve is used")}</td></tr>
          </tbody>
        </table>
      </Card>
      <Card title={L("12) المصاريف غير المباشرة للموقع", "12) Site overheads")} actions={!locked && <>
        <button className="sm" onClick={() => run(async () => { await api.post(`/estimates/${est.id}/indirects/template`); reloadI(); onChange(); })}>{L("تحميل قالب الشركة", "Load company template")}</button>
        <button className="sm" onClick={() => run(async () => { await api.post(`/estimates/${est.id}/indirects`, { description: L("بند جديد", "New item"), kind: "time", monthly_cost: 0, quantity: 1 }); reloadI(); })}>+ {L("بند", "Item")}</button></>}>
        <div className="tbl-wrap"><table>
          <thead><tr><th>{L("البند", "Item")}</th><th>{L("النوع", "Kind")}</th><th className="n">{L("شهري", "Monthly")}</th><th className="n">{L("العدد", "Qty")}</th><th className="n">{L("الأشهر", "Months")}</th><th className="n">{L("مبلغ ثابت", "Fixed")}</th><th className="n">{L("الإجمالي", "Total")}</th><th /></tr></thead>
          <tbody>{(ind || []).map((x) => (
            <tr key={x.id} className={x.origin === "site_visit" ? "ai-row" : ""}>
              <td><TextIn value={x.description} onCommit={up(x, "description")} disabled={locked} /></td>
              <td><Select value={x.kind} disabled={locked} onChange={up(x, "kind")} options={[["time", lab("time")], ["fixed", lab("fixed")]]} /></td>
              <td className="n">{x.kind === "time" && <NumIn value={x.monthly_cost} onCommit={up(x, "monthly_cost")} disabled={locked} />}</td>
              <td className="n"><NumIn className="sm" value={x.quantity} onCommit={up(x, "quantity")} disabled={locked} /></td>
              <td className="n">{x.kind === "time" && <NumIn className="sm" value={x.months} onCommit={up(x, "months")} disabled={locked} placeholder={String(months)} />}</td>
              <td className="n">{x.kind === "fixed" && <NumIn value={x.amount} onCommit={up(x, "amount")} disabled={locked} />}</td>
              <td className="n">{fmt.m(total(x))}</td>
              <td>{!locked && <button className="sm ghost" onClick={() => run(async () => { await api.del(`/indirects/${x.id}`); reloadI(); onChange(); })}>✕</button>}</td>
            </tr>))}
            <tr className="tot"><td colSpan={6}>{L("إجمالي غير المباشر", "Total site overheads")}</td><td className="n">{fmt.m((ind || []).reduce((s, x) => s + total(x), 0))}</td><td /></tr></tbody>
        </table></div>
      </Card>
    </div>
  );
}

function PriceAdjustment({ est, locked, onChange }: { est: any; locked: boolean; onChange: () => void }) {
  const { L } = useI18n();
  const fmt = useFmt();
  const { run } = useAction();
  const pa = est.params?.price_adjustment || { enabled: false, components: [] };
  const [comps, setComps] = useState<any[]>(pa.components || []);
  useEffect(() => setComps(est.params?.price_adjustment?.components || []), [est.id]);
  const save = (next: any) => run(async () => { await api.patch(`/estimates/${est.id}`, { params: { price_adjustment: next } }); onChange(); });
  const wsum = comps.reduce((a, c) => a + Number(c.weight || 0), 0);
  const rec = comps.reduce((a, c) => a + Number(c.weight || 0) / 100 * Number(c.expected_change_pct || 0), 0);
  const defaults = [{ name: L("عمالة", "Labour"), weight: 20, expected_change_pct: 0 }, { name: L("حديد", "Steel"), weight: 20, expected_change_pct: 0 },
    { name: L("أسمنت", "Cement"), weight: 15, expected_change_pct: 0 }, { name: L("وقود", "Fuel"), weight: 10, expected_change_pct: 0 }];
  return (
    <div style={{ marginTop: 16 }}>
      <label className="row gap"><input type="checkbox" checked={!!pa.enabled} disabled={locked} onChange={(e) => save({ enabled: e.target.checked, components: comps.length ? comps : defaults })} />
        <b>{L("العقد به بند فروق أسعار (معادلة تعديل الأسعار)", "Contract has a price-adjustment clause (formula)")}</b></label>
      {pa.enabled && <>
        <p className="muted small">P = a + Σ wᵢ·Iᵢ/Iᵢ₀ — {L("أدخل وزن كل عنصر والتغير المتوقع في مؤشره خلال المدة؛ الجزء الثابت a = 100% − مجموع الأوزان.", "enter each component's weight and expected index change; fixed part a = 100 % − Σ weights.")}</p>
        <table><thead><tr><th>{L("العنصر", "Component")}</th><th className="n">{L("الوزن %", "Weight %")}</th><th className="n">{L("التغير المتوقع %", "Expected change %")}</th><th /></tr></thead>
          <tbody>{comps.map((c, i) => (
            <tr key={i}><td><input value={c.name} disabled={locked} onChange={(e) => setComps(comps.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} /></td>
              {["weight", "expected_change_pct"].map((k) => <td key={k}><input className="num sm" type="number" disabled={locked} value={c[k]} onChange={(e) => setComps(comps.map((x, j) => j === i ? { ...x, [k]: Number(e.target.value) } : x))} /></td>)}
              <td>{!locked && <button className="sm ghost" onClick={() => setComps(comps.filter((_, j) => j !== i))}>✕</button>}</td></tr>))}
            <tr className="tot"><td>{L("الجزء الثابت a", "Fixed part a")}: {fmt.p(100 - wsum, 0)}</td><td colSpan={3}>{L("المسترد بالمعادلة", "Recovered by the formula")}: <b>{fmt.p(rec, 2)}</b></td></tr></tbody></table>
        {!locked && <div className="row gap" style={{ marginTop: 6 }}><button className="sm" onClick={() => setComps([...comps, { name: "", weight: 0, expected_change_pct: 0 }])}>+ {L("عنصر", "Component")}</button>
          <button className="sm primary" onClick={() => save({ enabled: true, components: comps })}>{L("حفظ المعادلة", "Save formula")}</button></div>}
        <p className="muted small">{L("التحميل في التسعير = زيادة الخامات المتوقعة − المسترد بالمعادلة (لا يقل عن صفر).", "Priced escalation = expected material escalation − recovered by formula (not below zero).")}</p>
      </>}
    </div>
  );
}

// ---------------------------------------------------------------- parameters (steps 13–14)
function Params({ est, onChange }: { est: any; onChange: () => void }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const can = useCan();
  const { run } = useAction();
  const [settings] = useLoad<any>("/settings");
  const locked = !["draft", "rejected"].includes(est.status) || !can("pricing.edit");
  const p = est.params || {};
  const save = (k: string) => (v: any) => run(async () => { await api.patch(`/estimates/${est.id}`, { params: { [k]: v } }); onChange(); });
  const fxSave = (cur: string) => (v: any) => run(async () => { await api.patch(`/estimates/${est.id}`, { fx_rates: { ...est.fx_rates, [cur]: v } }); onChange(); });
  const num = (k: string, label: string, hint?: string) => <Field label={label} hint={hint}><NumIn value={p[k]} onCommit={save(k)} disabled={locked} /></Field>;
  const taxes = p.taxes || settings?.taxes || [];
  return (
    <div className="grid2">
      <Card title={L("13) الطوارئ وفروق الأسعار وسعر الصرف", "13) Contingency, escalation & FX")}>
        <div className="form">
          {num("general_contingency_pct", L("طوارئ عامة % من المباشر", "General contingency % of direct"), L("بالإضافة لقيم سجل المخاطر", "on top of the risk register values"))}
          {num("material_escalation_pct", L("زيادة أسعار الخامات % خلال المدة", "Material escalation % over duration"))}
          {num("fx_buffer_pct", L("هامش سعر الصرف % على البنود المستوردة", "FX buffer % on imported items"))}
        </div>
        <h4 style={{ margin: "14px 0 8px" }}>{L("أسعار الصرف المحفوظة في هذه النسخة", "FX rates frozen in this version")} ({tender.base_currency})</h4>
        <div className="form">
          {Object.keys({ USD: 1, EUR: 1, ...(est.fx_rates || {}) }).map((c) => <Field key={c} label={`1 ${c} =`}><NumIn value={est.fx_rates?.[c]} onCommit={fxSave(c)} disabled={locked} /></Field>)}
        </div>
        <PriceAdjustment est={est} locked={locked} onChange={onChange} />
      </Card>
      <Card title={L("14) التمويل والمصاريف الإدارية والضمانات والضرائب", "14) Finance, HO overheads, bonds & taxes")}>
        <div className="form">
          {num("ho_overhead_pct", L("مصاريف المكتب الرئيسي %", "Head-office overheads %"))}
          {num("advance_payment_pct", L("الدفعة المقدمة %", "Advance payment %"))}
          {num("retention_pct", L("الاستقطاع %", "Retention %"))}
          {num("payment_delay_months", L("تأخر صرف المستخلص (شهر)", "Payment delay (months)"))}
          {num("finance_rate_pa_pct", L("تكلفة التمويل السنوية %", "Finance rate % p.a."))}
          {num("maintenance_months", L("فترة الصيانة (شهر)", "Maintenance (months)"))}
          {num("performance_bond_pct", L("خطاب الضمان النهائي %", "Performance bond %"))}
          {num("advance_guarantee_pct", L("ضمان الدفعة المقدمة %", "Advance guarantee %"))}
          {num("bond_commission_pa_pct", L("عمولة البنك السنوية %", "Bank commission % p.a."))}
          {num("insurance_pct", L("التأمين (CAR) % من القيمة", "Insurance (CAR) % of value"))}
          {num("duration_months", L("المدة المستخدمة (شهر)", "Duration used (months)"), L("فارغ = مدة المناقصة", "empty = tender duration"))}
          <Field label={L("حساب تكلفة التمويل", "Include finance cost")}><input type="checkbox" checked={p.include_finance !== false} disabled={locked} onChange={(e) => save("include_finance")(e.target.checked)} /></Field>
        </div>
        <h4 style={{ margin: "14px 0 8px" }}>{L("الضرائب (من الإعدادات — تُراجع حسب القانون الساري)", "Taxes (from settings — confirm against current law)")}</h4>
        <table><tbody>{taxes.map((t: any, i: number) => <tr key={i}><td>{t.name}</td><td className="n">{t.rate_pct}%</td><td className="muted small">{t.mode === "on_top" ? L("تضاف على الإجمالي", "added on top") : L("ضمن السعر", "included in price")}</td></tr>)}</tbody></table>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- markup & spreading (steps 15–16)
function Markup({ est, calc, onChange }: { est: any; calc: any; onChange: () => void }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [wi, setWi] = useState<any[] | null>(null);
  const [marks, setMarks] = useState("5, 7.5, 10, 12.5, 15, 20");
  const [items] = useLoad<any[]>(`/tenders/${tender.id}/boq`);
  const [res] = useLoad<any>(`/tenders/${tender.id}/result`);
  const locked = !["draft", "rejected"].includes(est.status) || !can("markup.edit");
  const p = est.params || {};
  const ov = p.spread_overrides || {};
  const setMarkup = (v: any) => run(async () => { await api.patch(`/estimates/${est.id}`, { params: { markup_pct: v } }); onChange(); });
  const setOv = (id: number, val: any) => run(async () => {
    const next = { ...ov };
    if (!val || (val.rate == null && val.factor == null)) delete next[id]; else next[id] = val;
    await api.patch(`/estimates/${est.id}`, { params: { spread_overrides: next } });
    onChange();
  });
  const runWi = () => run(async () => setWi(await api.post(`/estimates/${est.id}/whatif`, { markups: marks.split(/[,،\s]+/).filter(Boolean).map(Number) })));
  useEffect(() => { if (can("markup.view")) runWi(); }, [est.id]);
  if (!can("markup.view")) return <Card><Empty>{L("نسبة الربح والأسعار النهائية متاحة للإدارة فقط", "Markup and final prices are visible to management only")}</Empty></Card>;
  const rows = Object.fromEntries((calc?.items || []).map((r: any) => [r.id, r]));
  const s = calc?.summary;
  return (
    <div className="stack">
      <div className="grid2">
        <Card title={L("15) قرار الربح — سيناريوهات «ماذا لو»", "15) Markup decision — what-if scenarios")}>
          <div className="row gap wrap">
            <Field label={L("نسبة الربح المعتمدة %", "Approved markup %")}><NumIn value={p.markup_pct} onCommit={setMarkup} disabled={locked} /></Field>
            <Field label={L("سيناريوهات", "Scenarios")}><input value={marks} onChange={(e) => setMarks(e.target.value)} /></Field>
            <button onClick={runWi} style={{ alignSelf: "flex-end" }}>{L("احسب", "Run")}</button>
          </div>
          {wi && (
            <table style={{ marginTop: 10 }}>
              <thead><tr><th className="n">{L("الربح %", "Markup %")}</th><th className="n">{L("الإجمالي قبل ض.ق.م", "Total excl. VAT")}</th><th className="n">{L("الربح", "Profit")}</th><th className="n">{L("شامل ض.ق.م", "Incl. VAT")}</th><th /></tr></thead>
              <tbody>{wi.map((w) => (
                <tr key={w.markup_pct} className={Number(w.markup_pct) === Number(p.markup_pct) ? "sel" : ""}>
                  <td className="n">{w.markup_pct}%</td><td className="n">{fmt.m(w.total_excl_vat)}</td><td className="n">{fmt.m(w.profit)}</td><td className="n">{fmt.m(w.total_incl_vat)}</td>
                  <td>{!locked && <button className="sm" onClick={() => setMarkup(w.markup_pct)}>{L("اعتماد", "Use")}</button>}</td></tr>))}</tbody>
            </table>
          )}
        </Card>
        <Card title={L("مقارنة بمناقصات سابقة وأسعار المنافسين", "Benchmark vs past tenders & competitors")}>
          {res?.competitors?.length ? (
            <table><tbody>{res.competitors.map((c: any) => <tr key={c.id}><td>{c.name}</td><td className="n">{fmt.m(c.price)}</td><td className="n">{s && fmt.p((s.submitted_total - c.price) / c.price * 100)}</td></tr>)}</tbody></table>
          ) : <p className="muted">{L("تظهر أسعار المنافسين المعروفة هنا بعد تسجيلها في تبويب النتيجة. نسبة الفوز حسب نوع المشروع في لوحة المؤشرات.", "Known competitor prices appear here once recorded in the result tab.")}</p>}
          {s && <dl className="kv" style={{ marginTop: 10 }}><dt>{L("هامش الربح من السعر", "Margin on price")}</dt><dd>{fmt.p(s.margin_on_price_pct)}</dd>
            <dt>{L("معامل التوزيع", "Spread factor")}</dt><dd>{fmt.n(s.spread_factor, 4)}</dd></dl>}
        </Card>
      </div>
      <Card title={L("16) توزيع غير المباشر والربح على البنود", "16) Spreading indirects & profit over items")}>
        <p className="muted small">{L("الافتراضي: بنسبة التكلفة المباشرة. يمكن تثبيت سعر أو معامل لبنود محددة ويُوزع الباقي على البنود الأخرى تلقائيًا.", "Default: proportional to direct cost. Fix a rate or factor for selected items; the remainder spreads over the others.")}</p>
        <div className="tbl-wrap" style={{ maxHeight: "60vh" }}><table>
          <thead><tr><th>{L("رقم", "Ref")}</th><th>{L("الوصف", "Description")}</th><th className="n">{L("الكمية", "Qty")}</th><th className="n">{L("المباشر", "Direct")}</th><th className="n">{L("المعامل", "Factor")}</th>
            <th className="n">{L("السعر النهائي", "Final rate")}</th><th className="n">{L("الإجمالي", "Amount")}</th><th>{L("تثبيت يدوي", "Manual override")}</th></tr></thead>
          <tbody>{(items || []).filter((i) => !i.is_section).map((i) => {
            const r = rows[i.id] || {};
            const o = ov[i.id] || ov[String(i.id)];
            return (
              <tr key={i.id} className={o ? "sel" : ""}>
                <td>{i.item_ref}</td><td className="small">{i.description.slice(0, 70)}</td><td className="n">{fmt.n(i.quantity, 0)}</td>
                <td className="n">{r.provisional ? <Badge>{L("احتياطي", "prov.")}</Badge> : fmt.n(r.direct_rate)}</td><td className="n">{r.factor ? fmt.n(r.factor, 3) : "—"}</td>
                <td className="n"><b>{fmt.n(r.final_rate)}</b></td><td className="n">{fmt.m(r.amount)}</td>
                <td>{!r.provisional && <div className="row gap">
                  <NumIn className="sm" value={o?.factor} placeholder={L("معامل", "factor")} disabled={locked} onCommit={(v) => setOv(i.id, v == null ? null : { factor: v })} />
                  <NumIn className="sm" value={o?.rate} placeholder={L("سعر", "rate")} disabled={locked} onCommit={(v) => setOv(i.id, v == null ? null : { rate: v })} /></div>}</td>
              </tr>);
          })}</tbody>
        </table></div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- summary waterfall + cash flow
function Summary({ calc }: { calc: any }) {
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  if (!calc) return null;
  const s = calc.summary;
  const rows: [string, any, boolean?][] = [
    [L("التكلفة المباشرة", "Direct cost"), s.direct, true],
    [`  ${lab("material")}`, s.direct_by_kind.material], [`  ${lab("labor")}`, s.direct_by_kind.labor], [`  ${lab("equipment")}`, s.direct_by_kind.equipment], [`  ${lab("subcontract")}`, s.direct_by_kind.subcontract],
    [`  ${lab("supply")}`, s.direct_by_part.supply], [`  ${lab("apply")}`, s.direct_by_part.apply], [`  ${lab("supply_apply")}`, s.direct_by_part.supply_apply],
    [L("مصاريف الموقع غير المباشرة", "Site overheads"), s.site_overheads, true],
    [L("الطوارئ (مخاطر + عامة)", "Contingency (risks + general)"), s.contingency, true],
    [L("فروق أسعار وسعر صرف", "Escalation & FX"), s.escalation, true],
    ...(s.escalation_recovery_pct ? [[`  ${L("مسترد بمعادلة فروق الأسعار", "recovered by price-adjustment clause")} ${s.escalation_recovery_pct}%`, undefined] as [string, any]] : []),
    [L("مصاريف المكتب الرئيسي", "Head-office overheads"), s.ho_overheads, true],
    [L("تكلفة التأمين الابتدائي", "Bid bond cost"), s.bid_bond_cost],
    [L("تكلفة التمويل", "Finance cost"), s.finance, true],
    [L("الضمانات والتأمين", "Bonds & insurance"), s.bonds_insurance, true],
    [L("ضرائب ضمن السعر", "Taxes in price"), s.taxes_in_price],
    [L("التكلفة الكلية قبل الربح", "Total cost before profit"), s.cost_before_profit, true],
    [`${L("الربح", "Profit")} (${s.markup_pct ?? "—"}%)`, s.profit, true],
    [L("المبالغ الاحتياطية", "Provisional sums"), s.provisional_sums],
    [L("إجمالي العرض قبل ض.ق.م", "Bid total excl. VAT"), s.submitted_total, true],
    [L("فرق التقريب", "Rounding difference"), s.rounding_diff],
    [L("ضريبة القيمة المضافة", "VAT"), s.vat_total],
    [L("الإجمالي شامل الضريبة", "Total incl. VAT"), s.total_incl_vat, true],
  ];
  const cf = calc.cash_flow || [];
  const maxAbs = Math.max(1, ...cf.map((r: any) => Math.abs(r.balance)));
  return (
    <div className="grid2">
      <Card title={L("بناء السعر خطوة بخطوة", "Price build-up, step by step")}>
        {calc.redacted && <p className="alert info">{L("الربح والإجمالي النهائي مخفيان — صلاحية الإدارة", "Profit and final totals are hidden (management permission)")}</p>}
        <table className="waterfall"><tbody>{rows.filter(([, v]) => v !== undefined).map(([l, v, b], i) => (
          <tr key={i} className={b ? "" : "muted"}><td style={{ whiteSpace: "pre", fontWeight: b ? 600 : 400 }}>{l}</td><td className="n">{fmt.m(v)}</td>
            <td style={{ width: "30%" }}>{b && s.submitted_total ? <div className="bar"><i style={{ width: `${Math.min(100, Math.abs(v) / s.submitted_total * 100)}%` }} /></div> : null}</td></tr>))}</tbody></table>
        {calc.warnings?.map((w: any) => <div key={w.code} className="alert err" style={{ marginTop: 8 }}>{w.message}</div>)}
      </Card>
      <Card title={L("التدفق النقدي ورصيد التمويل الشهري", "Monthly cash flow & finance balance")}>
        {!cf.length ? <Empty>{L("يظهر للإدارة", "Visible to management")}</Empty> : <>
          <p className="muted small">{L("أقصى عجز نقدي", "Peak cash deficit")}: <b>{fmt.m(s.peak_cash_deficit)}</b></p>
          <div className="tbl-wrap" style={{ maxHeight: 420 }}><table>
            <thead><tr><th>{L("شهر", "Month")}</th><th className="n">{L("تكلفة", "Cost")}</th><th className="n">{L("تحصيل", "Income")}</th><th className="n">{L("الرصيد", "Balance")}</th><th /></tr></thead>
            <tbody>{cf.filter((r: any) => r.cost || r.income || r.interest).map((r: any) => (
              <tr key={r.month}><td>{r.month}</td><td className="n">{fmt.m(r.cost)}</td><td className="n">{fmt.m(r.income)}</td>
                <td className="n" style={{ color: r.balance < 0 ? "var(--err)" : "var(--ok)" }}>{fmt.m(r.balance)}</td>
                <td style={{ width: "28%" }}><div style={{ height: 8, width: `${Math.abs(r.balance) / maxAbs * 100}%`, background: r.balance < 0 ? "#fca5a5" : "#86efac", borderRadius: 3 }} /></td></tr>))}</tbody>
          </table></div></>}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- value engineering
function ValueEng({ calc }: { calc: any }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [ve, reload] = useLoad<any[]>(`/tenders/${tender.id}/ve`);
  const [items] = useLoad<any[]>(`/tenders/${tender.id}/boq`);
  const rows = Object.fromEntries((calc?.items || []).map((r: any) => [r.id, r]));
  const its = (items || []).filter((i) => !i.is_section);
  const byId = Object.fromEntries(its.map((i) => [i.id, i]));
  const dis = !can("pricing.edit");
  const up = (v: any, k: string) => (x: any) => run(async () => { await api.patch(`/ve/${v.id}`, { [k]: x }); reload(); });
  return (
    <Card title={L("البدائل والهندسة القيمية (Value Engineering)", "Alternatives & value engineering")} actions={!dis && <button className="sm" onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/ve`, { description: L("بديل مقترح", "Proposed alternative") }); reload(); })}>+ {L("بديل", "Alternative")}</button>}>
      <p className="muted small">{L("البدائل لا تغيّر السعر الأساسي؛ تُقدَّم كعرض اختياري مع مدة التوريد وتوفيرها.", "Alternatives do not change the base price; they are offered as options with lead time and saving.")}</p>
      {!ve?.length ? <Empty>{L("لا بدائل", "No alternatives")}</Empty> : (
        <table><thead><tr><th>{L("البند", "Item")}</th><th>{L("البديل", "Alternative")}</th><th className="n">{L("المباشر الحالي", "Current direct")}</th><th className="n">{L("سعر البديل", "Alt. rate")}</th><th className="n">{L("التوفير", "Saving")}</th><th>{L("مدة التوريد", "Lead time")}</th><th>{L("الحالة", "Status")}</th></tr></thead>
          <tbody>{ve.map((v) => {
            const cur = rows[v.boq_item_id]?.direct_rate || 0;
            const it = byId[v.boq_item_id];
            return (
              <tr key={v.id}>
                <td><Select value={v.boq_item_id ?? ""} disabled={dis} onChange={up(v, "boq_item_id")} options={[["", "—"], ...its.map((i) => [i.id, `${i.item_ref} ${i.description.slice(0, 40)}`] as [number, string])]} /></td>
                <td><TextIn value={v.description} onCommit={up(v, "description")} disabled={dis} /></td>
                <td className="n">{fmt.n(cur)}</td><td className="n"><NumIn value={v.alternative_rate} onCommit={up(v, "alternative_rate")} disabled={dis} /></td>
                <td className="n">{it && cur ? fmt.m((cur - v.alternative_rate) * it.quantity) : "—"}</td>
                <td><NumIn className="sm" value={v.lead_time_days} onCommit={up(v, "lead_time_days")} disabled={dis} /></td>
                <td><Select value={v.status} disabled={dis} onChange={up(v, "status")} options={[["proposed", L("مقترح", "Proposed")], ["offered", L("مقدَّم للمالك", "Offered")], ["accepted", L("مقبول", "Accepted")], ["rejected", L("مرفوض", "Rejected")]]} /></td>
              </tr>);
          })}</tbody></table>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- review & approval (step 17)
function Review({ est, onChange }: { est: any; onChange: () => void }) {
  const { tender, estimates, reloadEstimates, setEstimateId, reload } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [checks, reloadC] = useLoad<any[]>(`/estimates/${est.id}/checks`, [est.status]);
  const [cmpA, setCmpA] = useState<number | null>(null);
  const [cmp, setCmp] = useState<any>(null);
  const [comment, setComment] = useState("");
  const act = (path: string, body?: any, msg?: string) => run(async () => { await api.post(`/estimates/${est.id}/${path}`, body); reloadEstimates(); reload(); reloadC(); onChange(); }, msg);
  const errors = (checks || []).filter((c) => c.severity === "error");
  return (
    <div className="stack">
      <Card title={L("17) الفحوصات الآلية قبل الاعتماد", "17) Automated checks before approval")} actions={<Badge k={est.status} />}>
        {!checks ? null : !checks.length ? <div className="alert info">{L("لا ملاحظات", "No findings")}</div> : checks.map((c, i) => (
          <div key={i} className="check-row"><Badge k={c.severity} /><span>{c.message}</span></div>))}
        <div className="row gap wrap" style={{ marginTop: 12 }}>
          {["draft", "rejected"].includes(est.status) && can("pricing.edit") && <button className="primary" disabled={busy || errors.length > 0} onClick={() => act("submit", undefined, L("أُرسلت للمراجعة", "Sent for review"))}>{L("إرسال للمراجعة والاعتماد", "Submit for review")}</button>}
          {est.status === "in_review" && can("estimate.approve") && <>
            <button className="ok" disabled={busy} onClick={() => act("approve", undefined, L("تم الاعتماد وقفل النسخة", "Approved and locked"))}>{L("اعتماد وقفل النسخة", "Approve & lock")}</button>
            <input placeholder={L("ملاحظات الرفض", "Rejection comments")} value={comment} onChange={(e) => setComment(e.target.value)} />
            <button className="danger" disabled={busy} onClick={() => act("reject", { comments: comment }, L("رُفضت وعادت للتسعير", "Rejected, back to pricing"))}>{L("رفض وإرجاع للمرحلة 4", "Reject → back to stage 4")}</button></>}
          {errors.length > 0 && <span className="muted small">{L("أصلح الأخطاء أولًا", "Fix errors first")}</span>}
        </div>
        {est.review_comments && <div className="alert" style={{ marginTop: 10 }}>{L("ملاحظات المراجعة", "Review comments")}: {est.review_comments}</div>}
        {est.status === "approved" && <p className="muted small">{L("اعتمدها", "Approved by")} {est.approved_by_name} · {fmt.d(est.approved_at)} — {L("النسخة مقفولة؛ أي تعديل يتطلب نسخة جديدة.", "Locked; changes need a new version.")}</p>}
      </Card>
      <Card title={L("النسخ والمقارنة", "Versions & comparison")} actions={can("pricing.edit") && <button onClick={() => run(async () => { const n = await api.post(`/tenders/${tender.id}/estimates`, { clone_from: est.id }); reloadEstimates(); setEstimateId(n.id); }, L("أُنشئت نسخة جديدة", "New version created"))}>{L("نسخة جديدة من هذه", "New version from this")}</button>}>
        <table><thead><tr><th>{L("النسخة", "Version")}</th><th>{L("الحالة", "Status")}</th><th>{L("أنشأها", "Created by")}</th><th>{L("التاريخ", "Date")}</th><th>{L("أسعار الصرف", "FX")}</th><th /></tr></thead>
          <tbody>{estimates.map((e) => (
            <tr key={e.id} className={e.id === est.id ? "sel" : ""}><td>V{e.version_no}</td><td><Badge k={e.status} /></td><td>{e.created_by_name}</td><td>{fmt.d(e.created_at)}</td>
              <td className="small">{Object.entries(e.fx_rates || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</td>
              <td>{e.id !== est.id && <button className="sm" onClick={() => run(async () => { setCmpA(e.id); setCmp(await api.get(`/estimates/compare/${e.id}/${est.id}`)); })}>{L("قارن مع الحالية", "Compare")}</button>}</td></tr>))}</tbody></table>
        {cmp && cmpA && (
          <div style={{ marginTop: 12 }}>
            <h4>V{cmp.a.version} ↔ V{cmp.b.version}</h4>
            <table><thead><tr><th /><th className="n">V{cmp.a.version}</th><th className="n">V{cmp.b.version}</th><th className="n">{L("الفرق", "Diff")}</th></tr></thead>
              <tbody>{Object.entries(cmp.summary).filter(([, v]: any) => v.a != null || v.b != null).map(([k, v]: any) => (
                <tr key={k}><td>{k}</td><td className="n">{fmt.m(v.a)}</td><td className="n">{fmt.m(v.b)}</td><td className="n">{fmt.m((v.b || 0) - (v.a || 0))}</td></tr>))}</tbody></table>
            <p className="muted small">{cmp.items.length} {L("بند تغير سعره", "items changed")}</p>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- container
export default function Pricing() {
  const { tender, estimate, reloadEstimates, setEstimateId } = useTender();
  const { L } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [sub, setSub] = useState("buildup");
  const [n, setN] = useState(0);
  const [calc, setCalc] = useState<any>(null);
  const refresh = () => { setN((x) => x + 1); reloadEstimates(); };
  useEffect(() => {
    if (!estimate) return;
    api.get(`/estimates/${estimate.id}/calc`).then(setCalc).catch(() => setCalc(null));
  }, [estimate?.id, estimate?.status, n]);
  if (!estimate) return (
    <Card><Empty>{L("لا توجد نسخة تسعير", "No estimate version")}<br /><br />
      {can("pricing.edit") && <button className="primary" disabled={busy} onClick={() => run(async () => { const e = await api.post(`/tenders/${tender.id}/estimates`, {}); reloadEstimates(); setEstimateId(e.id); })}>{L("إنشاء النسخة الأولى (V1)", "Create first version (V1)")}</button>}</Empty></Card>
  );
  const s = calc?.summary;
  return (
    <div className="stack">
      <div className="row gap wrap between">
        <EstimatePicker />
        {s && <div className="row gap wrap">
          <Badge>{L("المباشر", "Direct")} {fmt.m(s.direct)}</Badge>
          {s.submitted_total != null && <Badge tone="ok">{L("الإجمالي", "Total")} {fmt.m(s.submitted_total)}</Badge>}
          {calc.redacted && <Badge>{L("الإجمالي النهائي للإدارة فقط", "Final total: management only")}</Badge>}
        </div>}
      </div>
      <Tabs tabs={[
        { key: "buildup", label: L("تحليل البنود", "Rate build-up") },
        { key: "analysis", label: L("تحليل الأسعار (توريد/تركيب)", "Price analysis (Supply/Apply)") },
        { key: "reference", label: L("مقارنة بالمرجعية", "vs references") },
        { key: "overheads", label: L("البرنامج وغير المباشر", "Schedule & overheads") },
        { key: "params", label: L("الطوارئ والتمويل والضرائب", "Contingency, finance & taxes") },
        { key: "markup", label: L("الربح والتوزيع", "Markup & spreading"), hidden: !can("markup.view") },
        { key: "summary", label: L("الملخص والتدفق النقدي", "Summary & cash flow") },
        { key: "ve", label: L("البدائل (VE)", "Alternatives (VE)") },
        { key: "review", label: L("المراجعة والاعتماد", "Review & approval") },
      ]} active={sub} onChange={setSub} />
      {sub === "buildup" && <BuildUp est={estimate} calc={calc} onChange={refresh} />}
      {sub === "analysis" && <PriceAnalysis key={n} est={estimate} />}
      {sub === "reference" && <ReferenceCompare key={n} est={estimate} />}
      {sub === "overheads" && <Overheads est={estimate} onChange={refresh} />}
      {sub === "params" && <Params est={estimate} onChange={refresh} />}
      {sub === "markup" && <Markup est={estimate} calc={calc} onChange={refresh} />}
      {sub === "summary" && <Summary calc={calc} />}
      {sub === "ve" && <ValueEng calc={calc} />}
      {sub === "review" && <Review est={estimate} onChange={refresh} />}
    </div>
  );
}
