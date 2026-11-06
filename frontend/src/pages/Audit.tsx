import { useState } from "react";
import { useI18n } from "../i18n";
import { Card, Empty, useFmt, useLoad } from "../ui";

export default function Audit() {
  const { L } = useI18n();
  const fmt = useFmt();
  const [entity, setEntity] = useState("");
  const [rows] = useLoad<any[]>(`/audit?limit=500${entity ? `&entity=${entity}` : ""}`);
  const entities = ["", "tenders", "estimates", "buildup_lines", "indirect_items", "boq_items", "quotations", "risks", "rfis", "settings", "users"];
  return (
    <div>
      <div className="page-h"><div><h1>{L("سجل التعديلات", "Audit log")}</h1><div className="sub">{L("من غيّر أي رقم ومتى", "Who changed which number, and when")}</div></div>
        <select value={entity} onChange={(e) => setEntity(e.target.value)}>{entities.map((e) => <option key={e} value={e}>{e || L("الكل", "All")}</option>)}</select></div>
      <Card>
        {!rows?.length ? <Empty>—</Empty> : (
          <div className="tbl-wrap" style={{ maxHeight: "75vh" }}><table>
            <thead><tr><th>{L("الوقت", "Time")}</th><th>{L("المستخدم", "User")}</th><th>{L("العملية", "Action")}</th><th>{L("الكيان", "Entity")}</th><th>{L("التغييرات", "Changes")}</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}><td className="small">{fmt.d(r.at)} {r.at.slice(11, 16)}</td><td>{r.user}</td><td>{r.action}</td><td>{r.entity} #{r.entity_id}{r.tender_id ? ` · T${r.tender_id}` : ""}</td>
                <td className="small" style={{ maxWidth: 520 }}>{r.action === "update"
                  ? Object.entries(r.changes).map(([k, v]: any) => <div key={k}><b>{k}</b>: {JSON.stringify(v[0])?.slice(0, 60)} → {JSON.stringify(v[1])?.slice(0, 60)}</div>)
                  : r.action === "create" ? <span className="muted">{Object.entries(r.changes).filter(([, v]) => v !== null && v !== "" && v !== false).slice(0, 5).map(([k, v]) => `${k}=${String(v).slice(0, 30)}`).join(" · ")}</span> : ""}</td></tr>))}</tbody>
          </table></div>
        )}
      </Card>
    </div>
  );
}
