import React, { useEffect, useMemo, useRef, useState } from "react";
import { exportRoutingHosts } from "./api.js";
import { networkKeyForCidr } from "./logic.js";
import { circleLayout, optimizeNodeOrder } from "./graphLayout.js";

// How long a node has to be continuously hovered before the "directly
// connected networks" tooltip appears — deliberately not instant, so
// briefly passing the mouse over a node while moving elsewhere on the
// graph doesn't pop it up.
const NODE_TOOLTIP_DELAY_MS = 2000;

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

// Same fallback as the routing table view: a host with no explicitly saved
// interfaces still tells us what networks it's on via its directly-connected
// routes, so we synthesize interface-shaped entries from those.
function interfacesForDisplay(detail) {
  const stored = detail?.interfaces || [];
  if (stored.length > 0) return stored;
  const seen = new Set();
  const out = [];
  for (const r of detail?.routes || []) {
    if ((r.nextHop || "").toLowerCase() !== "directly connected") continue;
    const name = (r.interface || "").trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push({ name, ipAddress: r.network, description: null });
  }
  return out;
}

// True for any address in 127.0.0.0/8 (loopback) — e.g. the "L" (local)
// host routes some vendor parsers record for an interface's own address
// can land here for lo0/loopback interfaces. Loopbacks aren't shared
// between devices, so they'd never legitimately connect two hosts; we
// exclude them up front rather than let every loopback-having host end up
// wrongly wired together.
function isLoopbackCidr(cidr) {
  if (typeof cidr !== "string") return false;
  const firstOctet = parseInt(cidr.split(".")[0], 10);
  return firstOctet === 127;
}

// Builds { nodes, edges } from the exported hosts:
//   nodes: [{ host }]
//   edges: [{ a, b, networks: [networkKey, ...] }]  — one entry per pair of
//   hosts that share at least one network, listing every shared network.
function buildGraph(hosts) {
  const nodes = hosts.map((h) => ({ host: h.host }));

  // networkKey -> Set of hostnames with an interface on that network
  const byNetwork = new Map();
  for (const h of hosts) {
    const ifaces = interfacesForDisplay(h);
    const keysOnThisHost = new Set();
    for (const iface of ifaces) {
      if (isLoopbackCidr(iface.ipAddress)) continue;
      const key = networkKeyForCidr(iface.ipAddress);
      if (key) keysOnThisHost.add(key);
    }
    for (const key of keysOnThisHost) {
      if (!byNetwork.has(key)) byNetwork.set(key, new Set());
      byNetwork.get(key).add(h.host);
    }
  }

  // pair key "hostA|||hostB" (sorted) -> Set of shared network keys
  const pairNetworks = new Map();
  for (const [networkKey, hostSet] of byNetwork) {
    const hostList = [...hostSet].sort();
    for (let i = 0; i < hostList.length; i++) {
      for (let j = i + 1; j < hostList.length; j++) {
        const pairKey = `${hostList[i]}|||${hostList[j]}`;
        if (!pairNetworks.has(pairKey)) pairNetworks.set(pairKey, new Set());
        pairNetworks.get(pairKey).add(networkKey);
      }
    }
  }

  const edges = [...pairNetworks.entries()].map(([pairKey, networkSet]) => {
    const [a, b] = pairKey.split("|||");
    return { a, b, networks: [...networkSet].sort() };
  });

  return { nodes, edges };
}

// host -> [{ name, network }] — every non-loopback interface's name and the
// network it's on (masked to the network address, not the host address), in
// the order the host's interfaces are recorded. Used by the hover tooltip.
function buildInterfaceLists(hosts) {
  const map = new Map();
  for (const h of hosts) {
    const list = [];
    for (const iface of interfacesForDisplay(h)) {
      if (isLoopbackCidr(iface.ipAddress)) continue;
      const network = networkKeyForCidr(iface.ipAddress) || iface.ipAddress;
      list.push({ name: iface.name, network });
    }
    map.set(h.host, list);
  }
  return map;
}

// Evenly spaced points around a circle, as percentages of the container
// box — kept in 0-100 so the same numbers drive both the node divs
// (left/top %) and the SVG overlay (viewBox="0 0 100 100").
/**
 * Loads every saved host from the routing-map database and draws them as
 * a graph: one node per host, with an edge between any two hosts that have
 * an interface on the same network (matched by masked network address +
 * prefix length, not just a raw string compare).
 */
