import React, { useMemo, useState } from "react";
import "./connection-test.css";
import { parseSources, parseLines, parsePorts, rowsToCsv, downloadCsv } from "./logic.js";
import { runConnectionTest } from "./api.js";

const EXAMPLE = {
  sources: "web01,linux\napp02,linux\nwinapp01,windows\nwinsql01,windows",
  destinations: "10.0.1.10\n10.0.1.20\ndb-prod.internal",
  ports: "443\n1433\n22",
};

function statusPillClass(status) {
  const s = (status || "").toUpperCase();
  if (s === "OPEN") return "tool-pill tool-pill-ok";
  if (s.startsWith("FAILED") || s.startsWith("UNREACHABLE") || s.startsWith("NO_OUTPUT")) return "tool-pill tool-pill-no";
  return "tool-pill tool-pill-warn"; // TIMEOUT, missing-credentials, etc.
}

export default function ConnectionTest() {
  const [sources, setSources] = useState(EXAMPLE.sources);
  const [destinations, setDestinations] = useState(EXAMPLE.destinations);
  const [ports, setPorts] = useState(EXAMPLE.ports);

  const [linuxUser, setLinuxUser] = useState("");
  const [linuxPass, setLinuxPass] = useState("");
  const [winUser, setWinUser] = useState("");
  const [winPass, setWinPass] = useState("");

  const [connectTimeout, setConnectTimeout] = useState(5);
  const [sshPort, setSshPort] = useState(22);
  const [winrmPort, setWinrmPort] = useState(5985);
  const [winrmScheme, setWinrmScheme] = useState("http");
  const [winrmTransport, setWinrmTransport] = useState("ntlm");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const run = async () => {
    setError(null);
    setResult(null);
    try {
      const parsedSources = parseSources(sources);
      if (parsedSources.length === 0) throw new Error("Enter at least one source (hostname,linux or hostname,windows).");
      const parsedDestinations = parseLines(destinations);
      if (parsedDestinations.length === 0) throw new Error("Enter at least one destination host.");
      const parsedPorts = parsePorts(ports);
      if (parsedPorts.length === 0) throw new Error("Enter at least one port.");

      const hasLinux = parsedSources.some((s) => s.os === "linux");
      const hasWindows = parsedSources.some((s) => s.os === "windows");
      if (hasLinux && (!linuxUser || !linuxPass)) throw new Error("Enter Linux SSH credentials — you have Linux sources.");
      if (hasWindows && (!winUser || !winPass)) throw new Error("Enter Windows credentials — you have Windows sources.");

      setLoading(true);
      const payload = {
        sources: parsedSources,
        destinations: parsedDestinations,
        ports: parsedPorts,
        linux_credentials: hasLinux ? { username: linuxUser, password: linuxPass } : null,
        windows_credentials: hasWindows ? { username: winUser, password: winPass } : null,
        connect_timeout_seconds: connectTimeout,
        ssh_port: sshPort,
        winrm_port: winrmPort,
        winrm_transport: winrmTransport,
        winrm_scheme: winrmScheme,
      };
      const data = await runConnectionTest(payload);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const stats = useMemo(() => {
    if (!result) return null;
    const rows = result.rows;
    const open = rows.filter((r) => r.status === "OPEN").length;
    const bad = rows.filter((r) => statusPillClass(r.status).includes("tool-pill-no")).length;
    const other = rows.length - open - bad;
    return { total: rows.length, open, bad, other };
  }, [result]);

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Connection test</h2>
        <p>SSH into Linux sources and WinRM into Windows sources, then check TCP connectivity to each destination:port.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">
              <span>Sources <span className="tool-hint">one per line: host,linux or host,windows</span></span>
            </div>
            <textarea className="tool-textarea" value={sources} onChange={(e) => setSources(e.target.value)} />
          </div>

          <div className="tool-field">
            <div className="tool-label"><span>Destinations <span className="tool-hint">one per line</span></span></div>
            <textarea className="tool-textarea" style={{ minHeight: 64 }} value={destinations} onChange={(e) => setDestinations(e.target.value)} />
          </div>

          <div className="tool-field">
            <div className="tool-label"><span>Ports <span className="tool-hint">one per line</span></span></div>
            <textarea className="tool-textarea" style={{ minHeight: 56 }} value={ports} onChange={(e) => setPorts(e.target.value)} />
          </div>

          <hr className="ct-divider" />

          <div className="ct-section-label">Linux SSH credentials</div>
          <div className="ct-cred-grid" style={{ marginBottom: 16 }}>
            <input className="tool-input" placeholder="username" value={linuxUser} onChange={(e) => setLinuxUser(e.target.value)} />
            <input className="tool-input" placeholder="password" type="password" value={linuxPass} onChange={(e) => setLinuxPass(e.target.value)} />
          </div>

          <div className="ct-section-label">Windows / WinRM credentials</div>
          <div className="ct-cred-grid">
            <input className="tool-input" placeholder="username" value={winUser} onChange={(e) => setWinUser(e.target.value)} />
            <input className="tool-input" placeholder="password" type="password" value={winPass} onChange={(e) => setWinPass(e.target.value)} />
          </div>
          <div className="tool-hint" style={{ marginTop: 6 }}>
            Sent directly to the backend for this run only — not stored.
          </div>

          <details className="ct-advanced" style={{ marginTop: 16 }}>
            <summary>Advanced settings</summary>
            <div className="ct-advanced-grid">
              <div className="tool-field">
                <div className="tool-label">Connect timeout (s)</div>
                <input className="tool-input" type="number" min={1} max={60} value={connectTimeout} onChange={(e) => setConnectTimeout(Number(e.target.value))} />
              </div>
              <div className="tool-field">
                <div className="tool-label">SSH port</div>
                <input className="tool-input" type="number" value={sshPort} onChange={(e) => setSshPort(Number(e.target.value))} />
              </div>
              <div className="tool-field">
                <div className="tool-label">WinRM port</div>
                <input className="tool-input" type="number" value={winrmPort} onChange={(e) => setWinrmPort(Number(e.target.value))} />
              </div>
              <div className="tool-field">
                <div className="tool-label">WinRM scheme</div>
                <select className="tool-input" value={winrmScheme} onChange={(e) => setWinrmScheme(e.target.value)}>
                  <option value="http">http (5985)</option>
                  <option value="https">https (5986)</option>
                </select>
              </div>
              <div className="tool-field" style={{ gridColumn: "1 / -1" }}>
                <div className="tool-label">WinRM auth transport</div>
                <select className="tool-input" value={winrmTransport} onChange={(e) => setWinrmTransport(e.target.value)}>
                  <option value="ntlm">NTLM (local accounts, non-domain)</option>
                  <option value="kerberos">Kerberos (domain-joined)</option>
                  <option value="basic">Basic (must be enabled on target)</option>
                  <option value="credssp">CredSSP</option>
                </select>
              </div>
            </div>
          </details>

          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" onClick={run} disabled={loading}>
              {loading ? "Running…" : "Run test"}
            </button>
            <button
              className="tool-btn tool-btn-ghost"
              onClick={() => {
                setSources(EXAMPLE.sources);
                setDestinations(EXAMPLE.destinations);
                setPorts(EXAMPLE.ports);
                setError(null);
              }}
            >
              Load example
            </button>
          </div>

          {error && <div className="tool-error">{error}</div>}
        </div>

        <div className="tool-panel">
          {!result && !loading && !error && (
            <div className="tool-empty">Fill in sources, destinations, and ports, then hit Run test.</div>
          )}
          {loading && <div className="ct-loading">Connecting to sources and testing ports…</div>}

          {result && !loading && (
            <>
              <div className="tool-summary">
                <div className="tool-stat"><div className="n">{stats.total}</div><div className="l">Tests run</div></div>
                <div className="tool-stat"><div className="n">{stats.open}</div><div className="l">Open</div></div>
                <div className="tool-stat"><div className="n">{stats.bad}</div><div className="l">Failed / unreachable</div></div>
                <div className="tool-stat"><div className="n">{stats.other}</div><div className="l">Other</div></div>
              </div>

              <div className="tool-section-title">
                Results
                <button
                  className="tool-btn tool-btn-ghost"
                  style={{ padding: "5px 10px", fontSize: 12 }}
                  onClick={() => downloadCsv(result.csv, `connectivity_results_${Date.now()}.csv`)}
                >
                  Download CSV
                </button>
              </div>
              <div className="tool-table-wrap">
                <table className="tool-table">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Destination</th>
                      <th>Port</th>
                      <th>Status</th>
                      <th>Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.source_host}</td>
                        <td>{r.destination}</td>
                        <td>{r.port}</td>
                        <td><span className={statusPillClass(r.status)}>{r.status}</span></td>
                        <td>{r.timestamp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
