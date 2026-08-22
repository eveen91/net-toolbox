import React, { useState } from "react";
import { getStpReport } from "./api.js";

export default function StpReportTab() {
  const [stpForm, setStpForm] = useState({ username: "", password: "" });
  const [stpResult, setStpResult] = useState(null);

  const handleStpReport = async () => {
    const result = await getStpReport(stpForm.username, stpForm.password);
    setStpResult(result);
  };

  return (
    <div className="tool-panel">
      <p className="tool-hint">
        Scans every switch in inventory for ports with frequent recent topology changes.
      </p>
      <div className="tool-field">
        <div className="tool-label">Username</div>
        <input
          className="tool-input"
          value={stpForm.username}
          onChange={(e) => setStpForm({ ...stpForm, username: e.target.value })}
        />
      </div>
      <div className="tool-field">
        <div className="tool-label">Password</div>
        <input
          className="tool-input"
          type="password"
          value={stpForm.password}
          onChange={(e) => setStpForm({ ...stpForm, password: e.target.value })}
        />
      </div>
      <div className="tool-actions">
        <button className="tool-btn" onClick={handleStpReport}>
          Run STP report
        </button>
      </div>
      {stpResult && (
        <div style={{ marginTop: 12 }}>
          {stpResult.success ? (
            <div className="tool-table-wrap">
              <table className="tool-table">
                <thead>
                  <tr>
                    <th>Device</th>
                    <th>Port</th>
                    <th>Topology Changes</th>
                    <th>Last Change</th>
                  </tr>
                </thead>
                <tbody>
                  {stpResult.entries.map((entry, i) => (
                    <tr key={i}>
                      <td>{entry.device}</td>
                      <td>{entry.port}</td>
                      <td>
                        <span
                          className={
                            entry.topologyChanges > 5 && entry.lastChangeSeconds < 3600
                              ? "tool-pill-warn"
                              : ""
                          }
                        >
                          {entry.topologyChanges}
                        </span>
                      </td>
                      <td>{entry.lastChangeAgo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="tool-error">{stpResult.error}</div>
          )}
        </div>
      )}
    </div>
  );
}
