import { useMemo, useState } from "react";
import { api } from "../api";
import { useI18n, useLabel, useName } from "../i18n";
import { AIBadge, Badge, Card, Empty, FileButton, Modal, NumIn, Select, TextIn, useAction, useCan, useFmt, useLoad } from "../ui";
import { useTender } from "./TenderPage";

const SCOPES = ["supply", "apply", "supply_apply"];

function ImportModal({ pv, onClose, onDone }: { pv: any; onClose: () => void; onDone: () => void }) {
  const { tender } = useTender();
  const { L } = useI18n();
  const { run, busy } = useAction();
  const [replace, setReplace] = useState(false);
  const go = () => run(async () => {
    const r = await api.post(`/tenders/${tender.id}/boq/import`, { document_id: pv.document_id, replace, mapping: pv.mapping });
    onDone();
    onClose();
    return r;
  }, L("تم استيراد المقايسة", "BOQ imported"));
  const colName: Record<string, string> = { ref: L("رقم البند", "Ref"), desc: L("الوصف", "Description"), unit: L("الوحدة", "Unit"), qty: L("الكمية", "Qty"), rate: L("الفئة", "Rate"), amount: L("الإجمالي", "Amount") };
  return (
    <Modal wide title={L("مراجعة قبل الاستيراد", "Review before import")} onClose={onClose}>
      <div className="stack">
        <div className="alert info">{L("تم التعرف على", "Detected")} {pv.items} {L("بند", "items")} {L("في", "in")} {Object.keys(pv.mapping).length} {L("شيت. الأعمدة:", "sheet(s). Columns:")}
          {Object.entries(pv.mapping).map(([sh, m]: any) => (
            <div key={sh} className="small">• {sh} — {L("صف العناوين", "header row")} {m.header_row}: {Object.entries(m.cols).map(([k, c]: any) => `${colName[k]}=${String.fromCharCode(64 + c)}`).join("، ")}</div>))}
        </div>
        {pv.warnings.map((w: string) => <div key={w} className="alert">{w}</div>)}
        <div className="tbl-wrap" style={{ maxHeight: 420 }}><table>
          <thead><tr><th>{L("الصف", "Row")}</th><th>{L("رقم", "Ref")}</th><th>{L("الوصف", "Description")}</th><th>{L("الوحدة", "Unit")}</th><th className="n">{L("الكمية", "Qty")}</th></tr></thead>
          <tbody>{pv.rows.map((r: any, i: number) => (
            <tr key={i} className={r.is_section ? "sec" : ""}><td className="muted">{r.sheet.slice(0, 12)}!{r.row}</td><td>{r.ref}</td><td className="desc">{r.description}</td><td>{r.unit}</td><td className="n">{r.quantity ?? ""}</td></tr>))}</tbody>
        </table></div>
        <label className="row gap"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />{L("استبدال المقايسة الحالية", "Replace the current BOQ")}</label>
        <div><button className="primary" disabled={busy} onClick={go}>{L("تأكيد الاستيراد", "Confirm import")}</button></div>
      </div>
    </Modal>
  );
}

