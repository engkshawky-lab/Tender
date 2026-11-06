import { useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { Badge, Card, Empty, Field, FileButton, Select, useAction, useCan, useFmt, useLoad } from "../ui";

export default function References() {
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [refs, reload] = useLoad<any[]>("/references");
  const [f, setF] = useState<any>({ project_type: "building", outcome: "historical", rate_basis: "final" });
  const [q, setQ] = useState("");
  const [unit, setUnit] = useState("");
  const [hits, setHits] = useState<any[] | null>(null);
  const upload = (file: File) => run(async () => {
    const r = await api.upload("/references/import", file, f);
    reload();
    return r;
  }, L("تم استيراد الملف كمرجع تسعير", "File imported as a pricing reference"));
  return (
    <div className="stack">
      <div className="page-h"><div><h1>{L("المرجعية السعرية — ملفات تسعير سابقة", "Pricing references — previous priced files")}</h1>
        <div className="sub">{L("المقايسات المسعرة من مناقصات سابقة (فزنا أو خسرنا) تُستخدم كمرجع: اقتراح أسعار، كشف الأسعار الشاذة، ومقارنة التسعير الحالي بها بندًا ببند.", "Priced BOQs from past tenders (won or lost) are used to suggest rates, flag outliers and compare the current estimate item by item.")}</div></div></div>
      {can("library.manage") && (
        <Card title={L("استيراد ملف مسعر قديم (Excel)", "Import an old priced file (Excel)")}>
          <div className="form">
            <Field label={L("اسم المشروع", "Project name")}><input value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label={L("نوع المشروع", "Project type")}><Select value={f.project_type} onChange={(v) => setF({ ...f, project_type: v })} options={[["building", lab("building")], ["infra", lab("infra")]]} /></Field>
            <Field label={L("النتيجة", "Outcome")}><Select value={f.outcome} onChange={(v) => setF({ ...f, outcome: v })} options={[["won", L("فزنا", "Won")], ["lost", L("خسرنا", "Lost")], ["historical", L("مرجع فقط", "Reference only")]]} /></Field>
            <Field label={L("تاريخ الأسعار", "Price date")}><input type="date" value={f.reference_date || ""} onChange={(e) => setF({ ...f, reference_date: e.target.value })} /></Field>
            <Field label={L("نوع الأسعار في الملف", "Rates in the file are")}><Select value={f.rate_basis} onChange={(v) => setF({ ...f, rate_basis: v })} options={[["final", L("أسعار بيع نهائية (شاملة غير المباشر والربح)", "Final selling rates (incl. overheads & profit)")], ["direct", L("تكلفة مباشرة (من شيت التحليل)", "Direct cost (from the analysis sheet)")]]} /></Field>
            <Field label={L("المالك", "Owner")}><input value={f.owner || ""} onChange={(e) => setF({ ...f, owner: e.target.value })} /></Field>
          </div>
          <div className="row gap" style={{ marginTop: 10 }}>
            <FileButton className="primary" disabled={busy || !f.name} label={L("اختيار الملف المسعر واستيراده", "Choose priced file & import")} accept=".xlsx,.xlsm" onFile={upload} />
            {!f.name && <span className="muted small">{L("اكتب اسم المشروع أولًا", "Enter the project name first")}</span>}
          </div>
          <p className="muted small">{L("يُقرأ عمود الفئة/السعر من نفس شكل ملف المالك، وتُكوَّد البنود تلقائيًا. للحصول على أفضل مقارنة: استورد ملفات التحليل (التكلفة المباشرة) عند توفرها.", "The rate column is read from the owner's layout and items are auto-coded. For best comparisons import the cost analysis sheets when available.")}</p>
        </Card>
      )}
      <Card title={L("بحث في المرجعية", "Search the references")}>
        <div className="row gap wrap">
          <input className="grow" placeholder={L("وصف البند — مثال: خرسانة مسلحة أسقف", "Item description — e.g. RC slab")} value={q} onChange={(e) => setQ(e.target.value)} />
          <input className="num sm" placeholder={L("الوحدة", "Unit")} value={unit} onChange={(e) => setUnit(e.target.value)} />
          <button className="primary" disabled={!q} onClick={() => run(async () => setHits(await api.get(`/references/search?q=${encodeURIComponent(q)}&unit=${encodeURIComponent(unit)}&k=15`)))}>{L("بحث", "Search")}</button>
        </div>
        {hits && (!hits.length ? <Empty>{L("لا نتائج", "No results")}</Empty> : (
          <div className="tbl-wrap" style={{ marginTop: 10 }}><table>
            <thead><tr><th>{L("المرجع", "Reference")}</th><th>{L("البند", "Item")}</th><th>{L("الوحدة", "Unit")}</th><th className="n">{L("التكلفة المباشرة", "Direct")}</th><th className="n">{L("السعر النهائي", "Final")}</th><th>{L("التاريخ", "Date")}</th><th>{L("التطابق", "Match")}</th></tr></thead>
            <tbody>{hits.map((h, i) => (
              <tr key={i}><td>{h.tender_code} <Badge k={h.outcome} /><div className="small muted">{h.tender_name}</div></td><td className="desc small">{h.item_ref} — {h.description}</td><td>{h.unit}</td>
                <td className="n">{fmt.n(h.direct_rate)}</td><td className="n">{fmt.n(h.final_rate)}</td><td>{fmt.d(h.date)}</td><td>{Math.round(h.score * 100)}%</td></tr>))}</tbody>
          </table></div>
        ))}
      </Card>
      <Card title={L("المشاريع المرجعية", "Reference projects")}>
        {!refs?.length ? <Empty>{L("لا مراجع بعد — استورد ملفات مسعرة قديمة أو سجّل نتائج المناقصات", "No references yet — import old priced files or record tender results")}</Empty> : (
          <table><thead><tr><th>{L("الكود", "Code")}</th><th>{L("المشروع", "Project")}</th><th>{L("النوع", "Type")}</th><th>{L("النتيجة", "Outcome")}</th><th>{L("المصدر", "Source")}</th><th className="n">{L("بنود مسعرة", "Priced items")}</th><th>{L("تاريخ الأسعار", "Price date")}</th>{can("markup.view") && <th className="n">{L("الإجمالي", "Total")}</th>}</tr></thead>
            <tbody>{refs.map((r) => (
              <tr key={r.id}><td>{r.code}</td><td>{r.name}</td><td>{lab(r.project_type)}</td><td><Badge k={r.status} /></td>
                <td className="small">{r.reference_import ? (r.rate_basis === "direct" ? L("ملف تحليل مستورد", "Imported cost sheet") : L("مقايسة مسعرة مستوردة", "Imported priced BOQ")) : L("تسعير على المنصة", "Priced on the platform")}</td>
                <td className="n">{r.items}</td><td>{fmt.d(r.date)}</td>{can("markup.view") && <td className="n">{fmt.m(r.total)}</td>}</tr>))}</tbody></table>
        )}
      </Card>
    </div>
  );
}
