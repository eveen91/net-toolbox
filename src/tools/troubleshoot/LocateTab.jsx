import React, { useState } from "react";
import {
  locateDevice,
  portHealth,
  runCableTest,
  checkTransceiverHealth,
  checkAccessStatus,
} from "./api.js";

export default function LocateTab({ locateForm, setLocateForm }) {
  const [locateResult, setLocateResult] = useState(null);
  const [portHealthResult, setPortHealthResult] = useState(null);
  const [cableTestConfirmed, setCableTestConfirmed] = useState(false);
  const [cableTestResult, setCableTestResult] = useState(null);
  const [transceiverResult, setTransceiverResult] = useState(null);
  const [accessResult, setAccessResult] = useState(null);

  const handleLocate = async () => {
    const result = await locateDevice(locateForm.ip, locateForm.username, locateForm.password);
    setLocateResult(result);
  };

  const handlePortHealth = async () => {
    const result = await portHealth(
      locateResult.device,
      locateResult.port,
      locateForm.username,
      locateForm.password,
    );
    setPortHealthResult(result);
  };

  const handleCableTest = async () => {
    const result = await runCableTest(
      locateResult.device,
      locateResult.port,
      locateForm.username,
      locateForm.password,
      cableTestConfirmed,
    );
    setCableTestResult(result);
  };

  const handleTransceiverHealth = async () => {
    const result = await checkTransceiverHealth(
      locateResult.device,
      locateResult.port,
      locateForm.username,
      locateForm.password,
    );
    setTransceiverResult(result);
  };

  const handleAccessCheck = async () => {
    const result = await checkAccessStatus(
      locateResult.device,
      locateResult.port,
      locateForm.username,
      locateForm.password,
    );
    setAccessResult(result);
  };

  const locatedDevice = locateResult?.success ? locateResult.device : "-";
  const locatedPort = locateResult?.success ? locateResult.port : "-";
  const canUseLocated = !locateResult || !locateResult.success;

  return (
    <div>
      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Locate device</h3>
        <div className="tool-field">
          <div className="tool-label">IP address</div>
          <input
            className="tool-input"
            value={locateForm.ip}
            onChange={(e) => setLocateForm({ ...locateForm, ip: e.target.value })}
          />
        </div>
        <div className="tool-field">
          <div className="tool-label">Username</div>
          <input
            className="tool-input"
            value={locateForm.username}
            onChange={(e) => setLocateForm({ ...locateForm, username: e.target.value })}
          />
        </div>
        <div className="tool-field">
          <div className="tool-label">Password</div>
          <input
            className="tool-input"
            type="password"
            value={locateForm.password}
            onChange={(e) => setLocateForm({ ...locateForm, password: e.target.value })}
          />
        </div>
        <div className="tool-actions">
          <button className="tool-btn" onClick={handleLocate}>
            Locate
          </button>
        </div>
        {locateResult && (
          <div style={{ marginTop: 12 }}>
            {locateResult.success ? (
              <div className="tool-panel">
                <div><strong>MAC:</strong> {locateResult.mac}</div>
                <div><strong>Device:</strong> {locateResult.device}</div>
                <div><strong>Port:</strong> {locateResult.port}</div>
                <div><strong>VLAN:</strong> {locateResult.vlan}</div>
              </div>
            ) : (
              <div className="tool-error">{locateResult.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Port health</h3>
        <div className="tool-field">
          <div className="tool-label">Device</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedDevice}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedPort}
          </div>
        </div>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handlePortHealth}
            disabled={canUseLocated}
          >
            Check port health
          </button>
        </div>
        {portHealthResult && (
          <div style={{ marginTop: 12 }}>
            {portHealthResult.success ? (
              <div className="tool-panel">
                {(() => {
                  const healthy =
                    portHealthResult.adminStatus === "up" &&
                    portHealthResult.operStatus === "up" &&
                    (portHealthResult.inputErrors === 0 || portHealthResult.inputErrors === null) &&
                    (portHealthResult.outputErrors === 0 || portHealthResult.outputErrors === null) &&
                    (portHealthResult.crcErrors === 0 || portHealthResult.crcErrors === null);
                  const pills = [
                    { label: "Admin", value: portHealthResult.adminStatus },
                    { label: "Oper", value: portHealthResult.operStatus },
                    { label: "Speed", value: portHealthResult.speed },
                    { label: "Duplex", value: portHealthResult.duplex },
                    { label: "RX err", value: portHealthResult.inputErrors },
                    { label: "TX err", value: portHealthResult.outputErrors },
                    { label: "CRC", value: portHealthResult.crcErrors },
                  ];
                  return pills.map((p) => (
                    <span
                      key={p.label}
                      className={healthy ? "tool-pill-ok" : "tool-pill-warn"}
                      style={{ marginRight: 6, marginBottom: 4, display: "inline-block" }}
                    >
                      {p.label}: {p.value ?? "-"}
                    </span>
                  ));
                })()}
              </div>
            ) : (
              <div className="tool-error">{portHealthResult.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Cable diagnostics</h3>
        <p className="tool-hint">
          This can briefly interrupt link. Only run it if you're prepared for that.
        </p>
        <div className="tool-field">
          <div className="tool-label">Device</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedDevice}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedPort}
          </div>
        </div>
        <label className="tool-field" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="checkbox"
            checked={cableTestConfirmed}
            onChange={(e) => setCableTestConfirmed(e.target.checked)}
          />
          I understand this may briefly interrupt link
        </label>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handleCableTest}
            disabled={canUseLocated || !cableTestConfirmed}
          >
            Run cable test
          </button>
        </div>
        {cableTestResult && (
          <div style={{ marginTop: 12 }}>
            {cableTestResult.success ? (
              <div className="tool-table-wrap">
                <table className="tool-table">
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th>Length (m)</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cableTestResult.pairs.map((p) => (
                      <tr key={p.pair}>
                        <td>{p.pair}</td>
                        <td>{p.lengthMeters}</td>
                        <td>
                          <span
                            className={
                              p.status === "Normal" || p.status === "OK"
                                ? "tool-pill-ok"
                                : "tool-pill-warn"
                            }
                          >
                            {p.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="tool-error">{cableTestResult.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Optics health</h3>
        <div className="tool-field">
          <div className="tool-label">Device</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedDevice}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedPort}
          </div>
        </div>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handleTransceiverHealth}
            disabled={canUseLocated}
          >
            Check optics
          </button>
        </div>
        {transceiverResult && (
          <div style={{ marginTop: 12 }}>
            {transceiverResult.success ? (
              <div className="tool-table-wrap">
                <table className="tool-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Value</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { key: "temperature", label: "Temperature", unit: "C" },
                      { key: "voltage", label: "Voltage", unit: "V" },
                      { key: "biasCurrent", label: "Bias Current", unit: "mA" },
                      { key: "txPower", label: "Tx Power", unit: "dBm" },
                      { key: "rxPower", label: "Rx Power", unit: "dBm" },
                    ].map(({ key, label, unit }) => {
                      const metric = transceiverResult.metrics[key];
                      const value =
                        metric?.value !== null && metric?.value !== undefined
                          ? `${metric.value} ${unit}`
                          : "-";
                      const status = metric?.status ?? "unknown";
                      const statusClass =
                        status === "ok"
                          ? "tool-pill-ok"
                          : status === "alarm"
                          ? "tool-pill-warn"
                          : "tool-pill-warn";
                      return (
                        <tr key={key}>
                          <td>{label}</td>
                          <td>{value}</td>
                          <td>
                            <span className={statusClass}>{status}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="tool-error">{transceiverResult.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="tool-panel">
        <h3>Port access status</h3>
        <div className="tool-field">
          <div className="tool-label">Device</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedDevice}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locatedPort}
          </div>
        </div>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handleAccessCheck}
            disabled={canUseLocated}
          >
            Check access status
          </button>
        </div>
        {accessResult && (
          <div style={{ marginTop: 12 }}>
            {accessResult.success ? (
              <div className="tool-panel">
                <div>Enabled: {accessResult.enabled ? "Yes" : "No"}</div>
                <div>
                  Status:{" "}
                  <span
                    className={
                      accessResult.status &&
                      (accessResult.status.toLowerCase().includes("authenticated") ||
                        accessResult.status.toLowerCase().includes("secure-up"))
                        ? "tool-pill-ok"
                        : "tool-pill-warn"
                    }
                  >
                    {accessResult.status}
                  </span>
                </div>
              </div>
            ) : (
              <div className="tool-error">{accessResult.error}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
