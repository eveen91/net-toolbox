import React, { useEffect, useState } from "react";
import { listRoutingHosts } from "./api.js";

/** Simple router glyph, drawn with CSS vars so it themes with the rest of the app. */
function RouterIcon() {
  return (
    <svg className="rm-node-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="18" width="40" height="16" rx="3" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="12" cy="26" r="1.6" fill="currentColor" />
      <circle cx="18" cy="26" r="1.6" fill="currentColor" />
      <path d="M24 18V11M24 11C24 8 26 6 30 6M24 11C24 8 22 6 18 6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M30 34v4M18 34v4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

/**
 * For now: load every saved host from the routing-map database and lay
 * them out as router nodes (icon + hostname). Edges between hosts (drawn
 * from each host's routes/next-hops) come next.
 */
export default function NetworkVisualization() {
  const [hosts, setHosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRoutingHosts();
      setHosts(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Network visualization</h2>
        <p>A graph view of the saved routing-map database — hosts and how their routes connect.</p>
      </div>

      <div className="tool-panel">
        <div className="rm-section-label">
          Hosts <span className="tool-hint">{hosts.length}</span>
          <button className="tool-btn tool-btn-ghost rm-refresh" onClick={load} disabled={loading}>
            {loading ? "…" : "Refresh"}
          </button>
        </div>

        {error && <div className="tool-error">{error}</div>}

        {!loading && !error && hosts.length === 0 && (
          <div className="tool-empty">No hosts saved yet — add some in the Routing Map tab first.</div>
        )}

        {hosts.length > 0 && (
          <div className="rm-graph">
            {hosts.map((h) => (
              <div className="rm-node" key={h.host}>
                <RouterIcon />
                <span className="rm-node-label">{h.host}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
