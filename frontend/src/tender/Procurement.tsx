import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { AIBadge, Badge, Card, Empty, Field, FileButton, Modal, NumIn, Select, TextIn, useAction, useCan, useFmt, useLoad } from "../ui";
import { EstimatePicker, useTender } from "./TenderPage";

function ManualQuote({ pkg, items, onClose, onDone }: { pkg: any; items: any[]; onClose: () => void; onDone: () => void }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const { run } = useAction();
  const [sups] = useLoad<any[]>("/suppliers");
  const [f, setF] = useState<any>({ scope: pkg.scope, currency: tender.base_currency, includes_transport: true, rates: {} });
  const save = () => run(async () => {
    await api.post(`/tenders/${tender.id}/quotations`, { ...f, package_id: pkg.id,
      lines: Object.entries(f.rates).filter(([, v]) => v !== "" && v != null).map(([k, v]) => ({ boq_item_id: Number(k), unit_rate: v })) });
    onDone(); onClose();
  }, L("تم حفظ العرض", "Quotation saved"));
  return (
    <Modal wide title={`${L("إدخال عرض سعر", "Enter quotation")} — ${pkg.name}`} onClose={onClose}>
      <div className="form">
        <Field label={L("المورد / مقاول الباطن", "Supplier / subcontractor")}>
          <Select value={f.supplier_id ?? ""} onChange={(v) => setF({ ...f, supplier_id: Number(v) })} options={[["", "—"], ...(sups || []).map((s) => [s.id, s.name] as [number, string])]} /></Field>
        <Field label={L("النطاق", "Scope")}><Select value={f.scope} onChange={(v) => setF({ ...f, scope: v })} options={["supply", "apply", "supply_apply"].map((s) => [s, lab(s)])} /></Field>
        <Field label={L("العملة", "Currency")}><input value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></Field>
        <Field label={L("مرجع العرض", "Reference")}><input value={f.reference || ""} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
        <Field label={L("صالح حتى", "Valid until")}><input type="date" value={f.valid_until || ""} onChange={(e) => setF({ ...f, valid_until: e.target.value })} /></Field>
        <Field label={L("مدة التوريد (يوم)", "Lead time (days)")}><input type="number" value={f.lead_time_days || ""} onChange={(e) => setF({ ...f, lead_time_days: e.target.value })} /></Field>
      </div>
      <div className="tbl-wrap" style={{ maxHeight: 360, marginTop: 12 }}><table>
        <thead><tr><th>{L("رقم", "Ref")}</th><th>{L("الوصف", "Description")}</th><th>{L("الوحدة", "Unit")}</th><th className="n">{L("الكمية", "Qty")}</th><th>{L("سعر الوحدة", "Unit rate")}</th></tr></thead>
        <tbody>{items.map((i) => (
          <tr key={i.id}><td>{i.item_ref}</td><td className="desc">{i.description}</td><td>{i.unit}</td><td className="n">{i.quantity}</td>
            <td><input type="number" className="num" value={f.rates[i.id] ?? ""} onChange={(e) => setF({ ...f, rates: { ...f.rates, [i.id]: e.target.value } })} /></td></tr>))}</tbody>
      </table></div>
      <button className="primary" style={{ marginTop: 10 }} disabled={!f.supplier_id} onClick={save}>{L("حفظ", "Save")}</button>
    </Modal>
  );
}

