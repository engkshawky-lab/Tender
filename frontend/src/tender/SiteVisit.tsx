import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Card, Field, FileButton, useAction, useCan, useLoad } from "../ui";
import { useTender } from "./TenderPage";

export default function SiteVisit() {
  const { tender, estimateId } = useTender();
  const { L, lang } = useI18n();
  const can = useCan();
  const { run, busy } = useAction();
  const [sv, reload] = useLoad<any>(`/tenders/${tender.id}/site-visit`);
  const [f, setF] = useState<any>(null);
  const [sugg, setSugg] = useState<any[]>([]);
  useEffect(() => { if (sv) setF(sv); }, [sv]);
  if (!f) return null;
  const dis = !can("analysis.manage");
  const setItem = (i: number, k: string, v: string) => setF({ ...f, checklist: f.checklist.map((c: any, j: number) => (j === i ? { ...c, [k]: v } : c)) });
  const save = () => run(async () => { const r = await api.put(`/tenders/${tender.id}/site-visit`, f); setSugg(r.suggestions); reload(); }, L("تم حفظ التقرير", "Report saved"));
  const photo = (file: File) => {
    const go = (lat?: number, lng?: number) => run(async () => { await api.upload(`/tenders/${tender.id}/site-visit/photos`, file, { caption: file.name, lat, lng }); reload(); }, L("تم رفع الصورة", "Photo uploaded"));
    if (navigator.geolocation) navigator.geolocation.getCurrentPosition((p) => go(p.coords.latitude, p.coords.longitude), () => go(), { timeout: 4000 });
    else go();
  };
  const toRisk = (s: any) => run(() => api.post(`/tenders/${tender.id}/risks`, { description: s.description, category: "site", probability_pct: s.probability_pct, origin: "site_visit" }), L("أضيفت لسجل المخاطر", "Added to risk register"));
  const toIndirect = (s: any) => run(() => api.post(`/estimates/${estimateId}/indirects`, { description: s.description, kind: "fixed", category: "site", origin: "site_visit" }), L("أضيف بند غير مباشر", "Indirect item added"));
  return (
    <div className="stack">
      <Card title={L("6) زيارة الموقع — قائمة فحص حسب نوع المشروع", "6) Site visit — checklist by project type")} actions={!dis && <button className="primary" disabled={busy} onClick={save}>{L("حفظ", "Save")}</button>}>
        <div className="form">
          <Field label={L("تاريخ الزيارة", "Visit date")}><input type="date" value={f.visit_date || ""} disabled={dis} onChange={(e) => setF({ ...f, visit_date: e.target.value })} /></Field>
          <Field label={L("الحضور", "Attendees")}><input value={f.attendees || ""} disabled={dis} onChange={(e) => setF({ ...f, attendees: e.target.value })} /></Field>
        </div>
        <div className="tbl-wrap" style={{ marginTop: 12 }}><table>
          <thead><tr><th>{L("البند", "Item")}</th><th>{L("الحالة", "Status")}</th><th>{L("الملاحظات", "Notes")}</th></tr></thead>
          <tbody>{f.checklist.map((c: any, i: number) => (
            <tr key={c.key}>
              <td>{lang === "ar" ? c.label : c.label_en || c.label}</td>
              <td><div className="row gap">{[["ok", "✓"], ["issue", "!"], ["na", "—"]].map(([k, s]) => (
                <button key={k} disabled={dis} className={`sm ${c.status === k ? (k === "issue" ? "danger primary" : "primary") : ""}`} onClick={() => setItem(i, "status", k)}>{s}</button>))}</div></td>
              <td style={{ width: "55%" }}><input style={{ width: "100%" }} disabled={dis} value={c.notes || ""} onChange={(e) => setItem(i, "notes", e.target.value)} /></td>
            </tr>))}</tbody>
        </table></div>
        <Field label={L("ملخص التقرير", "Report summary")} wide><textarea disabled={dis} value={f.summary || ""} onChange={(e) => setF({ ...f, summary: e.target.value })} /></Field>
        <div className="row gap wrap" style={{ marginTop: 10 }}>
          {!dis && <FileButton label={`📷 ${L("إضافة صورة (مع الموقع الجغرافي)", "Add photo (with location)")}`} accept="image/*" onFile={photo} />}
          <span className="muted small">{(f.photos || []).length} {L("صورة", "photos")}</span>
          {(f.photos || []).map((p: any) => <button key={p.document_id} className="sm ghost" onClick={() => api.download(`/documents/${p.document_id}/file`)}>🖼 {p.caption}{p.lat ? ` (${p.lat.toFixed(4)}, ${p.lng.toFixed(4)})` : ""}</button>)}
        </div>
      </Card>
      {sugg.length > 0 && (
        <Card title={L("بنود مقترحة من ملاحظات الزيارة", "Suggested items from the visit")}>
          <table><tbody>{sugg.map((s, i) => (
            <tr key={i} className="ai-row"><td>{s.type === "risk" ? L("مخاطرة", "Risk") : L("مصروف غير مباشر", "Indirect cost")}</td><td>{s.description}</td>
              <td>{s.type === "risk" ? <button className="sm" onClick={() => toRisk(s)}>{L("إضافة لسجل المخاطر", "Add to risks")}</button>
                : <button className="sm" disabled={!estimateId} onClick={() => toIndirect(s)}>{L("إضافة لغير المباشر", "Add to indirects")}</button>}</td></tr>))}</tbody></table>
        </Card>
      )}
    </div>
  );
}
