import React, { useState } from "react";
import { pingHost, checkRoute } from "./api.js";

export default function ReachabilityTab({ locateForm }) {
  const [pingIp, setPingIp] = useState("");
  const [pingResult, setPingResult] = useState(null);
  const [routeResult, setRouteResult] = useState(null);

  const handlePing = async () => {
    const result = await pingHost(pingIp);
    setPingResult(result);
  };

  const handleRouteCheck = async () => {
    const result = await checkRoute(pingIp, locateForm.username, locateForm.password);
    setRouteResult(result);
  };

  return (
    <div>
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

      <div className="tool-panel">
        <h3>Route check</h3>
        <p className="tool-hint">
          Uses credentials from the Locate tab.
        </p>
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
    </div>
  );
}
