import React, { useState } from "react";
import AuditTimeline from "../tools/ipam/AuditTimeline.jsx";

export default function AuditLogPanel() {
  const [scope, setScope] = useState("all");
  const [subnetId, setSubnetId] = useState("");
  const [addressId, setAddressId] = useState("");
  const selectedSubnetId = scope === "subnet" && subnetId ? subnetId : undefined;
  const selectedAddressId = scope === "address" && addressId ? addressId : undefined;

  return (
    <div className="nt-admin-panel">
      <div className="audit-scope-bar" aria-label="Audit scope">
        <label className="audit-filter-field" htmlFor="audit-scope">
          <span>Show</span>
          <select id="audit-scope" className="tool-input" value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="all">All changes</option>
            <option value="subnet">A subnet</option>
            <option value="address">An address</option>
          </select>
        </label>
        {scope === "subnet" && (
          <label className="audit-filter-field audit-filter-id" htmlFor="audit-subnet-id">
            <span>Subnet ID</span>
            <input id="audit-subnet-id" className="tool-input" type="number" min="1" placeholder="e.g. 42" value={subnetId} onChange={(event) => setSubnetId(event.target.value)} />
          </label>
        )}
        {scope === "address" && (
          <label className="audit-filter-field audit-filter-id" htmlFor="audit-address-id">
            <span>Address ID</span>
            <input id="audit-address-id" className="tool-input" type="number" min="1" placeholder="e.g. 128" value={addressId} onChange={(event) => setAddressId(event.target.value)} />
          </label>
        )}
      </div>
      {scope === "all" || selectedSubnetId || selectedAddressId ? (
        <AuditTimeline
          key={`${scope}-${selectedSubnetId || selectedAddressId || "all"}`}
          subnetId={selectedSubnetId}
          addressId={selectedAddressId}
          title="IPAM Audit Log"
          description="Track address, subnet, DHCP pool, tag, and discovery changes across the inventory."
          adminExport
        />
      ) : <div className="tool-empty">Enter an ID to load scoped history.</div>}
    </div>
  );
}
