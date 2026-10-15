import React, { useMemo, useState } from "react";
import { formatVlan, utilizationPercent } from "./logic.js";
import { filterSubnetsByTags, searchSubnets } from "./SubnetSearch.jsx";
import { subnetBrowserRows } from "./subnetHierarchy.js";

export default function SubnetBrowser({ subnets, selectedTagIds, onSelect, loading }) {
  const [query, setQuery] = useState("");
  const [collapsedIds, setCollapsedIds] = useState(() => new Set());
  const matches = useMemo(() => searchSubnets(filterSubnetsByTags(subnets, selectedTagIds), query), [subnets, selectedTagIds, query]);
  const filtering = Boolean(query.trim() || selectedTagIds.length);
  const rows = useMemo(() => subnetBrowserRows(subnets, matches.map(subnet => subnet.id), collapsedIds, filtering), [subnets, matches, collapsedIds, filtering]);
  const byId = useMemo(() => new Map(subnets.map(subnet => [subnet.id, subnet])), [subnets]);
  const toggle = id => setCollapsedIds(previous => {
    const next = new Set(previous);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  return <section className="ip-subnet-browser" aria-label="Subnets">
    <div className="ip-browser-heading"><label>Filter subnets<input type="search" className="tool-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="CIDR, description or VLAN" /></label>
      <span role="status">{loading ? "Loading subnets…" : `${matches.length} ${filtering ? 'matching ' : ''}subnet${matches.length === 1 ? '' : 's'}`}</span></div>
    {loading ? <div className="nt-loading-skeleton" aria-label="Loading subnet list" /> : matches.length === 0 ? <div className="tool-empty">{subnets.length ? "No subnets match these filters." : "No subnets yet. Add or import a subnet to get started."}
      {query && <button className="tool-btn tool-btn-ghost" onClick={() => setQuery("")}>Clear search</button>}</div>
      : <div className="tool-table-wrap"><table className="tool-table ip-subnet-list-table"><thead><tr><th>Subnet</th><th>Description</th><th>VLAN</th><th>Allocated</th><th>Recorded addresses</th></tr></thead>
        <tbody>{rows.map(({ subnet, depth, isContext, hasChildren, expanded }) => <tr key={subnet.id} className={isContext ? "ip-subnet-context" : undefined}>
          <td data-label="Subnet"><div className="ip-subnet-tree-node" style={{ paddingInlineStart: `${Math.min(depth, 5) * 16}px` }}>
            {hasChildren ? <button type="button" className="ip-subnet-tree-toggle" aria-label={`${expanded ? 'Collapse' : 'Expand'} subnet ${subnet.cidr}`} aria-expanded={expanded}
              disabled={filtering} onClick={() => toggle(subnet.id)}><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d={expanded ? 'M4 6l4 4 4-4' : 'M6 4l4 4-4 4'} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg></button> : <span className="ip-subnet-tree-spacer" aria-hidden="true">{depth > 0 && <svg width="16" height="16" viewBox="0 0 16 16" focusable="false"><path d="M4 3v7h8m-3-3 3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>}</span>}
            <div><button className="ip-subnet-link" onClick={() => onSelect(subnet.id)}>{subnet.cidr}</button>
              {subnet.parentId != null && byId.has(subnet.parentId) && <small className="ip-subnet-parent">In {byId.get(subnet.parentId).cidr}</small>}
              {isContext && <small className="ip-subnet-parent">Parent context</small>}
            </div>
          </div></td>
          <td data-label="Description">{subnet.description || "—"}</td><td data-label="VLAN">{formatVlan(subnet.vlan)}</td>
          <td data-label="Allocated">{utilizationPercent(subnet)}%<span className="ip-browser-util" aria-hidden="true"><span style={{ width: `${utilizationPercent(subnet)}%` }} /></span></td>
          <td data-label="Recorded">{subnet.usedCount} used · {subnet.reservedCount} reserved · {subnet.freeCount} free</td>
        </tr>)}</tbody></table></div>}
  </section>;
}
