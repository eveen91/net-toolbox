import React, { useMemo, useState } from "react";
import { formatVlan, utilizationPercent } from "./logic.js";
import { filterSubnetsByTags, searchSubnets } from "./SubnetSearch.jsx";

export default function SubnetBrowser({ subnets, selectedTagIds, onSelect, loading }) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => searchSubnets(filterSubnetsByTags(subnets, selectedTagIds), query), [subnets, selectedTagIds, query]);
  return <section className="ip-subnet-browser" aria-label="Subnets">
    <div className="ip-browser-heading"><label>Filter subnets<input type="search" className="tool-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="CIDR, description or VLAN" /></label>
      <span role="status">{loading ? "Loading subnets…" : `${matches.length} subnets`}</span></div>
    {loading ? <div className="nt-loading-skeleton" aria-label="Loading subnet list" /> : matches.length === 0 ? <div className="tool-empty">{subnets.length ? "No subnets match these filters." : "No subnets yet. Add or import a subnet to get started."}
      {query && <button className="tool-btn tool-btn-ghost" onClick={() => setQuery("")}>Clear search</button>}</div>
      : <div className="tool-table-wrap"><table className="tool-table ip-subnet-list-table"><thead><tr><th>Subnet</th><th>Description</th><th>VLAN</th><th>Allocated</th><th>Recorded addresses</th></tr></thead>
        <tbody>{matches.map((subnet) => <tr key={subnet.id}>
          <td data-label="Subnet"><button className="ip-subnet-link" onClick={() => onSelect(subnet.id)}>{subnet.cidr}</button></td>
          <td data-label="Description">{subnet.description || "—"}</td><td data-label="VLAN">{formatVlan(subnet.vlan)}</td>
          <td data-label="Allocated">{utilizationPercent(subnet)}%<span className="ip-browser-util" aria-hidden="true"><span style={{ width: `${utilizationPercent(subnet)}%` }} /></span></td>
          <td data-label="Recorded">{subnet.usedCount} used · {subnet.reservedCount} reserved · {subnet.freeCount} free</td>
        </tr>)}</tbody></table></div>}
  </section>;
}
