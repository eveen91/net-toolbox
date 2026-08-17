import React, { useEffect, useState } from "react";
import { getMisplacedAddresses, moveAddress } from "./api.js";

export default function ResubnetReview({ onMoved }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dismissedIds, setDismissedIds] = useState(() => new Set());
  const [movingId, setMovingId] = useState(null);
  const [rowErrors, setRowErrors] = useState({});

  const loadEntries = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMisplacedAddresses();
      setEntries(result);
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

  if (loading) return <div className="tool-empty">Loading misplaced addresses…</div>;
  if (error) return <div className="tool-error">{error}</div>;
  if (visibleEntries.length === 0) return <div className="tool-empty">Nothing to review</div>;

  const handleMove = async (entry) => {
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[entry.addressId];
      return next;
    });
    setMovingId(entry.addressId);
    try {
      await moveAddress(entry.currentSubnetId, entry.addressId, entry.proposedSubnetId);
      setEntries((prev) => prev.filter((e) => e.addressId !== entry.addressId));
      onMoved?.();
    } catch (e) {
      setRowErrors((prev) => ({ ...prev, [entry.addressId]: e.message }));
    } finally {
      setMovingId(null);
    }
  };

  const handleDismiss = (entry) => {
    setDismissedIds((prev) => new Set(prev).add(entry.addressId));
  };

  return (
    <div className="tool-table-wrap ip-table-wrap-full">
      <table className="tool-table">
        <thead>
          <tr>
            <th>Address</th>
            <th>Hostname</th>
            <th>Status</th>
            <th>Current subnet</th>
            <th>Proposed subnet</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {visibleEntries.map((e) => (
            <tr key={e.addressId}>
              <td className="ip-subnet-cidr">
                {e.address}
                {rowErrors[e.addressId] && (
                  <div className="tool-error">{rowErrors[e.addressId]}</div>
                )}
              </td>
              <td>{e.hostname || "—"}</td>
              <td>{e.status}</td>
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
                  onClick={() => handleDismiss(e)}
                >
                  Dismiss
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}