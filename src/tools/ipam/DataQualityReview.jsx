import React, { useEffect, useState } from "react";
import { getDataQualityViolations, moveAddress, muteDataQualityViolation } from "./api.js";

const RULE_LABELS = {
  utilization_80: "Utilization ≥80%",
  utilization_90: "Utilization ≥90%",
  never_scanned: "Never scanned",
  stale_scan: "Stale scan",
  missing_owner_team: "Missing owner/team",
  duplicate_hostname: "Duplicate hostname",
  static_in_dhcp: "Static IP in DHCP",
  misplaced_subnet: "Wrong subnet",
  critical_subnet_metadata: "Critical subnet metadata",
};

export default function DataQualityReview({ onSelectSubnet, onChanged, canWrite = true }) {
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [rule, setRule] = useState("");
  const [severity, setSeverity] = useState("");
  const [actionId, setActionId] = useState(null);
  const [rowErrors, setRowErrors] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      setViolations(await getDataQualityViolations());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const dismiss = async (violation) => {
    const reason = window.prompt("Reason for muting this rule:");
    if (!reason?.trim()) return;
    const expiresAt = window.prompt("Expiry (ISO-8601, leave blank for no expiry):") || null;
    setActionId(violation.id);
    try {
      await muteDataQualityViolation(violation.id, reason, expiresAt);
      setViolations((items) => items.filter((item) => item.id !== violation.id));
    } catch (e) {
      setRowErrors((items) => ({ ...items, [violation.id]: e.message }));
    } finally {
      setActionId(null);
    }
  };

  const move = async (violation) => {
    setActionId(violation.id);
    try {
      await moveAddress(violation.subnetId, violation.addressId, violation.proposedSubnetId);
      setViolations((items) => items.filter((item) => item.id !== violation.id));
      onChanged?.();
    } catch (e) {
      setRowErrors((items) => ({ ...items, [violation.id]: e.message }));
    } finally {
      setActionId(null);
    }
  };

  const filtered = violations.filter((item) => (!rule || item.rule === rule) && (!severity || item.severity === severity));
  const rules = [...new Set(violations.map((item) => item.rule))];

  if (loading) return <div className="tool-empty">Loading data-quality violations…</div>;
  if (error) return <div className="tool-error">{error}</div>;

  return (
    <div>
      <div className="ip-quality-toolbar">
        <strong>{violations.length} open issue{violations.length === 1 ? "" : "s"}</strong>
        <select className="tool-input ip-row-input" value={rule} onChange={(event) => setRule(event.target.value)}>
          <option value="">All rules</option>
          {rules.map((value) => <option key={value} value={value}>{RULE_LABELS[value] || value}</option>)}
        </select>
        <select className="tool-input ip-row-input" value={severity} onChange={(event) => setSeverity(event.target.value)}>
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
        </select>
        <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={load}>Refresh</button>
      </div>
      {filtered.length === 0 ? <div className="tool-empty">No matching data-quality violations.</div> : (
        <div className="tool-table-wrap ip-table-wrap-full">
          <table className="tool-table">
            <thead><tr><th>Severity</th><th>Rule</th><th>Resource</th><th>Issue</th><th>Actions</th></tr></thead>
            <tbody>{filtered.map((item) => (
              <tr key={item.id}>
                <td><span className={`tool-badge ${item.severity === "critical" ? "tool-badge-danger" : "tool-badge-default"}`}>{item.severity}</span></td>
                <td>{RULE_LABELS[item.rule] || item.rule}</td>
                <td>{item.address || item.subnetCidr || "—"}</td>
                <td>{item.message}{rowErrors[item.id] && <div className="tool-error">{rowErrors[item.id]}</div>}</td>
                <td className="ip-actions-cell"><div className="ip-actions-inner">
                  {canWrite && item.rule === "misplaced_subnet" && <button className="tool-btn tool-btn-primary ip-row-btn" disabled={actionId === item.id} onClick={() => move(item)}>{actionId === item.id ? "Moving…" : "Move"}</button>}
                  <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => onSelectSubnet?.(item.subnetId)}>Open</button>
                  {canWrite && <button className="tool-btn tool-btn-ghost ip-row-btn" disabled={actionId === item.id} onClick={() => dismiss(item)}>Mute</button>}
                </div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
