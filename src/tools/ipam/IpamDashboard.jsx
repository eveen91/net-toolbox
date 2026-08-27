import React, { useEffect, useState } from "react";
import { getIpamDashboard } from "./api.js";
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

  const loadDashboard = async () => {
    try {
      const result = await getIpamDashboard();
      setEntries(result);
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

  return (
    <div className="tool-table-wrap ip-table-wrap-full">
      <table className="tool-table">
        <thead>
          <tr>
            <th className="ip-sortable-th" onClick={() => handleSort("cidr")}>
              CIDR{sortIndicator("cidr")}
            </th>
            <th>Description</th>
            <th>VLAN</th>
            <th className="ip-sortable-th" onClick={() => handleSort("usedCount")}>
              Used / Free / Reserved{sortIndicator("usedCount")}
            </th>
            <th>Tags</th>
            <th className="ip-sortable-th" onClick={() => handleSort("lastScannedAt")}>
              Last scanned{sortIndicator("lastScannedAt")}
            </th>
            <th>Since last scan</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sortedEntries.map((e) => {
            const entryTags = tags.filter((t) => t.subnetIds?.includes(e.id));
            return (
              <tr key={e.id} className={e.lastScannedAt ? "" : "ip-dashboard-unscanned"}>
                <td className="ip-subnet-cidr">{e.cidr}</td>
                <td>{e.description || "—"}</td>
                <td>{formatVlan(e.vlan)}</td>
                <td>
                  {e.usedCount} used · {e.freeCount} free · {e.reservedCount} reserved
                </td>
                <td>
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
                <td>{e.lastScannedAt ? formatTimestamp(e.lastScannedAt) : "never"}</td>
                <td>
                  {e.lastScannedAt
                    ? `${e.lastScanNewlyUsed ?? 0} new · ${e.lastScanWentQuiet ?? 0} quiet · ${e.lastScanHostnameChanged ?? 0} renamed`
                    : "—"}
                </td>
                <td>
                  <button
                    className="tool-btn tool-btn-ghost ip-row-btn"
                    onClick={() => onSelectSubnet(e.id)}
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
  );
}
