import React from "react";

/**
 * Template only — no logic yet.
 *
 * Intent: pick a source host and a destination (host or IP) and resolve
 * which route the routing-map database says traffic would take between
 * them — walking each hop's routing table the way a real device would,
 * rather than doing a live network test.
 */
export default function RoutingTest() {
  return (
    <div>
      <div className="nt-tool-header">
        <h2>Routing test</h2>
        <p>Resolve the route a packet would take between a source host and a destination, using the saved routing-map database.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">
              <span>Source host</span>
            </div>
            <input className="tool-input" placeholder="e.g. edge-fw-01" disabled />
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>Destination</span>
              <span className="tool-hint">host or IP</span>
            </div>
            <input className="tool-input" placeholder="e.g. 10.20.30.5" disabled />
          </div>
          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" disabled>
              Trace route
            </button>
          </div>
        </div>

        <div className="tool-panel">
          <div className="tool-empty">Not built yet — this tab will trace the hop-by-hop route using the saved routing-map data.</div>
        </div>
      </div>
    </div>
  );
}
