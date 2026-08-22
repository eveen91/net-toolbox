import React, { useState, useEffect } from "react";
import { getAuditLog } from "./api.js";

export default function ActivityTab() {
  const [auditLog, setAuditLog] = useState([]);

  const refreshAuditLog = async () => {
    const data = await getAuditLog();
    setAuditLog(data);
  };

  useEffect(() => {
    refreshAuditLog();
  }, []);

  return (
    <div className="tool-panel">
      <div className="tool-section-title">
        <h3>Recent activity</h3>
        <button className="tool-btn tool-btn-ghost" onClick={refreshAuditLog}>
          Refresh
        </button>
      </div>
      <div className="tool-table-wrap">
        <table className="tool-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Device</th>
              <th>Command</th>
              <th>User</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {auditLog.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.createdAt}</td>
                <td>{entry.deviceName ?? "unknown"}</td>
                <td>{entry.command}</td>
                <td>{entry.username}</td>
                <td>
                  <span className={entry.success ? "tool-pill-ok" : "tool-pill-warn"}>
                    {entry.success ? "OK" : "Failed"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
