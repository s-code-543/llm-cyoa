import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { getDashboard } from "../../api/admin";
import { AuditTable } from "./AuditPage";

export function AdminHome() {
  const dashboard = useQuery({ queryKey: ["admin", "dashboard"], queryFn: getDashboard });
  return (
    <>
      <h1>Dashboard</h1>
      {dashboard.isPending && <p className="empty" role="status">Loading…</p>}
      {dashboard.error && <p className="empty" role="alert">{dashboard.error.message}</p>}
      {dashboard.data && (
        <>
          <ul className="cards stats">
            <li className="card"><strong>{dashboard.data.total_requests}</strong><span>Requests</span></li>
            <li className="card"><strong>{dashboard.data.total_refusals}</strong><span>Refusals</span></li>
            <li className="card"><strong>{dashboard.data.total_corrections}</strong><span>Corrections</span></li>
            <li className="card"><strong>{dashboard.data.correction_rate}%</strong><span>Correction rate</span></li>
          </ul>
          <h2>Recent activity</h2>
          <AuditTable logs={dashboard.data.recent} />
          <p><Link to="/manage/audit">View full audit log →</Link></p>
        </>
      )}
    </>
  );
}