function QuoteHeader({ q, onDone }: { q: any; onDone: () => void }) {
  const { L } = useI18n();
  const lab = useLabel();
  const can = useCan();
  const { run } = useAction();
  const dis = !can("procurement.manage");
  const up = (k: string) => (v: any) => run(async () => { await api.patch(`/quotations/${q.id}`, { [k]: v }); onDone(); });
  const unapproved = q.lines.filter((l: any) => !l.approved).length;
  return (
    <tr className={unapproved ? "ai-row" : ""}>
      <td><b>{q.supplier}</b> {q.origin === "ai" && <AIBadge />}<div className="small muted">{q.reference} · {lab(q.origin)}</div></td>
      <td><Badge k={q.scope} /></td>
      <td><TextIn className="num sm" value={q.currency} onCommit={(v) => up("currency")(v.toUpperCase())} disabled={dis} /></td>
      <td><input type="date" value={q.valid_until || ""} disabled={dis} onChange={(e) => up("valid_until")(e.target.value || null)} /></td>
      <td><NumIn className="sm" value={q.lead_time_days} onCommit={up("lead_time_days")} disabled={dis} /></td>
      <td><input type="checkbox" checked={q.includes_vat} disabled={dis} onChange={(e) => up("includes_vat")(e.target.checked)} /></td>
      <td><input type="checkbox" checked={q.includes_transport} disabled={dis} onChange={(e) => up("includes_transport")(e.target.checked)} />
        {!q.includes_transport && <NumIn className="sm" value={q.transport_adjust_pct} onCommit={up("transport_adjust_pct")} disabled={dis} placeholder="%" />}</td>
      <td><NumIn className="sm" value={q.discount_pct} onCommit={up("discount_pct")} disabled={dis} /></td>
      <td><NumIn className="sm" value={q.other_adjust_pct} onCommit={up("other_adjust_pct")} disabled={dis} /></td>
      <td style={{ minWidth: 160 }}><TextIn value={q.exclusions} onCommit={up("exclusions")} disabled={dis} placeholder={L("الاستثناءات", "Exclusions")} /></td>
      <td className="row gap">
        {unapproved > 0 && !dis && <button className="sm ok" onClick={() => run(async () => { await api.post(`/quotations/${q.id}/approve-lines`); onDone(); })}>{L("اعتماد التفريغ", "Approve lines")} ({unapproved})</button>}
        {q.document_id && <button className="sm ghost" onClick={() => api.download(`/documents/${q.document_id}/file`)}>📄</button>}
        {!dis && <button className="sm ghost" onClick={() => run(async () => { await api.del(`/quotations/${q.id}`); onDone(); })}>✕</button>}
      </td>
    </tr>
  );
}

