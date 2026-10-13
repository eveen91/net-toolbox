import React, { useEffect, useState } from "react";
import { getDataQualityViolations, getIpamDashboard } from "./api.js";
import { formatTimestamp, formatVlan } from "./logic.js";
import TagBadge from "./TagBadge.jsx";

/**
 * Cross-subnet overview: one row per subnet showing utilization and
 * last-scan freshness, so the user doesn't have to open each subnet
 * individually to see what needs attention.
 *
 * Follows the same focused-file pattern as SubnetSearch.jsx and
 * AddSubnetForm.jsx — this file owns its own data fetching and is
 * imported into Ipam.jsx rather than folded into that file.
 */
export default function IpamDashboard({ onSelectSubnet, tags = [] }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortBy, setSortBy] = useState("cidr");
  const [sortDir, setSortDir] = useState("asc");
  const [issueCount, setIssueCount] = useState(0);

  const loadDashboard = async () => {
    try {
      const [result, violations] = await Promise.all([getIpamDashboard(), getDataQualityViolations()]);
      setEntries(result);
      setIssueCount(violations.length);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
  };

  if (loading) return <div className="tool-empty">Loading dashboard…</div>;
  if (error) return <div className="tool-error">{error}</div>;
  if (entries.length === 0) return <div className="tool-empty">No subnets recorded yet.</div>;

  const compareEntries = (a, b) => {
    if (sortBy === "cidr" || sortBy === "description") {
      const av = a[sortBy] || "";
      const bv = b[sortBy] || "";
      return av.localeCompare(bv);
    }
    if (sortBy === "lastScannedAt") {
      if (a.lastScannedAt === null && b.lastScannedAt === null) return 0;
      if (a.lastScannedAt === null) return -1;
      if (b.lastScannedAt === null) return 1;
      return a.lastScannedAt.localeCompare(b.lastScannedAt);
    }
    if (sortBy === "usedCount") {
      return a.usedCount - b.usedCount;
    }
    return 0;
  };

  const sortedEntries = [...entries].sort(compareEntries);
  if (sortDir === "desc") sortedEntries.reverse();

  const sortIndicator = (column) => (sortBy === column ? (sortDir === "asc" ? " ▲" : " ▼") : "");
  const ariaSort = (column) => (sortBy === column ? (sortDir === "asc" ? "ascending" : "descending") : "none");
  const SortButton = ({ column, children }) => (
    <button
      type="button"
      className="ip-address-sort"
      onClick={() => handleSort(column)}
      aria-label={`Sort by ${children}${sortBy === column ? `, currently ${sortDir === "asc" ? "ascending" : "descending"}` : ""}`}
    >
      {children}<span aria-hidden="true">{sortIndicator(column)}</span>
    </button>
  );

  return (
    <>
      <div className="ip-quality-summary">
        <strong>Data quality</strong>
        <span className={issueCount ? "tool-badge tool-badge-danger" : "tool-badge tool-badge-default"}>{issueCount} open issue{issueCount === 1 ? "" : "s"}</span>
      </div>
      <div className="tool-table-wrap ip-table-wrap-full ip-dashboard-table-wrap">
      <table className="tool-table ip-dashboard-table">
        <thead>
          <tr>
            <th aria-sort={ariaSort("cidr")}><SortButton column="cidr">CIDR</SortButton></th>
            <th aria-sort={ariaSort("description")}><SortButton column="description">Description</SortButton></th>
            <th>VLAN</th>
            <th aria-sort={ariaSort("usedCount")}><SortButton column="usedCount">Used / Free / Reserved</SortButton></th>
            <th>Tags</th>
            <th aria-sort={ariaSort("lastScannedAt")}><SortButton column="lastScannedAt">Last scanned</SortButton></th>
            <th>Since last scan</th>
            <th><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {sortedEntries.map((e) => {
            const entryTags = tags.filter((t) => t.subnetIds?.includes(e.id));
            return (
              <tr key={e.id} className={e.lastScannedAt ? "" : "ip-dashboard-unscanned"}>
                <td data-label="CIDR" className="ip-subnet-cidr">{e.cidr}</td>
                <td data-label="Description">{e.description || "—"}</td>
                <td data-label="VLAN">{formatVlan(e.vlan)}</td>
                <td data-label="Usage">
                  {e.usedCount} used · {e.freeCount} free · {e.reservedCount} reserved
                </td>
                <td data-label="Tags">
                  {entryTags.length > 0 ? (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {entryTags.map((tag) => (
                        <TagBadge key={tag.id} tag={tag} size="sm" />
                      ))}
                    </div>
                  ) : (
                    <span className="tool-hint">—</span>
                  )}
                </td>
                <td data-label="Last scanned">{e.lastScannedAt ? formatTimestamp(e.lastScannedAt) : "never"}</td>
                <td data-label="Since last scan">
                  {e.lastScannedAt
                    ? `${e.lastScanNewlyUsed ?? 0} new · ${e.lastScanWentQuiet ?? 0} quiet · ${e.lastScanHostnameChanged ?? 0} renamed`
                    : "—"}
                </td>
                <td data-label="Actions" className="ip-actions-cell">
                  <button
                    className="tool-btn tool-btn-ghost ip-row-btn"
                    onClick={() => onSelectSubnet(e.id)}
                    aria-label={`View subnet ${e.cidr}`}
                  >
                    View
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </>
  );
}