export default function NetworkVisualization() {
  const [hosts, setHosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hoveredHost, setHoveredHost] = useState(null);
  const [tooltipHost, setTooltipHost] = useState(null);
  const tooltipTimerRef = useRef(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await exportRoutingHosts();
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

  // Any timer left running when the component unmounts (e.g. navigating
  // away mid-hover) would try to set state on a gone component — clear it.
  useEffect(() => {
    return () => clearTimeout(tooltipTimerRef.current);
  }, []);

  const clearTooltipTimer = () => {
    clearTimeout(tooltipTimerRef.current);
    tooltipTimerRef.current = null;
  };

  const handleNodeEnter = (host) => {
    setHoveredHost(host);
    clearTooltipTimer();
    tooltipTimerRef.current = setTimeout(() => setTooltipHost(host), NODE_TOOLTIP_DELAY_MS);
  };

  const handleNodeLeave = () => {
    setHoveredHost(null);
    clearTooltipTimer();
    setTooltipHost(null);
  };

  const { nodes, edges } = useMemo(() => buildGraph(hosts), [hosts]);
  const interfacesByHost = useMemo(() => buildInterfaceLists(hosts), [hosts]);
  const orderedHosts = useMemo(
    () => optimizeNodeOrder(nodes.map((n) => n.host), edges.map((e) => [e.a, e.b])),
    [nodes, edges]
  );
  const positions = useMemo(() => circleLayout(orderedHosts.length), [orderedHosts.length]);
  const posByHost = useMemo(() => {
    const m = new Map();
    orderedHosts.forEach((host, i) => m.set(host, positions[i]));
    return m;
  }, [orderedHosts, positions]);

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Network visualization</h2>
        <p>
          A graph view of the saved routing-map database — one node per host, with an edge
          drawn between any two hosts that have an interface on the same network.
        </p>
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

        {!loading && !error && hosts.length > 0 && edges.length === 0 && (
          <div className="tool-hint rm-graph-hint">
            No two hosts currently share a network — nodes are shown unconnected.
          </div>
        )}

        {hosts.length > 0 && (
          <div className="rm-graph-canvas">
            <svg className="rm-graph-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
              {edges.map((e) => {
                const pa = posByHost.get(e.a);
                const pb = posByHost.get(e.b);
                if (!pa || !pb) return null;
                const dimmed = hoveredHost && hoveredHost !== e.a && hoveredHost !== e.b;
                return (
                  <line
                    key={`${e.a}|||${e.b}`}
                    x1={pa.x}
                    y1={pa.y}
                    x2={pb.x}
                    y2={pb.y}
                    className={`rm-graph-edge${dimmed ? " is-dimmed" : ""}`}
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>
                      {e.a} ↔ {e.b}
                      {"\n"}
                      {e.networks.join(", ")}
                    </title>
                  </line>
                );
              })}
            </svg>

            {edges.map((e) => {
              const pa = posByHost.get(e.a);
              const pb = posByHost.get(e.b);
              if (!pa || !pb) return null;
              const dimmed = hoveredHost && hoveredHost !== e.a && hoveredHost !== e.b;
              const mid = { x: (pa.x + pb.x) / 2, y: (pa.y + pb.y) / 2 };
              return (
                <div
                  key={`label-${e.a}|||${e.b}`}
                  className={`rm-graph-edge-label${dimmed ? " is-dimmed" : ""}`}
                  style={{ left: `${mid.x}%`, top: `${mid.y}%` }}
                  title={`${e.a} ↔ ${e.b}\n${e.networks.join(", ")}`}
                >
                  {e.networks.join(", ")}
                </div>
              );
            })}

            {nodes.map((n) => {
              const pos = posByHost.get(n.host);
              if (!pos) return null;
              const dimmed = hoveredHost && hoveredHost !== n.host;
              const showTooltip = tooltipHost === n.host;
              const ifaces = interfacesByHost.get(n.host) || [];
              return (
                <div
                  className={`rm-node rm-graph-node${dimmed ? " is-dimmed" : ""}`}
                  key={n.host}
                  style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                  onMouseEnter={() => handleNodeEnter(n.host)}
                  onMouseLeave={handleNodeLeave}
                >
                  <RouterIcon />
                  <span className="rm-node-label">{n.host}</span>
                  {showTooltip && (
                    <div className="rm-node-tooltip" role="tooltip">
                      <div className="rm-node-tooltip-title">{n.host}</div>
                      {ifaces.length === 0 ? (
                        <div className="tool-hint">No interfaces on file.</div>
                      ) : (
                        <ul className="rm-node-tooltip-list">
                          {ifaces.map((iface, i) => (
                            <li key={i}>
                              <span className="rm-node-tooltip-iface">{iface.name}</span>
                              <span className="rm-node-tooltip-network">{iface.network}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}