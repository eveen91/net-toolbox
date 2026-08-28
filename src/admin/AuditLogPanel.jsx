import React, { useState, useEffect } from "react";
import {
  getAuditLogForAddress,
  getAuditLogForSubnet,
} from "../tools/ipam/api.js";

const CHANGE_TYPE_STYLES = {
  create: { color: "#22c55e", bg: "#052e16", label: "Created" },
  update: { color: "#3b82f6", bg: "#1e3a8a", label: "Updated" },
  delete: { color: "#ef4444", bg: "#450a0a", label: "Deleted" },
  reassign: { color: "#a855f7", bg: "#3b0764", label: "Reassigned" },
  status: { color: "#eab308", bg: "#422006", label: "Status Change" },
  hostname: { color: "#06b6d4", bg: "#083344", label: "Hostname Change" },
};

function formatTimestamp(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function DiffView({ oldVal, newVal }) {
  if (!oldVal && !newVal) return null;

  const allKeys = new Set([
    ...(oldVal ? Object.keys(oldVal) : []),
    ...(newVal ? Object.keys(newVal) : []),
  ]);

  if (allKeys.size === 0) return null;

  return (
    <div className="audit-diff">
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Old</th>
            <th>New</th>
          </tr>
        </thead>
        <tbody>
          {Array.from(allKeys).map((key) => (
            <tr key={key}>
              <td className="audit-field">{key}</td>
              <td className="audit-old">
                {oldVal?.[key] !== undefined ? String(oldVal[key] ?? "—") : "—"}
              </td>
              <td className="audit-new">
                {newVal?.[key] !== undefined ? String(newVal[key] ?? "—") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AuditLogPanel() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [scope, setScope] = useState("all");
  const [subnetId, setSubnetId] = useState("");
  const [addressId, setAddressId] = useState("");

  useEffect(() => {
    loadAuditLog();
  }, [scope, subnetId, addressId]);

  const loadAuditLog = async () => {
    setLoading(true);
    setError(null);
    try {
      let result;
      if (scope === "address" && addressId) {
        result = await getAuditLogForAddress(parseInt(addressId, 10), 100);
      } else if (scope === "subnet" && subnetId) {
        result = await getAuditLogForSubnet(parseInt(subnetId, 10), 50);
      } else {
        const resp = await fetch(`/api/ipam/audit/export?limit=200`, {
          credentials: "include",
        });
        if (!resp.ok) throw new Error("Failed to load audit log");
        const raw = await resp.json();
        result = raw.map((r) => ({
          id: r.id,
          addressId: r.addressId,
          userId: r.userId,
          username: r.username,
          changeType: r.changeType,
          oldValue: r.oldValue,
          newValue: r.newValue,
          description: r.description,
          ipAddress: r.ipAddress,
          subnetCidr: r.subnetCidr,
          createdAt: r.createdAt,
        }));
      }
      setEntries(Array.isArray(result) ? result : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (scope === "subnet" && subnetId) params.append("subnet_id", subnetId);
      params.append("limit", 1000);

      const resp = await fetch(
        `/api/ipam/audit/export?${params.toString()}`,
        { credentials: "include" },
      );
      if (!resp.ok) throw new Error("Export failed");

      const data = await resp.json();
      const csv = [
        [
          "ID",
          "Address ID",
          "User",
          "Change Type",
          "IP Address",
          "Subnet",
          "Description",
          "Created At",
        ].join(","),
        ...data.map((e) =>
          [
            e.id,
            e.addressId,
            e.username || "",
            e.changeType,
            e.ipAddress || "",
            e.subnetCidr || "",
            `"${(e.description || "").replace(/"/g, '""')}"`,
            e.createdAt,
          ].join(","),
        ),
      ].join("\n");

      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-log-${subnetId || "all"}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  };

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="nt-admin-panel">
      <div className="audit-header">
        <h3>IPAM Audit Log</h3>
        <button
          className="tool-btn tool-btn-ghost"
          onClick={handleExport}
          disabled={exporting}
        >
          {exporting ? "Exporting…" : "Export CSV"}
        </button>
      </div>

      <div className="audit-filters">
        <label className="tool-hint">Scope:</label>
        <select
          className="tool-input"
          value={scope}
          onChange={(e) => setScope(e.target.value)}
        >
          <option value="all">All changes</option>
          <option value="subnet">By subnet ID</option>
          <option value="address">By address ID</option>
        </select>
        {scope === "subnet" && (
          <input
            className="tool-input"
            type="number"
            placeholder="Subnet ID"
            value={subnetId}
            onChange={(e) => setSubnetId(e.target.value)}
          />
        )}
        {scope === "address" && (
          <input
            className="tool-input"
            type="number"
            placeholder="Address ID"
            value={addressId}
            onChange={(e) => setAddressId(e.target.value)}
          />
        )}
        <button
          className="tool-btn"
          onClick={loadAuditLog}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      {loading && <div className="tool-empty">Loading audit log…</div>}
      {error && <div className="tool-error">{error}</div>}
      {!loading && !error && entries.length === 0 && (
        <div className="tool-empty">No audit entries found</div>
      )}

      {!loading && !error && entries.length > 0 && (
        <div className="audit-timeline">
          {entries.map((entry) => {
            const style = CHANGE_TYPE_STYLES[entry.changeType] || {
              color: "#888",
              bg: "#333",
              label: entry.changeType,
            };
            const isExpanded = expandedId === entry.id;

            return (
              <div key={entry.id} className="audit-entry">
                <div
                  className="audit-entry-header"
                  onClick={() => toggleExpand(entry.id)}
                >
                  <span
                    className="audit-type-badge"
                    style={{ backgroundColor: style.bg, color: style.color }}
                  >
                    {style.label}
                  </span>
                  <span className="audit-ip">{entry.ipAddress || "—"}</span>
                  <span className="audit-desc">{entry.description || "—"}</span>
                  <span className="audit-user">
                    {entry.username || "system"}
                  </span>
                  <span className="audit-time">
                    {formatTimestamp(entry.createdAt)}
                  </span>
                  <span className="audit-expand">
                    {isExpanded ? "▼" : "▶"}
                  </span>
                </div>
                {isExpanded && (
                  <div className="audit-entry-body">
                    {entry.subnetCidr && (
                      <div className="audit-meta">
                        <strong>Subnet:</strong> {entry.subnetCidr}
                      </div>
                    )}
                    <DiffView
                      oldVal={entry.oldValue}
                      newVal={entry.newValue}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
