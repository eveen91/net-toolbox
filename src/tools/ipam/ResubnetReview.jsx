import React, { useEffect, useState } from "react";
import {
  getMisplacedAddresses,
  getMisplacedDhcpPools,
  moveAddress,
  moveDhcpPool,
} from "./api.js";

export default function ResubnetReview({ onMoved }) {
  const [entries, setEntries] = useState([]);
  const [pools, setPools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dismissedIds, setDismissedIds] = useState(() => new Set());
  const [movingId, setMovingId] = useState(null);
  const [rowErrors, setRowErrors] = useState({});

  const loadEntries = async () => {
    setLoading(true);
    setError(null);
    try {
      const [addrResult, poolResult] = await Promise.all([
        getMisplacedAddresses(),
        getMisplacedDhcpPools(),
      ]);
      setEntries(addrResult);
      setPools(poolResult);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEntries();
  }, []);

  const visibleEntries = entries.filter((e) => !dismissedIds.has(e.addressId));
  const visiblePools = pools.filter((p) => !dismissedIds.has(`pool-${p.poolId}`));

  if (loading) return <div className="tool-empty">Loading misplaced resources…</div>;
  if (error) return <div className="tool-error">{error}</div>;
  if (visibleEntries.length === 0 && visiblePools.length === 0)
    return <div className="tool-empty">Nothing to review</div>;

  const handleMove = async (entry) => {
    const key = entry.addressId;
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setMovingId(key);
    try {
      await moveAddress(entry.currentSubnetId, entry.addressId, entry.proposedSubnetId);
      setEntries((prev) => prev.filter((e) => e.addressId !== entry.addressId));
      onMoved?.();
    } catch (e) {
      setRowErrors((prev) => ({ ...prev, [key]: e.message }));
    } finally {
      setMovingId(null);
    }
  };

  const handleMovePool = async (pool) => {
    const key = `pool-${pool.poolId}`;
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setMovingId(key);
    try {
      await moveDhcpPool(pool.currentSubnetId, pool.poolId, pool.proposedSubnetId);
      setPools((prev) => prev.filter((p) => p.poolId !== pool.poolId));
      onMoved?.();
    } catch (e) {
      setRowErrors((prev) => ({ ...prev, [key]: e.message }));
    } finally {
      setMovingId(null);
    }
  };

  const handleDismiss = (key) => {
    setDismissedIds((prev) => new Set(prev).add(key));
  };

  return (
    <div className="tool-table-wrap ip-table-wrap-full">
      <table className="tool-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Resource</th>
            <th>Detail</th>
            <th>Current subnet</th>
            <th>Proposed subnet</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {visibleEntries.map((e) => (
            <tr key={e.addressId}>
              <td>
                <span className="tool-badge tool-badge-default">Address</span>
              </td>
              <td className="ip-subnet-cidr">
                {e.address}
                {rowErrors[e.addressId] && (
                  <div className="tool-error">{rowErrors[e.addressId]}</div>
                )}
              </td>
              <td>{e.hostname ? `${e.hostname} · ${e.status}` : e.status}</td>
              <td>{e.currentSubnetCidr}</td>
              <td>{e.proposedSubnetCidr}</td>
              <td>
                <button
                  className="tool-btn tool-btn-primary ip-row-btn"
                  disabled={movingId === e.addressId}
                  onClick={() => handleMove(e)}
                >
                  {movingId === e.addressId ? "Moving…" : "Move"}
                </button>
                <button
                  className="tool-btn tool-btn-ghost ip-row-btn"
                  onClick={() => handleDismiss(e.addressId)}
                >
                  Dismiss
                </button>
              </td>
            </tr>
          ))}
          {visiblePools.map((p) => {
            const key = `pool-${p.poolId}`;
            return (
              <tr key={key}>
                <td>
                  <span className="tool-badge tool-badge-accent">DHCP Pool</span>
                </td>
                <td className="ip-subnet-cidr">
                  {p.startIp || p.start_ip} – {p.endIp || p.end_ip}
                  {rowErrors[key] && (
                    <div className="tool-error">{rowErrors[key]}</div>
                  )}
                </td>
                <td>{p.name || p.description || "—"}</td>
                <td>{p.currentSubnetCidr}</td>
                <td>{p.proposedSubnetCidr}</td>
                <td>
                  <button
                    className="tool-btn tool-btn-primary ip-row-btn"
                    disabled={movingId === key}
                    onClick={() => handleMovePool(p)}
                  >
                    {movingId === key ? "Moving…" : "Move"}
                  </button>
                  <button
                    className="tool-btn tool-btn-ghost ip-row-btn"
                    onClick={() => handleDismiss(key)}
                  >
                    Dismiss
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