export default function Boq() {
  const { tender } = useTender();
  const { L, lang } = useI18n();
  const lab = useLabel();
  const nm = useName();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [items, reload] = useLoad<any[]>(`/tenders/${tender.id}/boq`);
  const [pkgs, reloadP] = useLoad<any[]>(`/tenders/${tender.id}/packages`);
  const [codes] = useLoad<any[]>(`/cost-codes?project_type=${tender.project_type}`);
  const [sugg, reloadS] = useLoad<any[]>(`/tenders/${tender.id}/suggestions?status=pending&kind=cost_code`);
  const [pv, setPv] = useState<any>(null);
  const [filter, setFilter] = useState({ scope: "", pkg: "", uncoded: false, q: "" });
  const dis = !can("boq.edit");
  const suggBy = useMemo(() => Object.fromEntries((sugg || []).map((s) => [Number(s.target), s])), [sugg]);
  const l3 = (codes || []).filter((c) => c.level === 3);
  const upd = (id: number, k: string) => (v: any) => run(async () => { await api.patch("/boq/items", [{ id, [k]: v === "" ? null : v }]); reload(); });
  const refreshAll = () => { reload(); reloadP(); reloadS(); };
  const priced = (items || []).filter((i) => !i.is_section);
  const shown = (items || []).filter((i) => {
    if (i.is_section) return !filter.scope && !filter.pkg && !filter.uncoded && !filter.q;
    if (filter.scope && i.scope !== filter.scope) return false;
    if (filter.pkg && String(i.package_id) !== filter.pkg) return false;
    if (filter.uncoded && i.cost_code_id) return false;
    if (filter.q && !i.description.includes(filter.q) && !i.item_ref.includes(filter.q)) return false;
    return true;
  });
  const counts = SCOPES.map((s) => [s, priced.filter((i) => i.scope === s).length]);
  return (
    <div className="stack">
      <Card title={L("7) المقايسة — استيراد من Excel المالك ومراجعة الحصر", "7) BOQ — import the owner's Excel & check take-off")} actions={!dis && <>
        <FileButton className="primary" disabled={busy} label={L("استيراد مقايسة Excel", "Import Excel BOQ")} accept=".xlsx,.xlsm"
          onFile={(f) => run(async () => setPv(await api.upload(`/tenders/${tender.id}/boq/preview`, f)))} />
        <button onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/boq/items`, { description: L("بند جديد", "New item"), unit: "", quantity: 0 }); reload(); })}>+ {L("بند يدوي", "Manual item")}</button>
      </>}>
        <div className="row gap wrap">
          <Badge>{priced.length} {L("بند", "items")}</Badge>
          {counts.map(([s, n]) => <Badge key={s} k={String(s)}>{lab(String(s))}: {n}</Badge>)}
          <Badge tone={priced.some((i) => !i.cost_code_id) ? "warn" : "ok"}>{L("غير مكود", "uncoded")}: {priced.filter((i) => !i.cost_code_id).length}</Badge>
          {(sugg || []).length > 0 && !dis && <button className="sm ai-btn" onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/boq/accept-cost-codes`, {}); refreshAll(); }, L("تم اعتماد التكويد", "Cost codes accepted"))}>
            ✦ {L("اعتماد كل اقتراحات التكويد", "Accept all cost-code suggestions")} ({sugg!.length})</button>}
          <span className="grow" />
          <input placeholder={L("بحث", "Search")} value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
          <Select value={filter.scope} onChange={(v) => setFilter({ ...filter, scope: v })} options={[["", L("كل النطاقات", "All scopes")], ...SCOPES.map((s) => [s, lab(s)] as [string, string])]} />
          <Select value={filter.pkg} onChange={(v) => setFilter({ ...filter, pkg: v })} options={[["", L("كل الحزم", "All packages")], ...(pkgs || []).map((p) => [String(p.id), nm(p.name, p.name_en)] as [string, string])]} />
          <label className="row gap small"><input type="checkbox" checked={filter.uncoded} onChange={(e) => setFilter({ ...filter, uncoded: e.target.checked })} />{L("غير المكود فقط", "Uncoded only")}</label>
        </div>
      </Card>
      <Card>
        {!items?.length ? <Empty>{L("لم تُستورد مقايسة بعد", "No BOQ yet")}</Empty> : (
          <div className="tbl-wrap" style={{ maxHeight: "70vh" }}><table>
            <thead><tr><th>{L("رقم", "Ref")}</th><th>{L("الوصف", "Description")}</th><th>{L("الوحدة", "Unit")}</th><th className="n">{L("الكمية", "Qty")}</th>
              <th className="n">{L("حصرنا", "Our qty")}</th><th>{L("النطاق", "Scope")}</th><th>{L("كود الشركة", "Cost code")}</th><th>{L("الحزمة", "Package")}</th><th>{L("مبلغ احتياطي", "Prov. sum")}</th></tr></thead>
            <tbody>{shown.map((i) => i.is_section ? (
              <tr key={i.id} className="sec"><td>{i.item_ref}</td><td colSpan={8}>{i.description}</td></tr>
            ) : (
              <tr key={i.id}>
                <td>{i.item_ref}</td>
                <td className="desc" style={{ minWidth: 280 }}>{i.description}</td>
                <td>{i.unit}</td>
                <td className="n"><NumIn value={i.quantity} onCommit={upd(i.id, "quantity")} disabled={dis} /></td>
                <td className="n"><NumIn value={i.checked_quantity} onCommit={upd(i.id, "checked_quantity")} disabled={dis}
                  className={i.checked_quantity != null && i.quantity && Math.abs(i.checked_quantity - i.quantity) / i.quantity > 0.05 ? "warn" : ""} /></td>
                <td><Select value={i.scope} disabled={dis} onChange={upd(i.id, "scope")} options={SCOPES.map((s) => [s, lab(s)])} /></td>
                <td style={{ minWidth: 200 }}>
                  {suggBy[i.id] && !i.cost_code_id ? (
                    <div className="row gap"><AIBadge conf={suggBy[i.id].confidence} /><span className="small">{suggBy[i.id].payload.code} {suggBy[i.id].payload.name}</span>
                      {!dis && <button className="sm ok" onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/boq/accept-cost-codes`, { ids: [suggBy[i.id].id] }); refreshAll(); })}>✓</button>}</div>
                  ) : (
                    <Select value={i.cost_code_id ?? ""} disabled={dis} onChange={upd(i.id, "cost_code_id")} options={[["", "—"], ...l3.map((c) => [c.id, `${c.code.replace(/\.001$/, "")} ${nm(c.name_ar, c.name_en)}`] as [number, string])]} />
                  )}
                </td>
                <td><Select value={i.package_id ?? ""} disabled={dis} onChange={upd(i.id, "package_id")} options={[["", "—"], ...(pkgs || []).map((p) => [p.id, nm(p.name, p.name_en)] as [number, string])]} /></td>
                <td>{i.is_provisional ? <NumIn value={i.provisional_amount} onCommit={upd(i.id, "provisional_amount")} disabled={dis} /> :
                  <input type="checkbox" checked={false} disabled={dis} onChange={() => upd(i.id, "is_provisional")(true)} />}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
      <Card title={L("8) حزم الأعمال — تنفيذ ذاتي أم مقاول باطن", "8) Work packages — self-perform or subcontract")} actions={!dis && <>
        <button className="ai-btn" onClick={() => run(async () => { const r = await api.post(`/tenders/${tender.id}/packages/auto`); refreshAll(); return r; }, L("تم التقسيم حسب التكويد", "Grouped by cost code"))}>{L("تقسيم تلقائي حسب التكويد", "Auto-group by cost code")}</button>
        <button onClick={() => run(async () => { await api.post(`/tenders/${tender.id}/packages`, { name: L("حزمة جديدة", "New package") }); reloadP(); })}>+ {L("حزمة", "Package")}</button></>}>
        {!pkgs?.length ? <Empty>{L("لا حزم بعد", "No packages yet")}</Empty> : (
          <table>
            <thead><tr><th>{L("الحزمة", "Package")}</th><th>{L("طريقة التنفيذ", "Execution")}</th><th>{L("النطاق", "Scope")}</th><th className="n">{L("البنود", "Items")}</th><th>{L("مطلوبة بالموقع شهر", "Needed on site (month)")}</th></tr></thead>
            <tbody>{pkgs.map((p) => {
              const up = (k: string) => (v: any) => run(async () => { await api.patch(`/packages/${p.id}`, { [k]: v }); reloadP(); });
              return (
                <tr key={p.id}>
                  <td>{lang === "en" ? <TextIn value={p.name_en || p.name} onCommit={up("name_en")} disabled={dis} /> : <TextIn value={p.name} onCommit={up("name")} disabled={dis} />}</td>
                  <td><Select value={p.execution} disabled={dis} onChange={up("execution")} options={["self", "subcontract", "supply_only", "mixed"].map((x) => [x, lab(x)])} /></td>
                  <td><Select value={p.scope} disabled={dis} onChange={up("scope")} options={SCOPES.map((s) => [s, lab(s)])} /></td>
                  <td className="n">{p.items}</td>
                  <td><NumIn className="sm" value={p.required_on_site_month} onCommit={up("required_on_site_month")} disabled={dis} /></td>
                </tr>);
            })}</tbody>
          </table>
        )}
      </Card>
      {pv && <ImportModal pv={pv} onClose={() => setPv(null)} onDone={refreshAll} />}
      <p className="muted small">{fmt.n(priced.reduce((s, i) => s + (i.quantity || 0), 0), 0)} {L("إجمالي الكميات (للمراجعة)", "total quantity (sanity check)")}</p>
    </div>
  );
}