function Evaluation({ ev, onDone }: { ev: any; onDone: () => void }) {
  const { L, lang } = useI18n();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const dis = !can("procurement.manage");
  const setScore = (r: any, k: string, v: number) => run(async () => { await api.patch(`/quotations/${r.quotation_id}`, { tech_scores: { ...r.scores, [k]: v } }); onDone(); });
  const ranked = [...ev.rows].sort((a: any, b: any) => (a.rank ?? 99) - (b.rank ?? 99));
  return (
    <Card title={L("التقييم الفني مقابل المالي للعروض", "Technical vs financial evaluation")} actions={
      <span className="muted small">{L("الوزن", "Weights")}: {L("فني", "technical")} {ev.technical_weight}% · {L("مالي", "financial")} {ev.financial_weight}% · {L("حد النجاح الفني", "technical pass")} {ev.technical_pass_pct}%</span>}>
      <div className="tbl-wrap"><table>
        <thead><tr><th>{L("المعيار الفني", "Technical criterion")}</th><th className="n">{L("الوزن", "Weight")}</th>{ev.rows.map((r: any) => <th key={r.quotation_id}>{r.supplier}<div><Badge k={r.scope} /></div></th>)}</tr></thead>
        <tbody>
          {ev.criteria.map((c: any) => (
            <tr key={c.key}><td>{lang === "ar" ? c.ar : c.en}</td><td className="n">{c.weight}%</td>
              {ev.rows.map((r: any) => (
                <td key={r.quotation_id}><select value={r.scores[c.key] || ""} disabled={dis} onChange={(e) => setScore(r, c.key, Number(e.target.value))}>
                  <option value="">—</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select></td>))}</tr>))}
          <tr className="tot"><td colSpan={2}>{L("الدرجة الفنية", "Technical score")}</td>{ev.rows.map((r: any) => <td key={r.quotation_id}>{fmt.p(r.technical_pct)} {!r.complete_scoring ? <Badge tone="warn">{L("غير مكتمل", "incomplete")}</Badge> : r.passes_technical ? <Badge tone="ok">{L("ناجح", "pass")}</Badge> : <Badge tone="err">{L("راسب", "fail")}</Badge>}</td>)}</tr>
          <tr className="tot"><td colSpan={2}>{L("الدرجة المالية (أقل سعر = 100)", "Financial score (lowest = 100)")}</td>{ev.rows.map((r: any) => <td key={r.quotation_id}>{fmt.p(r.financial_pct)} <span className="muted small">{fmt.m(r.total_base)}</span>{r.missing_items > 0 && <Badge tone="err">{r.missing_items} {L("ناقص", "missing")}</Badge>}</td>)}</tr>
          <tr className="tot"><td colSpan={2}>{L("الدرجة المجمعة", "Combined score")}</td>{ev.rows.map((r: any) => <td key={r.quotation_id} className={r.quotation_id === ev.recommended ? "low" : ""}>{fmt.p(r.combined_pct)} {r.rank && <Badge>#{r.rank}</Badge>}</td>)}</tr>
        </tbody>
      </table></div>
      {ev.recommended ? <div className="alert info" style={{ marginTop: 10 }}>{L("الترتيب حسب الدرجة المجمعة للعروض الناجحة فنيًا:", "Ranking of technically compliant quotes by combined score:")} {ranked.filter((r: any) => r.rank).map((r: any) => `#${r.rank} ${r.supplier}`).join(" ← ")}</div>
        : <p className="muted small">{L("أكمل درجات المعايير الفنية لكل عرض لظهور الترتيب.", "Score every technical criterion for each quote to see the ranking.")}</p>}
    </Card>
  );
}

export default function Procurement() {
  const { tender, estimateId, estimate, reloadEstimates } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [pkgs, reloadP] = useLoad<any[]>(`/tenders/${tender.id}/packages`);
  const [pid, setPid] = useState<number | null>(null);
  useEffect(() => { if (pkgs?.length && !pid) setPid(pkgs.find((p) => p.execution !== "self")?.id || pkgs[0].id); }, [pkgs]);
  const pkg = pkgs?.find((p) => p.id === pid);
  const [quotes, reloadQ] = useLoad<any[]>(pid ? `/tenders/${tender.id}/quotations?package_id=${pid}` : null);
  const [cmp, reloadC] = useLoad<any>(pid ? `/packages/${pid}/comparison${estimateId ? `?estimate_id=${estimateId}` : ""}` : null);
  const [sups] = useLoad<any[]>("/suppliers");
  const [manual, setManual] = useState(false);
  const [upSup, setUpSup] = useState("");
  const [upScope, setUpScope] = useState("");
  const refresh = () => { reloadQ(); reloadC(); reloadP(); };
  const canSel = can("procurement.manage") && estimate && ["draft", "rejected"].includes(estimate.status);
  const select = (q: any) => run(async () => {
    const r = await api.post(`/packages/${pid}/select`, { quotation_id: q.quotation_id, estimate_id: estimateId });
    refresh(); reloadEstimates();
    return r;
  }, L("تم اختيار العرض ونقل أسعاره لتحليل البنود", "Quotation selected and written to the build-up"));
  const flagText = (f: any) => f.code === "lead_time" ? `${L("مدة التوريد", "Lead time")} ${f.days} ${L("يوم > المطلوب", "d > needed by month")} ${f.required_month}`
    : f.code === "vendor_not_approved" ? `${L("مورد غير معتمد", "Vendor not approved")} (${f.status})`
    : f.code === "validity_short" ? `${L("ينتهي قبل نهاية صلاحية عرضنا", "Expires before our bid validity")} (${f.needed})` : `${L("لا يوجد سعر صرف", "Missing FX")} ${f.currency}`;
  return (
    <div className="stack">
      <div className="row gap wrap between">
        <div className="row gap wrap">
          {(pkgs || []).map((p) => <button key={p.id} className={p.id === pid ? "primary" : ""} onClick={() => setPid(p.id)}>{p.name} <span className="small">({lab(p.execution)})</span></button>)}
        </div>
        <EstimatePicker />
      </div>
      {!pkgs?.length && <Empty>{L("قسّم المقايسة إلى حزم أولًا (تبويب المقايسة)", "Create packages first (BOQ tab)")}</Empty>}
      {pkg && (
        <Card title={`9) ${L("طلب عروض الأسعار", "Request for quotations")} — ${pkg.name}`} actions={can("procurement.manage") && <>
          <button onClick={() => run(() => api.download(`/packages/${pkg.id}/rfq.xlsx`))}>⬇ {L("ملف RFQ للموردين", "RFQ file for suppliers")}</button>
          <select value={upSup} onChange={(e) => setUpSup(e.target.value)}><option value="">{L("المورد (اختياري)", "Supplier (optional)")}</option>{(sups || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <select value={upScope} onChange={(e) => setUpScope(e.target.value)}><option value="">{L("نطاق العرض", "Quote scope")}</option>{["supply", "apply", "supply_apply"].map((s) => <option key={s} value={s}>{lab(s)}</option>)}</select>
          <FileButton className="primary" disabled={busy} label={`⬆ ${L("رفع عرض (RFQ مملوء / PDF / إيميل)", "Upload quote (filled RFQ / PDF / e-mail)")}`} accept=".xlsx,.pdf,.txt,.eml,.docx"
            onFile={(f) => run(async () => { await api.upload(`/packages/${pkg.id}/quotations/upload`, f, { supplier_id: upSup, scope: upScope }); refresh(); }, L("تم تفريغ العرض", "Quotation read"))} />
          <button onClick={() => setManual(true)}>+ {L("إدخال يدوي", "Manual entry")}</button></>}>
          <p className="muted small">{L("ملف الـ RFQ المملوء يُقرأ بدقة بدون AI. عروض PDF أو الإيميل يفرغها الـ AI وتبقى بلون مختلف حتى تعتمدها. لتقسيم توريد وتركيب: اختر عرض توريد وعرض تركيب منفصلين.", "A filled RFQ file is read exactly without AI. PDF / e-mail quotes are transcribed by the AI and stay highlighted until approved. For Supply & Apply split, select one Supply quote and one Apply quote.")}</p>
          {!quotes?.length ? <Empty>{L("لا عروض بعد", "No quotations yet")}</Empty> : (
            <div className="tbl-wrap"><table>
              <thead><tr><th>{L("المورد", "Supplier")}</th><th>{L("النطاق", "Scope")}</th><th>{L("العملة", "Cur")}</th><th>{L("صالح حتى", "Valid until")}</th><th>{L("توريد (يوم)", "Lead (d)")}</th>
                <th>{L("شامل ض.ق.م", "Incl. VAT")}</th><th>{L("شامل النقل", "Incl. transport")}</th><th>{L("خصم %", "Disc %")}</th><th>{L("تسوية نطاق %", "Scope adj %")}</th><th>{L("الاستثناءات", "Exclusions")}</th><th /></tr></thead>
              <tbody>{quotes.map((q) => <QuoteHeader key={q.id} q={q} onDone={refresh} />)}</tbody>
            </table></div>
          )}
        </Card>
      )}
      {cmp && cmp.quotations.length > 0 && (
        <Card title={L("جدول المقارنة (Comparison Sheet) — أسعار موحدة النطاق بعملة التسعير", "Comparison sheet — levelled rates in base currency")}>
          <div className="tbl-wrap"><table>
            <thead><tr><th>{L("رقم", "Ref")}</th><th>{L("الوصف", "Description")}</th><th className="n">{L("الكمية", "Qty")}</th>
              {cmp.quotations.map((q: any) => <th key={q.quotation_id} className="n">{q.supplier}<div><Badge k={q.scope} /> {q.currency}</div></th>)}</tr></thead>
            <tbody>
              {cmp.items.map((it: any) => (
                <tr key={it.id}><td>{it.item_ref}</td><td className="desc">{it.description.slice(0, 90)}</td><td className="n">{fmt.n(it.quantity, 0)}</td>
                  {cmp.quotations.map((q: any) => {
                    const c = q.cells[it.id];
                    return c ? <td key={q.quotation_id} className={`n ${cmp.lowest_per_item[it.id] === q.quotation_id ? "low" : ""}`} title={`${L("السعر المعروض", "quoted")}: ${c.quoted} ${q.currency}`}>{fmt.n(c.base)}</td>
                      : <td key={q.quotation_id} className="miss">{L("غير مسعّر", "not quoted")}</td>;
                  })}</tr>))}
              <tr className="tot"><td colSpan={3}>{L("الإجمالي الموحّد", "Levelled total")}</td>
                {cmp.quotations.map((q: any) => <td key={q.quotation_id} className={`n ${cmp.lowest_complete === q.quotation_id ? "low" : ""}`}>{fmt.m(q.total_base)}</td>)}</tr>
              <tr><td colSpan={3} className="muted">{L("بنود ناقصة / تنبيهات", "Missing items / flags")}</td>
                {cmp.quotations.map((q: any) => (
                  <td key={q.quotation_id} className="small">
                    {q.missing_items > 0 && <div><Badge tone="err">{q.missing_items} {L("ناقص", "missing")}</Badge></div>}
                    {q.flags.map((f: any, i: number) => <div key={i}><Badge tone="warn">{flagText(f)}</Badge></div>)}
                    {q.payment_terms && <div className="muted">{q.payment_terms}</div>}
                  </td>))}</tr>
              <tr><td colSpan={3} />
                {cmp.quotations.map((q: any) => (
                  <td key={q.quotation_id}>{q.selected ? <Badge tone="ok">✓ {L("المختار", "Selected")}</Badge>
                    : <button className="sm primary" disabled={!canSel || busy} title={!estimate ? L("أنشئ نسخة تسعير أولًا", "Create an estimate first") : ""} onClick={() => select(q)}>{L("اختيار", "Select")}</button>}</td>))}</tr>
            </tbody>
          </table></div>
          {!estimate && <p className="alert">{L("لنقل أسعار العرض المختار، أنشئ نسخة تسعير من تبويب التسعير.", "To use the selected quote, create an estimate version in the Pricing tab.")}</p>}
        </Card>
      )}
      {cmp && cmp.quotations.length > 0 && <Evaluation ev={cmp.evaluation} onDone={refresh} />}
      {manual && pkg && cmp && <ManualQuote pkg={pkg} items={cmp.items} onClose={() => setManual(false)} onDone={refresh} />}
    </div>
  );
}
