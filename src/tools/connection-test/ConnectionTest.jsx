import React, { useMemo, useRef, useState } from "react";
import "./connection-test.css";
import { parseSources, parseLines, parsePorts, validateWorkload, validateSettings, downloadCsv } from "./logic.js";
import { runConnectionTest } from "./api.js";

const EXAMPLE = {
  sources: "web01,linux\napp02,linux\nwinapp01,windows\nwinsql01,windows",
  destinations: "10.0.1.10\n10.0.1.20\ndb-prod.internal",
  ports: "443\n1433\n22",
};

function countLabel(count, label) {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}

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
  const [runSummary, setRunSummary] = useState(null);
  const runningRef = useRef(false);

  const run = async (event) => {
    event.preventDefault();
    if (runningRef.current) return;
    setError(null);
    setResult(null);
    try {
      const parsedSources = parseSources(sources);
      if (parsedSources.length === 0) throw new Error("Enter at least one source (hostname,linux or hostname,windows).");
      const parsedDestinations = parseLines(destinations);
      if (parsedDestinations.length === 0) throw new Error("Enter at least one destination host.");
      const parsedPorts = parsePorts(ports);
      if (parsedPorts.length === 0) throw new Error("Enter at least one port.");

      const combinations = validateWorkload(parsedSources, parsedDestinations, parsedPorts);
      validateSettings({ connectTimeout, sshPort, winrmPort, winrmScheme, winrmTransport });
      const hasLinux = parsedSources.some((s) => s.os === "linux");
      const hasWindows = parsedSources.some((s) => s.os === "windows");
      if (hasLinux && (!linuxUser || !linuxPass)) throw new Error("Enter Linux SSH credentials — you have Linux sources.");
      if (hasWindows && (!winUser || !winPass)) throw new Error("Enter Windows credentials — you have Windows sources.");

      runningRef.current = true;
      setRunSummary(`${countLabel(parsedSources.length, "source")} × ${countLabel(parsedDestinations.length, "destination")} × ${countLabel(parsedPorts.length, "port")} = ${countLabel(combinations, "test")}`);
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
      runningRef.current = false;
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
    <div className="ct-tool">
      <div className="nt-tool-header">
        <h2>Connection test</h2>
        <p>SSH into Linux sources and WinRM into Windows sources, then check TCP connectivity to each destination:port.</p>
      </div>

      <div className="tool-layout">
        <form className="tool-panel" onSubmit={run} noValidate aria-label="Connection test configuration">
          <fieldset className="ct-run-fields" disabled={loading}>
          <legend className="ct-sr-only">Connection test configuration</legend>
          <p className="tool-hint" id="ct-limits">Up to 16 sources, 64 destinations, 32 ports and 1024 combinations per run.</p>
          <div className="tool-field">
            <label className="tool-label" htmlFor="ct-sources">Sources <span className="tool-hint">one per line: host,linux or host,windows</span></label>
            <textarea id="ct-sources" aria-describedby="ct-limits" className="tool-textarea" value={sources} onChange={(e) => setSources(e.target.value)} />
          </div>

          <div className="tool-field">
            <label className="tool-label" htmlFor="ct-destinations">Destinations <span className="tool-hint">one per line</span></label>
            <textarea id="ct-destinations" className="tool-textarea" style={{ minHeight: 64 }} value={destinations} onChange={(e) => setDestinations(e.target.value)} />
          </div>

          <div className="tool-field">
            <label className="tool-label" htmlFor="ct-ports">Ports <span className="tool-hint">one per line</span></label>
            <textarea id="ct-ports" className="tool-textarea" style={{ minHeight: 56 }} value={ports} onChange={(e) => setPorts(e.target.value)} />
          </div>

          <hr className="ct-divider" />

          <fieldset className="ct-credentials">
            <legend className="ct-section-label">Linux SSH credentials</legend>
            <div className="ct-cred-grid">
              <label htmlFor="ct-linux-user">Username<input id="ct-linux-user" className="tool-input" autoComplete="off" value={linuxUser} onChange={e => setLinuxUser(e.target.value)} /></label>
              <label htmlFor="ct-linux-pass">Password<input id="ct-linux-pass" className="tool-input" autoComplete="off" type="password" value={linuxPass} onChange={e => setLinuxPass(e.target.value)} /></label>
            </div>
          </fieldset>
          <fieldset className="ct-credentials">
            <legend className="ct-section-label">Windows / WinRM credentials</legend>
            <div className="ct-cred-grid">
              <label htmlFor="ct-win-user">Username<input id="ct-win-user" className="tool-input" autoComplete="off" value={winUser} onChange={e => setWinUser(e.target.value)} /></label>
              <label htmlFor="ct-win-pass">Password<input id="ct-win-pass" className="tool-input" autoComplete="off" type="password" value={winPass} onChange={e => setWinPass(e.target.value)} /></label>
            </div>
          </fieldset>
          <div className="tool-hint">Sent directly to the backend for this run only — not stored.</div>

          <details className="ct-advanced" style={{ marginTop: 16 }}>
            <summary>Advanced settings</summary>
            <div className="ct-advanced-grid">
              <div className="tool-field">
                <label className="tool-label" htmlFor="ct-timeout">Connect timeout (s)</label>
                <input id="ct-timeout" className="tool-input" type="number" min={1} max={60} step={1} value={connectTimeout} onChange={(e) => setConnectTimeout(Number(e.target.value))} />
              </div>
              <div className="tool-field">
                <label className="tool-label" htmlFor="ct-ssh-port">SSH port</label>
                <input id="ct-ssh-port" className="tool-input" type="number" min={1} max={65535} step={1} value={sshPort} onChange={(e) => setSshPort(Number(e.target.value))} />
              </div>
              <div className="tool-field">
                <label className="tool-label" htmlFor="ct-winrm-port">WinRM port</label>
                <input id="ct-winrm-port" className="tool-input" type="number" min={1} max={65535} step={1} value={winrmPort} onChange={(e) => setWinrmPort(Number(e.target.value))} />
              </div>
              <div className="tool-field">
                <label className="tool-label" htmlFor="ct-scheme">WinRM scheme</label>
                <select id="ct-scheme" className="tool-input" value={winrmScheme} onChange={e => { const scheme = e.target.value; setWinrmScheme(scheme); if (winrmPort === 5985 || winrmPort === 5986) setWinrmPort(scheme === "https" ? 5986 : 5985); }}>
                  <option value="http" disabled={winrmTransport === "basic"}>http (5985)</option>
                  <option value="https">https (5986)</option>
                </select>
              </div>
              <div className="tool-field" style={{ gridColumn: "1 / -1" }}>
                <label className="tool-label" htmlFor="ct-transport">WinRM auth transport</label>
                <select id="ct-transport" aria-describedby="ct-basic-help" className="tool-input" value={winrmTransport} onChange={e => { const transport = e.target.value; setWinrmTransport(transport); if (transport === "basic") { setWinrmScheme("https"); if (winrmPort === 5985) setWinrmPort(5986); } }}>
                  <option value="ntlm">NTLM (local accounts, non-domain)</option>
                  <option value="kerberos">Kerberos (domain-joined)</option>
                  <option value="basic">Basic (requires HTTPS; enable on target)</option>
                  <option value="credssp">CredSSP</option>
                </select>
                <p id="ct-basic-help" className="tool-hint">Basic authentication requires HTTPS with a trusted server certificate.</p>
              </div>
            </div>
          </details>

          <div className="tool-actions">
            <button type="submit" className="tool-btn tool-btn-primary" disabled={loading}>
              {loading ? "Running…" : "Run test"}
            </button>
            <button
              type="button"
              className="tool-btn tool-btn-ghost"
              onClick={() => {
                setSources(EXAMPLE.sources);
                setDestinations(EXAMPLE.destinations);
                setPorts(EXAMPLE.ports);
                setError(null);
                setResult(null);
                setRunSummary(null);
              }}
            >
              Load example
            </button>
          </div>

          </fieldset>
          {error && <div className="tool-error" role="alert">{error}</div>}
        </form>

        <div className="tool-panel">
          {!result && !loading && !error && (
            <div className="tool-empty">Fill in sources, destinations, and ports, then hit Run test.</div>
          )}
          <div role="status" aria-live="polite" aria-atomic="true" className={loading ? "ct-loading" : "ct-run-status"}>
            {loading ? `Connecting to sources and testing ports… ${runSummary}` : result ? `Completed: ${countLabel(stats.total, "result")}, ${stats.open} open, ${stats.bad} failed or unreachable, ${stats.other} other. ${runSummary}.` : ""}
          </div>

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
