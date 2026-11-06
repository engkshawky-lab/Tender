import { useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { Card, Empty, FileButton, NumIn, Select, Tabs, TextIn, useAction, useCan, useFmt, useLoad } from "../ui";

function Resources() {
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run } = useAction();
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [rows, reload] = useLoad<any[]>(`/resources?${kind ? `kind=${kind}&` : ""}${q ? `q=${encodeURIComponent(q)}` : ""}`);
  const [settings] = useLoad<any>("/settings");
  const dis = !can("library.manage");
  const age = settings?.price_age_days || 90;
  const up = (r: any, k: string) => (v: any) => run(async () => { await api.patch(`/resources/${r.id}`, { [k]: v, ...(k === "price" ? { price_date: new Date().toISOString().slice(0, 10) } : {}) }); reload(); });
  return (
    <Card title={L("مكتبة الموارد — كل سعر له تاريخ وعملة ومصدر", "Resource library — every price has a date, currency and source")} actions={<>
      <input placeholder={L("بحث", "Search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <Select value={kind} onChange={setKind} options={[["", L("الكل", "All")], ...["material", "labor", "equipment", "subcontract"].map((k) => [k, lab(k)] as [string, string])]} />
      {!dis && <FileButton label={L("استيراد قائمة أسعار Excel", "Import Excel price list")} accept=".xlsx" onFile={(f) => run(async () => { const r = await api.upload("/resources/import", f); reload(); return r; }, L("تم تحديث مكتبة الأسعار", "Price library updated"))} />}
      {!dis && <button onClick={() => run(async () => { await api.post("/resources", { name: L("مورد جديد", "New resource"), kind: kind || "material", unit: "", price: 0 }); reload(); })}>+ {L("مورد", "Resource")}</button>}</>}>
      <div className="tbl-wrap" style={{ maxHeight: "65vh" }}><table>
        <thead><tr><th>{L("الكود", "Code")}</th><th>{L("الاسم", "Name")}</th><th>{L("النوع", "Kind")}</th><th>{L("الوحدة", "Unit")}</th><th className="n">{L("السعر", "Price")}</th><th>{L("العملة", "Cur")}</th><th>{L("تاريخ السعر", "Price date")}</th><th className="n">{L("هالك %", "Waste %")}</th><th>{L("المصدر", "Source")}</th></tr></thead>
        <tbody>{(rows || []).map((r) => {
          const stale = (Date.now() - new Date(r.price_date).getTime()) / 86400000 > age;
          return (
            <tr key={r.id}>
              <td><TextIn className="num sm" value={r.code} onCommit={up(r, "code")} disabled={dis} /></td>
              <td><TextIn value={r.name} onCommit={up(r, "name")} disabled={dis} /></td>
              <td><Select value={r.kind} disabled={dis} onChange={up(r, "kind")} options={["material", "labor", "equipment", "subcontract"].map((k) => [k, lab(k)])} /></td>
              <td><TextIn className="num sm" value={r.unit} onCommit={up(r, "unit")} disabled={dis} /></td>
              <td className="n"><NumIn value={r.price} onCommit={up(r, "price")} disabled={dis} /></td>
              <td><TextIn className="num sm" value={r.currency} onCommit={up(r, "currency")} disabled={dis} /></td>
              <td style={{ color: stale ? "var(--warn)" : "" }}>{fmt.d(r.price_date)} {stale && "⚠"}</td>
              <td className="n"><NumIn className="sm" value={r.waste_pct} onCommit={up(r, "waste_pct")} disabled={dis} /></td>
              <td><TextIn value={r.source} onCommit={up(r, "source")} disabled={dis} /></td>
            </tr>);
        })}</tbody>
      </table></div>
    </Card>
  );
}

function CostCodes() {
  const { L, lang } = useI18n();
  const lab = useLabel();
  const [rows] = useLoad<any[]>("/cost-codes");
  const [pt, setPt] = useState("building");
  const list = (rows || []).filter((c) => c.level < 3 && (c.project_type === pt || c.project_type === "common"));
  return (
    <Card title={L("شجرة التكويد: قسم ← نوع عمل ← بند قياسي", "Cost-code tree: division → work type → standard item")} actions={
      <Select value={pt} onChange={setPt} options={[["building", lab("building")], ["infra", lab("infra")]]} />}>
      {!list.length ? <Empty>—</Empty> : (
        <table><tbody>{list.map((c) => (
          <tr key={c.id} className={c.level === 1 ? "sec" : ""}><td style={{ paddingInlineStart: c.level === 2 ? 28 : 10 }}>{c.code}</td><td>{lang === "ar" ? c.name_ar : c.name_en}</td><td>{c.unit}</td></tr>))}</tbody></table>
      )}
    </Card>
  );
}

function Templates() {
  const { L } = useI18n();
  const lab = useLabel();
  const [rows] = useLoad<any[]>("/templates");
  return (
    <Card title={L("قوالب تحليل البنود (بأسعار مرجعية)", "Rate build-up templates (with reference prices)")}>
      <p className="muted small">{L("احفظ أي بند محلَّل كقالب من شاشة تحليل البنود، ويُطبق على بنود مشابهة في أي مناقصة.", "Save any analysed item as a template from the build-up screen and apply it to similar items in any tender.")}</p>
      {(rows || []).map((t) => (
        <div key={t.id} style={{ marginBottom: 12 }}><b>{t.name}</b> <span className="muted">/{t.unit}</span>
          <div className="small muted">{t.lines.map((l: any) => `${l.description} × ${l.coefficient}${l.use_template_price ? ` @ ${l.unit_price} ${l.currency}` : ""} (${lab(l.part)})`).join(" · ")}</div></div>))}
    </Card>
  );
}

export default function Library() {
  const { L } = useI18n();
  const [tab, setTab] = useState("resources");
  return (
    <div>
      <div className="page-h"><h1>{L("مكتبة الأسعار والقوالب", "Price library & templates")}</h1></div>
      <Tabs tabs={[{ key: "resources", label: L("الموارد والأسعار", "Resources & prices") }, { key: "codes", label: L("شجرة التكويد", "Cost codes") }, { key: "templates", label: L("قوالب التحليل", "Templates") }]} active={tab} onChange={setTab} />
      {tab === "resources" && <Resources />}
      {tab === "codes" && <CostCodes />}
      {tab === "templates" && <Templates />}
    </div>
  );
}
