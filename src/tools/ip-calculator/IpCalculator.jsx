import React, { useCallback, useState } from "react";
import "./ip-calculator.css";
import { calculateFromInputs, EXAMPLE } from "./logic.js";

// Turns a 32-bit int into "11000000.10101000.00000001.10000000" with the
// network-bit portion (the first `prefix` bits) wrapped separately from the
// host-bit portion, so the UI can color them differently — the usual way
// these calculators visualize "here's where the mask cuts the address".
function splitBinary(int, prefix) {
  const bits = int.toString(2).padStart(32, "0");
  const networkBits = bits.slice(0, prefix);
  const hostBits = bits.slice(prefix);
  const withDots = (s, offset) =>
    s
      .split("")
      .map((bit, i) => {
        const pos = offset + i;
        return pos > 0 && pos % 8 === 0 ? `.${bit}` : bit;
      })
      .join("");
  return { network: withDots(networkBits, 0), host: withDots(hostBits, prefix) };
}

function BinaryRow({ label, int, prefix }) {
  const { network, host } = splitBinary(int, prefix);
  return (
    <div className="ipc-binary-row">
      <div className="ipc-binary-label">{label}</div>
      <div className="ipc-binary-bits">
        <span className="ipc-bits-network">{network}</span>
        {host && <span className="ipc-bits-host">{host}</span>}
      </div>
    </div>
  );
}

export default function IpCalculator() {
  const [ip, setIp] = useState(EXAMPLE.ip);
  const [netmask, setNetmask] = useState(EXAMPLE.netmask);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const compute = useCallback(() => {
    setError(null);
    try {
      setResult(calculateFromInputs(ip, netmask));
    } catch (e) {
      setError(e.message);
      setResult(null);
    }
  }, [ip, netmask]);

  return (
    <div>
      <div className="nt-tool-header">
        <h2>IP calculator</h2>
        <p>Enter an IP address and netmask to work out the network's full details.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">
              <span>
                IP address <span className="tool-hint">plain, or combined as ip/prefix</span>
              </span>
            </div>
            <input
              className="tool-input"
              value={ip}
              onChange={(e) => setIp(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && compute()}
              placeholder="192.168.1.130 or 192.168.1.130/24"
            />
          </div>

          <div className="tool-field">
            <div className="tool-label">
              <span>
                Netmask <span className="tool-hint">prefix, dotted mask, or wildcard</span>
              </span>
            </div>
            <input
              className="tool-input"
              value={netmask}
              onChange={(e) => setNetmask(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && compute()}
              placeholder="24, /24, 255.255.255.0, or 0.0.0.255"
              disabled={ip.includes("/")}
            />
            {ip.includes("/") && (
              <div className="tool-hint" style={{ marginTop: 4 }}>
                Using the prefix from the IP field above — clear it there to enter a netmask separately.
              </div>
            )}
          </div>

          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" onClick={compute}>
              Calculate
            </button>
            <button
              className="tool-btn tool-btn-ghost"
              onClick={() => {
                setIp(EXAMPLE.ip);
                setNetmask(EXAMPLE.netmask);
                setError(null);
              }}
            >
              Load example
            </button>
          </div>

          {error && <div className="tool-error">{error}</div>}
        </div>

        <div className="tool-panel">
          {!result && !error && (
            <div className="tool-empty">Enter an IP address and netmask, then hit Calculate.</div>
          )}

          {result && (
            <>
              <div className="tool-section-title">
                {result.cidr}
                <span className="tool-hint">
                  {result.isPointToPoint
                    ? "/31 — point-to-point, no network/broadcast split"
                    : result.isSingleHost
                    ? "/32 — single host"
                    : `class ${result.ipClass}`}
                </span>
              </div>

              <div className="tool-summary">
                <div className="tool-stat">
                  <div className="n">{result.networkAddress}</div>
                  <div className="l">Network address</div>
                </div>
                <div className="tool-stat">
                  <div className="n">{result.broadcastAddress}</div>
                  <div className="l">Broadcast address</div>
                </div>
                <div className="tool-stat">
                  <div className="n">{result.usableHosts.toLocaleString("en-US")}</div>
                  <div className="l">Usable hosts</div>
                </div>
                <div className="tool-stat">
                  <div className="n">{result.totalAddresses.toLocaleString("en-US")}</div>
                  <div className="l">Total addresses</div>
                </div>
              </div>

              <div className="tool-table-wrap">
                <table className="tool-table">
                  <tbody>
                    <tr>
                      <td className="ipc-field">IP address</td>
                      <td>{result.inputIp}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">CIDR notation</td>
                      <td>{result.cidr}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Subnet mask</td>
                      <td>{result.subnetMask}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Wildcard mask</td>
                      <td>{result.wildcardMask}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Network address</td>
                      <td>{result.networkAddress}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Broadcast address</td>
                      <td>{result.broadcastAddress}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">First usable host</td>
                      <td>{result.hasHostRange || result.isPointToPoint ? result.firstHost : "—"}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Last usable host</td>
                      <td>{result.hasHostRange || result.isPointToPoint ? result.lastHost : "—"}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Usable hosts</td>
                      <td>{result.usableHosts.toLocaleString("en-US")}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Total addresses</td>
                      <td>{result.totalAddresses.toLocaleString("en-US")}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">IP class</td>
                      <td>{result.ipClass}</td>
                    </tr>
                    <tr>
                      <td className="ipc-field">Special use</td>
                      <td>
                        {result.specialUse ? (
                          <span className="tool-pill tool-pill-warn">{result.specialUse}</span>
                        ) : (
                          <span className="tool-pill tool-pill-ok">public / globally routable</span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="tool-section-title" style={{ marginTop: 20 }}>
                Binary
              </div>
              <div className="ipc-binary-wrap">
                <BinaryRow label="IP address" int={result.inputIpInt} prefix={result.prefix} />
                <BinaryRow label="Network" int={result.networkAddressInt} prefix={result.prefix} />
                <BinaryRow label="Broadcast" int={result.broadcastAddressInt} prefix={result.prefix} />
              </div>
              <div className="tool-hint" style={{ marginTop: 8 }}>
                <span className="ipc-legend-swatch ipc-bits-network" /> network bits ({result.prefix})
                &nbsp;&nbsp;
                <span className="ipc-legend-swatch ipc-bits-host" /> host bits ({32 - result.prefix})
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}