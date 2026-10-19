import React, { useState } from "react";
import { portDescription } from "./logic.js";

export default function PortTable({ device, selectedPort, onSelectPort, disabled }) {
  const [query, setQuery] = useState("");
  const ports = device.ports.filter((port) => [port.name, port.label, port.leadsTo, port.ipAddress].some((value) => (value || "").toLowerCase().includes(query.toLowerCase())));
  return <section aria-label="Device port table">
    <label className="sv-port-search">Find port<input className="tool-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, IP, label or destination" /></label>
    <div className="tool-table-wrap"><table className="tool-table sv-port-table"><thead><tr><th>Port</th><th>Family / speed</th><th>Label</th><th>Leads to</th><th>IP address</th><th>VLAN</th></tr></thead>
      <tbody>{ports.map((port) => <tr key={port.id} className={selectedPort === port.id ? "sv-table-selected" : ""}>
        <td data-label="Port"><button className="ip-subnet-link" disabled={disabled} onClick={() => onSelectPort(port.id)}>{port.name}</button></td>
        <td data-label="Family">{portDescription(port)}</td><td data-label="Label">{port.label || "—"}</td>
        <td data-label="Leads to">{port.leadsTo || "Unassigned"}</td><td data-label="IP address">{port.ipAddress || "—"}</td><td data-label="VLAN">{port.portMode === "access" ? `Access ${port.accessVlan}` : port.portMode === "trunk" ? `Trunk ${port.trunkVlans}` : "Not configured"}</td>
      </tr>)}</tbody></table></div>
    {!ports.length && <div className="tool-empty">No ports match this search.</div>}
  </section>;
}
