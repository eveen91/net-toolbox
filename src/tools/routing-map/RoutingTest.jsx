import React, { useEffect, useMemo, useState } from "react";
import "./routing-map.css";
import { exportRoutingHosts } from "./api.js";
import { traceRoute } from "./logic.js";

/**
 * Resolve the path a packet from `sourceAddress` to `destAddress` would take
 * through the saved routing-map database:
 *   1. Find which saved device's interface network the source address falls
 *      within — that's the device the source host is plugged into.
 *   2. At each device, if the destination address falls within one of that
 *      device's own interface networks, the trace is done. Otherwise, look
 *      up the device's most specific route to the destination and jump to
 *      whichever device owns that route's next-hop address, then repeat.
 * All of this reads only the saved routing-map data — it doesn't touch the
 * network. See traceRoute() in logic.js for the algorithm itself.
 */

function describeHop(step, isLast) {
  if (step.action === "delivered") {
    return {
      title: `${step.host}`,
      detail: `Destination is on ${step.interface} (${step.network}) — delivered here.`,
      tone: "ok",
    };
  }
  if (step.action === "forward") {
    return {
      title: `${step.host}`,
      detail: `Route ${step.network} → ${step.nextHop}${step.viaInterface ? ` via ${step.viaInterface}` : ""}`,
      tone: "forward",
    };
  }
  if (step.action === "no-route") {
    return { title: `${step.host}`, detail: "No route covers the destination here.", tone: "error" };
  }
  if (step.action === "connected-mismatch") {
    return {
      title: `${step.host}`,
      detail: `Route says ${step.network} is directly connected, but no saved interface matches it.`,
      tone: "error",
    };
  }
  return { title: step.host, detail: "", tone: isLast ? "error" : "forward" };
}

export default function RoutingTest() {
  const [hosts, setHosts] = useState([]);
  const [loadingHosts, setLoadingHosts] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [result, setResult] = useState(null);

  const load = async () => {
    setLoadingHosts(true);
    setLoadError(null);
    try {
      const data = await exportRoutingHosts();
      setHosts(data);
    } catch (e) {
      setLoadError(e.message);
    } finally {
      setLoadingHosts(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const canTrace = source.trim() && destination.trim() && !loadingHosts;

  const handleTrace = () => {
    if (!canTrace) return;
    setResult(traceRoute(hosts, source.trim(), destination.trim()));
  };

  const entryLine = useMemo(() => {
    if (!result || !result.entryHost) return null;
    return `${source.trim()} is attached to "${result.entryHost}".`;
  }, [result, source]);

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Routing test</h2>
        <p>
          Resolve the route a packet would take between a source host and a destination, using the saved
          routing-map database.
        </p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">
              <span>Source host address</span>
              <span className="tool-hint">must be on a saved device's interface network</span>
            </div>
            <input
              className="tool-input"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="e.g. 10.0.1.20"
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>Destination host address</span>
            </div>
            <input
              className="tool-input"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="e.g. 10.0.2.30"
            />
          </div>
          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" onClick={handleTrace} disabled={!canTrace}>
              Trace route
            </button>
            <button className="tool-btn tool-btn-ghost" onClick={load} disabled={loadingHosts}>
              {loadingHosts ? "Loading…" : "Refresh devices"}
            </button>
          </div>
          {loadError && <div className="tool-error">{loadError}</div>}
          {!loadingHosts && !loadError && (
            <div className="tool-hint" style={{ marginTop: 10 }}>
              {hosts.length} saved device{hosts.length !== 1 ? "s" : ""} to trace across.
            </div>
          )}
        </div>

        <div className="tool-panel">
          {!result && (
            <div className="tool-empty">Enter a source and destination address, then click "Trace route".</div>
          )}

          {result && (
            <>
              <div className="tool-section-title">{result.ok ? "Route found" : "Trace stopped"}</div>

              {entryLine && (
                <div className="tool-hint" style={{ marginBottom: 12 }}>
                  {entryLine}
                </div>
              )}

              {result.steps.length > 0 && (
                <div className="rm-trace-hops">
                  {result.steps.map((step, i) => {
                    const isLast = i === result.steps.length - 1;
                    const { title, detail, tone } = describeHop(step, isLast && !result.ok);
                    return (
                      <div key={i} className="rm-trace-hop">
                        <div className={`rm-trace-hop-marker rm-trace-hop-${tone}`}>{i + 1}</div>
                        <div className="rm-trace-hop-body">
                          <div className="rm-trace-hop-title">{title}</div>
                          <div className="rm-trace-hop-detail">{detail}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {result.ok ? (
                <div className="rm-notice rm-notice-ok" style={{ marginTop: 14 }}>
                  Reached {destination.trim()} on "{result.destinationHost}" via {result.destinationInterface}.
                </div>
              ) : (
                <div className="tool-error">{result.error}</div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}