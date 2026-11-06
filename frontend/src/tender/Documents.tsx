import { useState } from "react";
import { api } from "../api";
import { useI18n, useLabel } from "../i18n";
import { Badge, Card, Empty, FileButton, Modal, Select, useAction, useCan, useFmt, useLoad } from "../ui";
import { useTender } from "./TenderPage";

const TYPES = ["invitation", "drawings", "specs", "boq", "general_conditions", "particular_conditions", "addendum", "other"];

export default function Documents() {
  const { tender } = useTender();
  const { L } = useI18n();
  const lab = useLabel();
  const fmt = useFmt();
  const can = useCan();
  const { run, busy } = useAction();
  const [docs, reload] = useLoad<any[]>(`/tenders/${tender.id}/documents`);
  const [type, setType] = useState("particular_conditions");
  const [rev, setRev] = useState("0");
  const [supersedes, setSupersedes] = useState("");
  const [diff, setDiff] = useState<any>(null);
  const [view, setView] = useState<any>(null);
  const upload = (f: File) => run(async () => {
    await api.upload(`/tenders/${tender.id}/documents`, f, { doc_type: type, revision: rev, supersedes_id: supersedes || undefined });
    reload();
  }, L("تم رفع المستند واستخراج النص", "Uploaded and text extracted"));
  const list = (docs || []).filter((d) => !["site_photo", "quotation"].includes(d.doc_type));
  const statusTone: Record<string, string> = { extracted: "ok", needs_ocr: "warn", failed: "err", none: "" };
  return (
    <div className="stack">
      {can("documents.manage") && (
        <Card title={L("3) رفع وتسجيل المستندات", "3) Upload & register documents")}>
          <div className="row gap wrap">
            <Select value={type} onChange={setType} options={TYPES.map((t) => [t, lab(t)])} />
            <label className="row gap"><span className="muted small">{L("رقم الإصدار", "Revision")}</span><input className="num sm" value={rev} onChange={(e) => setRev(e.target.value)} /></label>
            <select value={supersedes} onChange={(e) => setSupersedes(e.target.value)}>
              <option value="">{L("يحل محل… (اختياري)", "Supersedes… (optional)")}</option>
              {list.filter((d) => d.is_latest).map((d) => <option key={d.id} value={d.id}>{d.title} (rev {d.revision})</option>)}
            </select>
            <FileButton className="primary" disabled={busy} label={L("اختيار ملف ورفعه", "Choose file & upload")} accept=".pdf,.docx,.xlsx,.txt,.png,.jpg,.jpeg" onFile={upload} />
          </div>
          <p className="muted small">{L("PDF و Word و Excel يُستخرج نصها بأرقام الصفحات. الملفات المصورة تُقرأ بالـ AI (OCR عربي وإنجليزي) عند تفعيل مفتاح API.", "PDF, Word and Excel are extracted with page numbers. Scanned files are read by the AI (Arabic/English OCR) when an API key is configured.")}</p>
        </Card>
      )}
      <Card title={L("سجل المستندات", "Document register")}>
        {!list.length ? <Empty>{L("لم تُرفع مستندات بعد", "No documents yet")}</Empty> : (
          <div className="tbl-wrap"><table>
            <thead><tr><th>{L("النوع", "Type")}</th><th>{L("العنوان", "Title")}</th><th>{L("الإصدار", "Rev")}</th><th>{L("الصفحات", "Pages")}</th><th>{L("قراءة النص", "Text")}</th><th>{L("الحالة", "State")}</th><th>{L("تاريخ الرفع", "Uploaded")}</th><th /></tr></thead>
            <tbody>{list.map((d) => (
              <tr key={d.id} style={{ opacity: d.is_latest ? 1 : 0.55 }}>
                <td>{lab(d.doc_type)}</td><td>{d.title}</td><td>{d.revision}</td><td className="n">{d.pages}</td>
                <td><Badge tone={statusTone[d.text_status]}>{lab(d.text_status)}</Badge></td>
                <td>{d.is_latest ? <Badge tone="ok">{L("آخر إصدار", "latest")}</Badge> : <Badge>{L("ملغى بإصدار أحدث", "superseded")}</Badge>}</td>
                <td>{fmt.d(d.created_at)}</td>
                <td className="row gap">
                  <button className="sm" onClick={() => run(() => api.download(`/documents/${d.id}/file`, d.filename))}>{L("تنزيل", "Download")}</button>
                  {d.pages > 0 && <button className="sm" onClick={() => run(async () => setView({ d, pages: await api.get(`/documents/${d.id}/pages`) }))}>{L("النص", "Text")}</button>}
                  {d.supersedes_id && <button className="sm ai-btn" onClick={() => run(async () => setDiff(await api.get(`/documents/${d.id}/compare/${d.supersedes_id}`)))}>{L("مقارنة بالأصل", "Compare to original")}</button>}
                </td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
      {diff && (
        <Modal wide title={`${L("التغييرات", "Changes")}: ${diff.revised.title} ← ${diff.original.title}`} onClose={() => setDiff(null)}>
          {!diff.changes.length ? <Empty>{L("لا اختلافات في النص", "No text differences")}</Empty> : (
            <table><thead><tr><th>{L("نوع التغيير", "Change")}</th><th>{L("الأصل", "Original")}</th><th>{L("الملحق", "Revised")}</th></tr></thead>
              <tbody>{diff.changes.map((c: any, i: number) => (
                <tr key={i}><td><Badge tone={c.change === "added" ? "ok" : c.change === "removed" ? "err" : "warn"}>{c.change}</Badge></td>
                  <td className="desc" style={{ background: "#fef2f2" }}>{c.old.join("\n")}</td><td className="desc" style={{ background: "#f0fdf4" }}>{c.new.join("\n")}</td></tr>))}</tbody></table>
          )}
        </Modal>
      )}
      {view && (
        <Modal wide title={view.d.title} onClose={() => setView(null)}>
          {view.pages.map((p: any) => <div key={p.page} style={{ marginBottom: 12 }}><Badge>{L("صفحة", "Page")} {p.page}</Badge><pre className="letter">{p.text}</pre></div>)}
        </Modal>
      )}
    </div>
  );
}
