import React, { useState, useMemo, useCallback } from "react";
import "./subnet-splitter.css";
import {
  rangeFromCidr,
  rangeFromString,
  getFreeRanges,
  getCidrsFromRange,
  findMatchingCidr,
  parseLines,
  formatAddresses,
  ipToInt,
  intToIp,
  EXAMPLE,
} from "./logic.js";

export default function SubnetSplitter() {
  const [network, setNetwork] = useState(EXAMPLE.network);
  const [excludes, setExcludes] = useState(EXAMPLE.excludes);
  const [checkIps, setCheckIps] = useState(EXAMPLE.checkIps);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [hovered, setHovered] = useState(null);

  const compute = useCallback(() => {
    setError(null);
    try {
      if (!network.trim()) throw new Error("Enter a base network in CIDR notation, e.g. 10.0.0.0/24");
      const networkRange = rangeFromCidr(network.trim());

      const excludeLines = parseLines(excludes);
      if (excludeLines.length === 0) {
        throw new Error("Enter at least one excluded range (CIDR or start-end).");
      }
      const excludedRanges = excludeLines.map((line) => rangeFromString(line));

      const { free, merged } = getFreeRanges(networkRange, excludedRanges);

      const allCidrs = [];
      for (const fr of free) {
        for (const c of getCidrsFromRange(fr.start, fr.end)) allCidrs.push(c);
      }

      const totalAddresses = allCidrs.reduce((sum, c) => sum + c.addresses, 0);
      const networkSize = networkRange.end - networkRange.start + 1;

      let ipChecks = [];
      const ipLines = parseLines(checkIps);
      if (ipLines.length > 0) {
        ipChecks = ipLines.map((line) => {
          try {
            const ipInt = ipToInt(line);
            const match = findMatchingCidr(ipInt, allCidrs);
            return { ip: line, valid: true, inList: !!match, matchedCidr: match || "" };
          } catch {
            return { ip: line, valid: false, inList: false, matchedCidr: "" };
          }
        });
      }

      const segments = [
        ...merged.map((m) => ({ kind: "excluded", start: m.start, end: m.end })),
        ...allCidrs.map((c) => ({ kind: "free", ...c })),
      ].sort((a, b) => a.start - b.start);

      setResult({ networkRange, networkSize, allCidrs, totalAddresses, ipChecks, segments });
    } catch (e) {
      setError(e.message);
      setResult(null);
    }
  }, [network, excludes, checkIps]);

  const matchedCount = useMemo(
    () => (result ? result.ipChecks.filter((r) => r.inList).length : 0),
    [result]
  );

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Subnet splitter</h2>
        <p>Carve a network into the largest possible CIDR blocks around one or more excluded ranges.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">Base network</div>
            <input
              className="tool-input"
              value={network}
              onChange={(e) => setNetwork(e.target.value)}
              placeholder="10.0.0.0/24"
            />
          </div>

          <div className="tool-field">
            <div className="tool-label">
              <span>
                Excluded ranges <span className="tool-hint">one per line</span>
              </span>
            </div>
            <textarea
              className="tool-textarea"
              value={excludes}
              onChange={(e) => setExcludes(e.target.value)}
              placeholder={"10.0.0.128/26\n10.0.0.10-10.0.0.20"}
            />
          </div>

          <div className="tool-field">
            <div className="tool-label">
              <span>
                Check IPs <span className="tool-hint">optional</span>
              </span>
            </div>
            <textarea
              className="tool-textarea"
              style={{ minHeight: 64 }}
              value={checkIps}
              onChange={(e) => setCheckIps(e.target.value)}
              placeholder={"10.0.0.15\n10.0.1.150"}
            />
          </div>

          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" onClick={compute}>
              Compute
            </button>
            <button
              className="tool-btn tool-btn-ghost"
              onClick={() => {
                setNetwork(EXAMPLE.network);
                setExcludes(EXAMPLE.excludes);
                setCheckIps(EXAMPLE.checkIps);
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
            <div className="tool-empty">Enter a network and at least one excluded range, then hit Compute.</div>
          )}

          {result && (
            <>
              <div className="tool-section-title">Address space</div>
              <div className="ss-bar-wrap">
                <div className="ss-bar-labels">
                  <span>{intToIp(result.networkRange.start)}</span>
                  <span>{network.trim()}</span>
                  <span>{intToIp(result.networkRange.end)}</span>
                </div>
                <div className="ss-bar">
                  {result.segments.map((seg, i) => {
                    const size = seg.end - seg.start + 1;
                    const width = (size / result.networkSize) * 100;
                    const cls =
                      seg.kind === "excluded"
                        ? "ss-seg ss-seg-excluded"
                        : `ss-seg ${i % 2 === 0 ? "ss-seg-free-a" : "ss-seg-free-b"}`;
                    return (
                      <div
                        key={i}
                        className={cls}
                        style={{ flexBasis: `${width}%`, flexGrow: 0, flexShrink: 0 }}
                        onMouseEnter={() => setHovered(seg)}
                        onMouseLeave={() => setHovered(null)}
                      />
                    );
                  })}
                </div>
              </div>
              <div className="ss-legend">
                <div className="ss-legend-item">
                  <span className="ss-swatch" style={{ background: "var(--accent)" }} />
                  Free / returned subnet
                </div>
                <div className="ss-legend-item">
                  <span
                    className="ss-swatch"
                    style={{
                      background:
                        "repeating-linear-gradient(135deg, var(--warn-dim), var(--warn-dim) 3px, #3a2a17 3px, #3a2a17 6px)",
                    }}
                  />
                  Excluded
                </div>
              </div>
              {hovered && (
                <div className="ss-tooltip">
                  {hovered.kind === "excluded" ? (
                    <>
                      <span className="k">excluded</span> {intToIp(hovered.start)} – {intToIp(hovered.end)} (
                      {formatAddresses(hovered.end - hovered.start + 1)} addrs)
                    </>
                  ) : (
                    <>
                      <span className="k">cidr</span> {hovered.cidr} &nbsp;
                      <span className="k">first</span> {hovered.firstIp} &nbsp;
                      <span className="k">last</span> {hovered.lastIp} &nbsp;
                      <span className="k">addrs</span> {formatAddresses(hovered.addresses)}
                    </>
                  )}
                </div>
              )}

              <div className="tool-summary">
                <div className="tool-stat">
                  <div className="n">{result.allCidrs.length}</div>
                  <div className="l">Subnets returned</div>
                </div>
                <div className="tool-stat">
                  <div className="n">{formatAddresses(result.totalAddresses)}</div>
                  <div className="l">Free addresses</div>
                </div>
                <div className="tool-stat">
                  <div className="n">{formatAddresses(result.networkSize)}</div>
                  <div className="l">Network size</div>
                </div>
              </div>

              <div className="tool-section-title">Resulting subnets</div>
              <div className="tool-table-wrap">
                <table className="tool-table">
                  <thead>
                    <tr>
                      <th>CIDR</th>
                      <th>Subnet mask</th>
                      <th>First IP</th>
                      <th>Last IP</th>
                      <th>Addresses</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.allCidrs.map((c, i) => (
                      <tr key={i}>
                        <td>{c.cidr}</td>
                        <td>{c.subnetMask}</td>
                        <td>{c.firstIp}</td>
                        <td>{c.lastIp}</td>
                        <td>{formatAddresses(c.addresses)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {result.ipChecks.length > 0 && (
                <>
                  <div className="tool-section-title" style={{ marginTop: 20 }}>
                    IP membership check
                    <span style={{ color: "var(--muted)", fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
                      {matchedCount} of {result.ipChecks.length} fall within the resulting subnet list
                    </span>
                  </div>
                  <div className="tool-table-wrap">
                    <table className="tool-table">
                      <thead>
                        <tr>
                          <th>IP</th>
                          <th>In subnet list</th>
                          <th>Matched CIDR</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.ipChecks.map((r, i) => (
                          <tr key={i}>
                            <td>{r.ip}</td>
                            <td>
                              {!r.valid ? (
                                <span className="tool-pill tool-pill-warn">invalid ip</span>
                              ) : r.inList ? (
                                <span className="tool-pill tool-pill-ok">true</span>
                              ) : (
                                <span className="tool-pill tool-pill-no">false</span>
                              )}
                            </td>
                            <td>{r.matchedCidr}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
