import React, { useState, useEffect } from "react";
import {
  listDevices,
  addDevice,
  deleteDevice,
  locateDevice,
  portHealth,
  runCableTest,
  checkTransceiverHealth,
  getStpReport,
  checkAccessStatus,
  pingHost,
  checkRoute,
  runFullDiagnostic,
  getAuditLog,
} from "./api.js";

export default function Troubleshoot() {
  const [devices, setDevices] = useState([]);
  const [locateForm, setLocateForm] = useState({ ip: "", username: "", password: "" });
  const [locateResult, setLocateResult] = useState(null);
  const [portHealthResult, setPortHealthResult] = useState(null);
  const [cableTestConfirmed, setCableTestConfirmed] = useState(false);
  const [cableTestResult, setCableTestResult] = useState(null);
  const [transceiverResult, setTransceiverResult] = useState(null);
  const [stpForm, setStpForm] = useState({ username: "", password: "" });
  const [stpResult, setStpResult] = useState(null);
  const [accessResult, setAccessResult] = useState(null);
  const [pingIp, setPingIp] = useState("");
  const [pingResult, setPingResult] = useState(null);
  const [routeResult, setRouteResult] = useState(null);
  const [runForm, setRunForm] = useState({ ip: "", username: "", password: "" });
  const [runInProgress, setRunInProgress] = useState(false);
  const [runResult, setRunResult] = useState(null);
  const [auditLog, setAuditLog] = useState([]);
  const [formValues, setFormValues] = useState({
    name: "",
    mgmtIp: "",
    vendor: "",
    model: "",
    osVersion: "",
    deviceType: "",
  });

  const fetchDevices = async () => {
    const data = await listDevices();
    setDevices(data);
  };

  const refreshAuditLog = async () => {
    const data = await getAuditLog();
    setAuditLog(data);
  };

  useEffect(() => {
    fetchDevices();
    refreshAuditLog();
  }, []);

  const handleChange = (e) => {
    setFormValues({ ...formValues, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await addDevice(formValues);
    await fetchDevices();
    setFormValues({
      name: "",
      mgmtIp: "",
      vendor: "",
      model: "",
      osVersion: "",
      deviceType: "",
    });
  };

  const handleDelete = async (id) => {
    await deleteDevice(id);
    await fetchDevices();
  };

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

  const handleStpReport = async () => {
    const result = await getStpReport(stpForm.username, stpForm.password);
    setStpResult(result);
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

  const handlePing = async () => {
    const result = await pingHost(pingIp);
    setPingResult(result);
  };

  const handleRouteCheck = async () => {
    const result = await checkRoute(pingIp, locateForm.username, locateForm.password);
    setRouteResult(result);
  };

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
    <div>
      <div className="nt-tool-header">
        <h2>Troubleshoot</h2>
        <p>Look up a device on the network and check its health.</p>
      </div>

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Run full diagnostic</h3>
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
            {locateResult?.success ? locateResult.device : "-"}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locateResult?.success ? locateResult.port : "-"}
          </div>
        </div>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handlePortHealth}
            disabled={!locateResult || !locateResult.success}
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
            {locateResult?.success ? locateResult.device : "-"}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locateResult?.success ? locateResult.port : "-"}
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
            disabled={!locateResult || !locateResult.success || !cableTestConfirmed}
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
            {locateResult?.success ? locateResult.device : "-"}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locateResult?.success ? locateResult.port : "-"}
          </div>
        </div>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handleTransceiverHealth}
            disabled={!locateResult || !locateResult.success}
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

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Spanning-tree flap report</h3>
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

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Port access status</h3>
        <div className="tool-field">
          <div className="tool-label">Device</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locateResult?.success ? locateResult.device : "-"}
          </div>
        </div>
        <div className="tool-field">
          <div className="tool-label">Port</div>
          <div className="tool-input" style={{ background: "var(--bg-muted)", cursor: "default" }}>
            {locateResult?.success ? locateResult.port : "-"}
          </div>
        </div>
        <div className="tool-actions">
          <button
            className="tool-btn"
            onClick={handleAccessCheck}
            disabled={!locateResult || !locateResult.success}
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

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Reachability</h3>
        <div className="tool-field">
          <div className="tool-label">IP address</div>
          <input
            className="tool-input"
            value={pingIp}
            onChange={(e) => setPingIp(e.target.value)}
          />
        </div>
        <div className="tool-actions">
          <button className="tool-btn" onClick={handlePing}>
            Ping
          </button>
        </div>
        {pingResult && (
          <div style={{ marginTop: 12 }}>
            {pingResult.success ? (
              <div className="tool-panel">
                <div>Packets Sent: {pingResult.packetsSent}</div>
                <div>Packets Received: {pingResult.packetsReceived}</div>
                <div>
                  Packet Loss:{" "}
                  <span
                    className={
                      pingResult.packetLossPercent === 0
                        ? "tool-pill-ok"
                        : "tool-pill-warn"
                    }
                  >
                    {pingResult.packetLossPercent}%
                  </span>
                </div>
                <div>Avg Latency: {pingResult.avgLatencyMs} ms</div>
              </div>
            ) : (
              <div className="tool-error">{pingResult.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="tool-panel" style={{ marginBottom: 16 }}>
        <h3>Route check</h3>
        <div className="tool-actions">
          <button className="tool-btn" onClick={handleRouteCheck}>
            Check route
          </button>
        </div>
        {routeResult && (
          <div style={{ marginTop: 12 }}>
            {routeResult.success ? (
              <div className="tool-panel">
                <div>Next Hop: {routeResult.nextHop ?? "Not found"}</div>
                <div>Interface: {routeResult.interface ?? "Not found"}</div>
              </div>
            ) : (
              <div className="tool-error">{routeResult.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <form onSubmit={handleSubmit}>
            <div className="tool-field">
              <div className="tool-label">Name</div>
              <input
                className="tool-input"
                name="name"
                value={formValues.name}
                onChange={handleChange}
              />
            </div>
            <div className="tool-field">
              <div className="tool-label">Management IP</div>
              <input
                className="tool-input"
                name="mgmtIp"
                value={formValues.mgmtIp}
                onChange={handleChange}
              />
            </div>
            <div className="tool-field">
              <div className="tool-label">Vendor</div>
              <input
                className="tool-input"
                name="vendor"
                value={formValues.vendor}
                onChange={handleChange}
              />
            </div>
            <div className="tool-field">
              <div className="tool-label">Model</div>
              <input
                className="tool-input"
                name="model"
                value={formValues.model}
                onChange={handleChange}
              />
            </div>
            <div className="tool-field">
              <div className="tool-label">OS Version</div>
              <input
                className="tool-input"
                name="osVersion"
                value={formValues.osVersion}
                onChange={handleChange}
              />
            </div>
            <div className="tool-field">
              <div className="tool-label">Device Type</div>
              <input
                className="tool-input"
                name="deviceType"
                value={formValues.deviceType}
                onChange={handleChange}
              />
            </div>
            <div className="tool-actions">
              <button className="tool-btn" type="submit">
                Add Device
              </button>
            </div>
          </form>
        </div>

        <div className="tool-panel">
          <div className="tool-table-wrap">
            <table className="tool-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Management IP</th>
                  <th>Vendor</th>
                  <th>Model</th>
                  <th>Device Type</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {devices.map((device) => (
                  <tr key={device.id}>
                    <td>{device.name}</td>
                    <td>{device.mgmtIp}</td>
                    <td>{device.vendor}</td>
                    <td>{device.model}</td>
                    <td>{device.deviceType}</td>
                    <td>
                      <button
                        className="tool-btn"
                        onClick={() => handleDelete(device.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="tool-panel" style={{ marginTop: 16 }}>
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
    </div>
  );
}
