import React, { useState } from "react";
import { runFullDiagnostic } from "./api.js";

export default function DiagnosticsTab() {
  const [runForm, setRunForm] = useState({ ip: "", username: "", password: "" });
  const [runInProgress, setRunInProgress] = useState(false);
  const [runResult, setRunResult] = useState(null);

  const handleFullRun = async () => {
    setRunInProgress(true);
    setRunResult(null);
    try {
      const result = await runFullDiagnostic(runForm.ip, runForm.username, runForm.password);
      setRunResult(result);
    } finally {
      setRunInProgress(false);
    }
  };

  return (
    <div className="tool-panel">
      <div className="tool-field">
        <div className="tool-label">IP address</div>
        <input
          className="tool-input"
          value={runForm.ip}
          onChange={(e) => setRunForm({ ...runForm, ip: e.target.value })}
        />
      </div>
      <div className="tool-field">
        <div className="tool-label">Username</div>
        <input
          className="tool-input"
          value={runForm.username}
          onChange={(e) => setRunForm({ ...runForm, username: e.target.value })}
        />
      </div>
      <div className="tool-field">
        <div className="tool-label">Password</div>
        <input
          className="tool-input"
          type="password"
          value={runForm.password}
          onChange={(e) => setRunForm({ ...runForm, password: e.target.value })}
        />
      </div>
      <div className="tool-actions">
        <button className="tool-btn" onClick={handleFullRun} disabled={runInProgress}>
          {runInProgress ? "Running — this can take 20-30 seconds." : "Run diagnostic"}
        </button>
      </div>
      {runResult && (
        <div style={{ marginTop: 12 }}>
          {[
            { key: "locate", title: "Locate" },
            { key: "portHealth", title: "Port Health" },
            { key: "transceiverHealth", title: "Transceiver Health" },
            { key: "accessStatus", title: "Access Status" },
            { key: "ping", title: "Ping" },
            { key: "route", title: "Route" },
          ].map(({ key, title }) => {
            const step = runResult[key];
            if (!step) return null;
            return (
              <div className="tool-panel" key={key}>
                <strong>{title}</strong>
                <div style={{ marginTop: 4 }}>
                  {step.success ? (
                    key === "locate" ? (
                      <span>
                        Device: {step.device} · Port: {step.port} · VLAN: {step.vlan}
                      </span>
                    ) : key === "ping" ? (
                      <span>Packet loss: {step.packetLossPercent}%</span>
                    ) : key === "route" ? (
                      <span>Next hop: {step.nextHop ?? "Not found"}</span>
                    ) : key === "portHealth" ? (
                      <span>
                        {step.adminStatus}/{step.operStatus} · {step.speed} · RX {step.inputErrors} · TX {step.outputErrors}
                      </span>
                    ) : key === "transceiverHealth" ? (
                      <span>Temperature {step.temperature?.status ?? "unknown"}</span>
                    ) : key === "accessStatus" ? (
                      <span>Status: {step.status}</span>
                    ) : null
                  ) : (
                    <span className="tool-pill-warn">{step.error}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
