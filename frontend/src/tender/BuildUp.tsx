import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { AIBadge, Badge, Card, Empty, Select, useAction, useCan, useFmt, useLoad } from "../ui";
import { useTender } from "./TenderPage";

const KINDS = ["material", "labor", "equipment", "subcontract"];
const PARTS = ["supply", "apply", "supply_apply"];

function lineCost(l: any, fx: Record<string, number>, base: string) {
  const f = !l.currency || l.currency === base ? 1 : Number(fx[l.currency] || 0);
  return Number(l.coefficient || 0) * Number(l.unit_price || 0) * (1 + Number(l.waste_pct || 0) / 100) * f;
}

function Editor({ item, est, onSaved }: { item: any; est: any; onSaved: () => void }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [all] = useLoad<any[]>(`/estimates/${est.id}/lines`, [item.id]);
  const [src, reloadSrc] = useLoad<any>(`/estimates/${est.id}/items/${item.id}/sources`);
  const [lines, setLines] = useState<any[]>([]);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { if (all) { setLines(all.filter((l) => l.boq_item_id === item.id)); setDirty(false); } }, [all, item.id]);
  const locked = !["draft", "rejected"].includes(est.status) || !can("pricing.edit");
  const fx = est.fx_rates || {};
  const set = (i: number, k: string, v: any) => { setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l))); setDirty(true); };
  const add = (l: any) => { setLines([...lines, { kind: "material", part: item.scope === "apply" ? "apply" : "supply", coefficient: 1, unit_price: 0, currency: tender.base_currency, waste_pct: 0, source: "manual", approved: true, ...l }]); setDirty(true); };
  const save = () => run(async () => { await api.put(`/estimates/${est.id}/items/${item.id}/lines`, lines); setDirty(false); onSaved(); }, L("تم حفظ التحليل", "Build-up saved"));
  const total = lines.reduce((s, l) => s + lineCost(l, fx, tender.base_currency), 0);
  const byPart = PARTS.map((p) => [p, lines.filter((l) => l.part === p).reduce((s, l) => s + lineCost(l, fx, tender.base_currency), 0)] as [string, number]);
  const old = (d?: string) => d && (Date.now() - new Date(d).getTime()) / 86400000 > 90;
  return (
    <div className="stack">
      <Card title={<span>{item.item_ref} — {L("تحليل سعر البند", "Item rate build-up")} <Badge k={item.scope} /></span>} actions={!locked && <>
        <button className="sm" onClick={() => add({ kind: "material" })}>+ {L("خامة", "Material")}</button>
        <button className="sm" onClick={() => add({ kind: "labor", part: "apply" })}>+ {L("عمالة", "Labour")}</button>
        <button className="sm" onClick={() => add({ kind: "equipment", part: "apply" })}>+ {L("معدة", "Equipment")}</button>
        <button className="sm" onClick={() => add({ kind: "subcontract", part: item.scope })}>+ {L("باطن", "Subcontract")}</button>
        <button className="primary" disabled={!dirty || busy} onClick={save}>{L("حفظ", "Save")}</button>
        {can("library.manage") && lines.length > 0 && !dirty && <button className="sm" onClick={() => { const name = prompt(L("اسم القالب", "Template name"), item.description.slice(0, 60)); if (name) run(() => api.post("/templates/from-item", { estimate_id: est.id, item_id: item.id, name }), L("حُفظ كقالب بأسعاره", "Saved as a priced template")); }}>{L("حفظ كقالب", "Save as template")}</button>}</>}>
        <p className="desc" style={{ margin: "0 0 10px" }}>{item.description} <span className="muted">— {item.quantity} {item.unit}</span></p>
        {!lines.length ? <Empty>{L("لا توجد مكونات — أضف من مصادر الأسعار أدناه", "No lines — add from the price sources below")}</Empty> : (
          <div className="tbl-wrap"><table>
            <thead><tr><th>{L("النوع", "Kind")}</th><th>{L("الجزء", "Part")}</th><th>{L("الوصف", "Description")}</th>
              <th className="n" title={L("كمية المورد لكل وحدة بند (للعمالة = 1 ÷ الإنتاجية)", "Resource qty per BOQ unit (labour = 1 ÷ productivity)")}>{L("المعامل", "Coef.")}</th>
              <th className="n">{L("سعر الوحدة", "Unit price")}</th><th>{L("العملة", "Cur")}</th><th className="n">{L("هالك %", "Waste %")}</th>
              <th className="n">{L("تكلفة/وحدة", "Cost/unit")}</th><th>{L("المصدر", "Source")}</th><th /></tr></thead>
            <tbody>{lines.map((l, i) => (
              <tr key={i} className={!l.approved ? "ai-row" : ""}>
                <td><Select value={l.kind} disabled={locked} onChange={(v) => set(i, "kind", v)} options={KINDS.map((k) => [k, lab(k)])} /></td>
                <td><Select value={l.part} disabled={locked} onChange={(v) => set(i, "part", v)} options={PARTS.map((k) => [k, lab(k)])} /></td>
                <td><input value={l.description || ""} disabled={locked} onChange={(e) => set(i, "description", e.target.value)} style={{ minWidth: 180 }} /></td>
                <td className="n"><input className="num sm" type="number" step="any" value={l.coefficient} disabled={locked} onChange={(e) => set(i, "coefficient", e.target.value)} />
                  {l.kind === "labor" && !locked && <div className="small muted">{L("إنتاجية/يوم", "units/day")} <input className="num sm" type="number" step="any"
                    placeholder="—" onChange={(e) => Number(e.target.value) > 0 && set(i, "coefficient", +(1 / Number(e.target.value)).toFixed(6))} /></div>}</td>
                <td className="n"><input className="num" type="number" step="any" value={l.unit_price} disabled={locked} onChange={(e) => set(i, "unit_price", e.target.value)} /></td>
                <td><input className="num sm" value={l.currency} disabled={locked} onChange={(e) => set(i, "currency", e.target.value.toUpperCase())} /></td>
                <td className="n"><input className="num sm" type="number" step="any" value={l.waste_pct} disabled={locked} onChange={(e) => set(i, "waste_pct", e.target.value)} /></td>
                <td className="n">{fmt.n(lineCost(l, fx, tender.base_currency))}</td>
                <td className="small">
                  <Badge>{lab(l.source)}</Badge> {!l.approved && <AIBadge conf={l.confidence} />}
                  <div className="muted">{l.source_ref}{l.price_date && <> · <span style={{ color: old(l.price_date) ? "var(--warn)" : "" }}>{fmt.d(l.price_date)}</span></>}</div>
                  {!l.approved && !locked && <button className="sm ok" onClick={() => set(i, "approved", true)}>{L("اعتماد", "Approve")}</button>}
                </td>
                <td>{!locked && <button className="sm ghost" onClick={() => { setLines(lines.filter((_, j) => j !== i)); setDirty(true); }}>✕</button>}</td>
              </tr>))}
              <tr className="tot"><td colSpan={7}>{L("التكلفة المباشرة للوحدة", "Direct cost per unit")} <span className="muted small">
                {byPart.filter(([, v]) => v).map(([p, v]) => ` · ${lab(p)} ${fmt.n(v)}`)}</span></td><td className="n">{fmt.n(total)}</td><td colSpan={2} className="n">× {item.quantity} = {fmt.m(total * item.quantity)}</td></tr>
            </tbody>
          </table></div>
        )}
        {dirty && <p className="alert" style={{ marginTop: 8 }}>{L("تعديلات غير محفوظة", "Unsaved changes")}</p>}
      </Card>
      {src && !locked && (
        <Card title={L("مصادر السعر بالترتيب: عرض مورد ← مكتبة الأسعار ← أقرب مشروع سابق", "Price sources in order: supplier quote → price library → nearest past project")}>
          <div className="grid2">
            <div>
              <h4>1) {L("عروض الموردين ومقاولي الباطن", "Supplier & subcontractor quotes")}</h4>
              {!src.quotations.length ? <p className="muted small">{L("لا عروض لهذا البند", "No quotes for this item")}</p> : (
                <table><tbody>{src.quotations.filter((q: any) => q.normalized != null).map((q: any) => (
                  <tr key={q.quotation_id}><td>{q.supplier} <Badge k={q.scope} /></td><td className="n">{fmt.n(q.normalized)} {q.currency}</td>
                    <td className="small muted">{q.lead_time_days ? `${q.lead_time_days} ${L("يوم", "d")}` : ""}</td>
                    <td><button className="sm" onClick={() => add({ kind: q.scope === "supply" ? "material" : "subcontract", part: q.scope, description: q.supplier, unit_price: q.normalized, currency: q.currency,
                      source: "quotation", source_ref: `Q#${q.quotation_id} ${q.supplier}`, quotation_id: q.quotation_id, price_date: q.received_date, approved: q.approved })}>{L("استخدام", "Use")}</button></td></tr>))}</tbody></table>
              )}
              <h4 style={{ marginTop: 12 }}>2) {L("مكتبة الموارد", "Resource library")}</h4>
              {!src.library.length ? <p className="muted small">{L("لا موارد مطابقة", "No matching resources")}</p> : (
                <table><tbody>{src.library.map((r: any) => (
                  <tr key={r.id}><td>{r.name} <span className="muted small">{lab(r.kind)}</span></td><td className="n">{fmt.n(r.price)} {r.currency}/{r.unit}</td>
                    <td className="small" style={{ color: old(r.price_date) ? "var(--warn)" : "var(--muted)" }}>{fmt.d(r.price_date)}</td>
                    <td><button className="sm" onClick={() => add({ kind: r.kind, part: ["labor", "equipment"].includes(r.kind) ? "apply" : "supply", description: r.name, resource_id: r.id, unit: r.unit,
                      coefficient: r.kind === "labor" && r.productivity ? +(1 / r.productivity).toFixed(6) : 1, unit_price: r.price, currency: r.currency, waste_pct: r.waste_pct || 0,
                      source: "library", source_ref: r.code, price_date: r.price_date })}>{L("إضافة", "Add")}</button></td></tr>))}</tbody></table>
              )}
            </div>
            <div>
              <h4>3) {L("أقرب بنود من مشاريع سابقة (بحث بالمعنى)", "Nearest items from past projects")}</h4>
              {!src.history.length ? <p className="muted small">{L("لا بنود سابقة مشابهة", "No similar past items")}</p> : (
                <table><tbody>{src.history.map((h: any) => (
                  <tr key={h.item_id} className="ai-row"><td className="small">{h.tender_code} / {h.item_ref} <Badge k={h.outcome} /><div className="desc">{h.description.slice(0, 80)}</div></td>
                    <td className="n">{h.direct_rate ? <>{fmt.n(h.adj_direct_rate)} <span className="small muted">{L("مباشر", "direct")}</span></> : h.final_rate ? <>{fmt.n(h.adj_final_rate)} <span className="small muted">{L("نهائي", "final")}</span></> : "—"}
                      <div className="small muted">{fmt.d(h.date)}{h.index_factor ? ` · ${L("معدل بالمؤشر", "index-adj.")} ×${h.index_factor.toFixed(2)}` : ""}</div></td><td><AIBadge conf={h.score} /></td>
                    <td><button className="sm ai-btn" onClick={() => run(async () => { await api.post(`/estimates/${est.id}/items/${item.id}/from-history`, { history_item_id: h.item_id, score: h.score }); onSaved(); reloadSrc(); })}>{h.reference_import ? L("استخدام السعر", "Use rate") : L("نسخ التحليل", "Copy build-up")}</button></td></tr>))}</tbody></table>
              )}
              {src.templates.length > 0 && <><h4 style={{ marginTop: 12 }}>{L("قوالب التحليل", "Build-up templates")}</h4>
                {src.templates.map((t: any) => <button key={t.id} className="sm" style={{ margin: 3 }} onClick={() => run(async () => { await api.post(`/estimates/${est.id}/apply-template`, { template_id: t.id, item_ids: [item.id] }); onSaved(); })}>{t.name}</button>)}</>}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function BuildUp({ est, calc, onChange }: { est: any; calc: any; onChange: () => void }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const [items] = useLoad<any[]>(`/tenders/${tender.id}/boq`);
  const [sel, setSel] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [onlyUnpriced, setOnlyUnpriced] = useState(false);
  const rows = useMemo(() => Object.fromEntries((calc?.items || []).map((r: any) => [r.id, r])), [calc]);
  const list = (items || []).filter((i) => !i.is_section && !i.is_provisional && (!q || i.description.includes(q) || i.item_ref.includes(q)) && (!onlyUnpriced || !rows[i.id]?.direct_rate));
  const item = (items || []).find((i) => i.id === sel);
  return (
    <div className="grid2" style={{ gridTemplateColumns: "minmax(300px, 420px) 1fr", alignItems: "start" }}>
      <Card title={L("10) بنود المقايسة", "10) BOQ items")} actions={<label className="row gap small"><input type="checkbox" checked={onlyUnpriced} onChange={(e) => setOnlyUnpriced(e.target.checked)} />{L("غير المسعّر", "Unpriced")}</label>}>
        <input placeholder={L("بحث", "Search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <div className="tbl-wrap" style={{ maxHeight: "70vh" }}><table>
          <tbody>{list.map((i) => {
            const r = rows[i.id];
            return (
              <tr key={i.id} className={`clickable ${sel === i.id ? "sel" : ""}`} onClick={() => setSel(i.id)}>
                <td>{i.item_ref}</td><td className="small">{i.description.slice(0, 70)}<div><Badge k={i.scope} /></div></td>
                <td className="n">{r?.direct_rate ? fmt.n(r.direct_rate) : <Badge tone="err">{L("بدون سعر", "unpriced")}</Badge>}
                  {r?.unapproved_lines > 0 && <div><AIBadge /></div>}</td>
              </tr>);
          })}</tbody>
        </table></div>
      </Card>
      {item ? <Editor key={item.id} item={item} est={est} onSaved={onChange} /> : <Card><Empty>{L("اختر بندًا لتحليل سعره", "Select an item to build up its rate")}</Empty></Card>}
    </div>
  );
}
