import React, { useState, useEffect } from "react";
import {
  getDhcpPools,
  createDhcpPool,
  updateDhcpPool,
  deleteDhcpPool,
  moveDhcpPool,
  bulkMoveDhcpPools,
} from "./api.js";

function isValidIPv4(ip) {
  const parts = ip.split(".");
  if (parts.length !== 4) return false;
  return parts.every((part) => {
    const num = Number(part);
    return !isNaN(num) && num >= 0 && num <= 255 && String(num) === part;
  });
}

function ipToNumber(ip) {
  return ip.split(".").reduce((acc, octet) => (acc << 8) + parseInt(octet, 10), 0) >>> 0;
}

export default function DhcpPoolManager({ subnetId, subnets, onPoolsChanged }) {
  const [pools, setPools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPool, setEditingPool] = useState(null);
  const [startIp, setStartIp] = useState("");
  const [endIp, setEndIp] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [targetSubnetId, setTargetSubnetId] = useState("");
  const [moving, setMoving] = useState(false);

  useEffect(() => {
    loadPools();
    setSelectedIds(new Set());
    setTargetSubnetId("");
  }, [subnetId]);

  const loadPools = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await getDhcpPools(subnetId);
      setPools(data);
      onPoolsChanged?.(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const openAddModal = () => {
    setEditingPool(null);
    setStartIp("");
    setEndIp("");
    setName("");
    setDescription("");
    setModalOpen(true);
  };

  const openEditModal = (pool) => {
    setEditingPool(pool);
    setStartIp(pool.start_ip || pool.startIp || "");
    setEndIp(pool.end_ip || pool.endIp || "");
    setName(pool.name || "");
    setDescription(pool.description || "");
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingPool(null);
    setStartIp("");
    setEndIp("");
    setName("");
    setDescription("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!isValidIPv4(startIp)) {
      setError("Invalid start IP address");
      return;
    }
    if (!isValidIPv4(endIp)) {
      setError("Invalid end IP address");
      return;
    }
    if (ipToNumber(startIp) > ipToNumber(endIp)) {
      setError("Start IP must be less than or equal to end IP");
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        start_ip: startIp.trim(),
        end_ip: endIp.trim(),
        name: name.trim() || null,
        description: description.trim() || null,
      };
      if (editingPool) {
        await updateDhcpPool(subnetId, editingPool.id, payload);
      } else {
        await createDhcpPool(subnetId, payload);
      }
      closeModal();
      await loadPools();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (poolId) => {
    if (!confirm("Delete this DHCP pool?")) return;
    setError(null);
    try {
      await deleteDhcpPool(subnetId, poolId);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(poolId);
        return next;
      });
      await loadPools();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleMoveOne = async (pool, destSubnetId) => {
    setError(null);
    setMoving(true);
    try {
      await moveDhcpPool(subnetId, pool.id, Number(destSubnetId));
      await loadPools();
    } catch (e) {
      setError(e.message);
    } finally {
      setMoving(false);
    }
  };

  const handleBulkMove = async () => {
    if (!targetSubnetId || selectedIds.size === 0) return;
    setError(null);
    setMoving(true);
    try {
      await bulkMoveDhcpPools(Array.from(selectedIds), Number(targetSubnetId));
      setSelectedIds(new Set());
      setTargetSubnetId("");
      await loadPools();
    } catch (e) {
      setError(e.message);
    } finally {
      setMoving(false);
    }
  };

  const toggleSelected = (poolId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(poolId)) next.delete(poolId);
      else next.add(poolId);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === pools.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(pools.map((p) => p.id)));
    }
  };

  const moveTargets = (subnets || []).filter((s) => s.id !== subnetId);

  if (loading) {
    return <div className="tool-empty">Loading pools...</div>;
  }

  return (
    <div>
      <div className="ip-add-row" style={{ alignItems: "center" }}>
        <button type="button" className="tool-btn tool-btn-primary" onClick={openAddModal}>
          + Add Pool
        </button>
        {selectedIds.size > 0 && moveTargets.length > 0 && (
          <>
            <select
              className="tool-input"
              style={{ width: "180px" }}
              value={targetSubnetId}
              onChange={(e) => setTargetSubnetId(e.target.value)}
            >
              <option value="">Move to subnet…</option>
              {moveTargets.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.cidr}
                  {s.vlan ? ` (VLAN ${s.vlan})` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="tool-btn tool-btn-ghost"
              onClick={handleBulkMove}
              disabled={moving || !targetSubnetId}
            >
              {moving ? "Moving…" : `Move ${selectedIds.size}`}
            </button>
            <button
              type="button"
              className="tool-btn tool-btn-ghost"
              onClick={() => setSelectedIds(new Set())}
            >
              Clear selection
            </button>
          </>
        )}
      </div>

      {error && <div className="tool-error">{error}</div>}

      {pools.length === 0 && !error && (
        <div className="tool-empty">No DHCP pools defined</div>
      )}

      {pools.length > 0 && (
        <div className="tool-table-wrap ip-table-wrap-full">
        <table className="tool-table">
          <thead>
            <tr>
              <th style={{ width: "32px" }}>
                <input
                  type="checkbox"
                  checked={pools.length > 0 && selectedIds.size === pools.length}
                  onChange={toggleAll}
                />
              </th>
              <th>Name</th>
              <th>Range</th>
              <th>Description</th>
              <th className="ip-actions-cell">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pools.map((pool) => (
              <tr key={pool.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(pool.id)}
                    onChange={() => toggleSelected(pool.id)}
                  />
                </td>
                <td>{pool.name || <span className="tool-muted">Unnamed</span>}</td>
                <td>
                  <span className="ip-mono">{pool.start_ip || pool.startIp}</span>
                  {" – "}
                  <span className="ip-mono">{pool.end_ip || pool.endIp}</span>
                </td>
                <td>{pool.description || "—"}</td>
                <td className="ip-actions-cell">
                  <div className="ip-actions-inner">
                    <button
                      type="button"
                      className="tool-btn tool-btn-ghost ip-row-btn"
                      onClick={() => openEditModal(pool)}
                    >
                      Edit
                    </button>
                    {moveTargets.length > 0 && (
                      <select
                        className="tool-btn tool-btn-ghost ip-row-btn"
                        value=""
                        onChange={(e) => {
                          if (e.target.value) handleMoveOne(pool, e.target.value);
                        }}
                        disabled={moving}
                      >
                        <option value="">Move…</option>
                        {moveTargets.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.cidr}
                            {s.vlan ? ` (VLAN ${s.vlan})` : ""}
                          </option>
                        ))}
                      </select>
                    )}
                    <button
                      type="button"
                      className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger"
                      onClick={() => handleDelete(pool.id)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      {modalOpen && (
        <div className="tool-modal-overlay" onClick={closeModal}>
          <div className="tool-modal" onClick={(e) => e.stopPropagation()}>
            <div className="tool-modal-header">
              <h3>{editingPool ? "Edit DHCP Pool" : "Add DHCP Pool"}</h3>
              <button type="button" className="tool-modal-close" onClick={closeModal}>
                ×
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Start IP</span>
                </div>
                <input
                  autoFocus
                  className="tool-input"
                  placeholder="192.168.1.100"
                  value={startIp}
                  onChange={(e) => setStartIp(e.target.value)}
                  required
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>End IP</span>
                </div>
                <input
                  className="tool-input"
                  placeholder="192.168.1.200"
                  value={endIp}
                  onChange={(e) => setEndIp(e.target.value)}
                  required
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Name <span className="tool-hint">optional</span></span>
                </div>
                <input
                  className="tool-input"
                  placeholder="e.g. Guest DHCP"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Description <span className="tool-hint">optional</span></span>
                </div>
                <input
                  className="tool-input"
                  placeholder="e.g. Guest network range"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="tool-actions">
                <button
                  type="submit"
                  className="tool-btn tool-btn-primary"
                  disabled={submitting || !startIp.trim() || !endIp.trim()}
                >
                  {submitting
                    ? editingPool ? "Saving…" : "Adding…"
                    : editingPool ? "Save" : "Add Pool"}
                </button>
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost"
                  onClick={closeModal}
                  disabled={submitting}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
