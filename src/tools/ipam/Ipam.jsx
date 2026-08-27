import React, { useEffect, useState, useRef } from "react";
import "./ipam.css";
import SubnetSearch from "./SubnetSearch.jsx";
import AddSubnetForm from "./AddSubnetForm.jsx";
import IpamDashboard from "./IpamDashboard.jsx";
import ResubnetReview from "./ResubnetReview.jsx";
import DhcpPoolManager from "./DhcpPoolManager.jsx";
import SubnetHeatmap from "./SubnetHeatmap.jsx";
import TagSelector from "./TagSelector.jsx";
import TagFilterBar from "./TagFilterBar.jsx";
import TagBadge from "./TagBadge.jsx";
import {
  formatVlan,
  formatTimestamp,
  utilizationPercent,
  STATUS_LABELS,
  ancestorChain,
  addressesToCsv,
} from "./logic.js";
import {
  listSubnets,
  getSubnet,
  updateSubnet,
  deleteSubnet,
  addAddress,
  updateAddress,
  deleteAddress,
  bulkUpdateAddresses,
  bulkDeleteAddresses,
  bulkMoveAddresses,
  rescanAddress,
  autodiscoverSubnet,
  startAutodiscoverJob,
  autodiscoverStreamUrl,
  getActiveAutodiscoverJob,
  listSubnetScans,
  listScanExcludes,
  addScanExclude,
  removeScanExclude,
  getIpamSettings,
  updateIpamSettings,
  getNextAvailableIp,
  fetchTags,
  createTag,
  deleteTag,
  fetchSubnetTags,
  addSubnetTag,
  removeSubnetTag,
  fetchAddressTags,
  addAddressTag,
  removeAddressTag,
} from "./api.js";

const STATUS_PILL_CLASS = {
  used: "tool-pill-muted",
  free: "tool-pill-ok",
  reserved: "tool-pill-warn",
};

function UtilizationBar({ subnet }) {
  const total = subnet.totalAddresses || 1;
  const usedPct = Math.min(100, (subnet.usedCount / total) * 100);
  const reservedPct = Math.min(100 - usedPct, (subnet.reservedCount / total) * 100);
  const freePct = Math.min(100 - usedPct - reservedPct, (subnet.freeCount / total) * 100);
  return (
    <div className="ip-util-bar" title={`${utilizationPercent(subnet)}% allocated (used + reserved)`}>
      <div className="ip-util-seg ip-util-used" style={{ width: `${usedPct}%` }} />
      <div className="ip-util-seg ip-util-reserved" style={{ width: `${reservedPct}%` }} />
      <div className="ip-util-seg ip-util-free" style={{ width: `${freePct}%` }} />
    </div>
  );
}

/** Row for one recorded address: view mode + an inline edit mode, plus a delete confirm step. */
const MACHINE_TYPE_LABELS = { physical: "Physical", vm: "VM" };
const ENVIRONMENT_LABELS = { prod: "Prod", test: "Test", dev: "Dev" };

function AddressRow({ subnetId, addr, selected, highlighted, onToggleSelect, onUpdated, onError, tags, addressTagIds = {}, onAddressTagChange }) {
  const rowRef = useRef(null);
  useEffect(() => {
    if (highlighted && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlighted]);
  const currentTags = addressTagIds[addr.id] || [];
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [draft, setDraft] = useState({
    address: addr.address,
    status: addr.status,
    hostname: addr.hostname || "",
    description: addr.description || "",
    team: addr.team || "",
    machineType: addr.machineType || "",
    vmCluster: addr.vmCluster || "",
    environment: addr.environment || "",
    locked: addr.locked || false,
  });
  const [formError, setFormError] = useState(null);

  const startEdit = () => {
    setDraft({
      address: addr.address,
      status: addr.status,
      hostname: addr.hostname || "",
      description: addr.description || "",
      team: addr.team || "",
      machineType: addr.machineType || "",
      vmCluster: addr.vmCluster || "",
      environment: addr.environment || "",
      locked: addr.locked || false,
    });
    setModalOpen(true);
    setFormError(null);
  };

  const closeModal = () => {
    setModalOpen(false);
    setFormError(null);
  };

  const save = async () => {
    setFormError(null);
    setSaving(true);
    try {
      const updated = await updateAddress(
        subnetId,
        addr.id,
        draft.address.trim(),
        draft.status,
        draft.hostname.trim() || null,
        draft.description.trim() || null,
        draft.team.trim() || null,
        draft.machineType || null,
        draft.machineType === "vm" ? draft.vmCluster.trim() || null : null,
        draft.environment || null,
        draft.locked
      );
      onUpdated(updated);
      closeModal();
    } catch (e) {
      setFormError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setSaving(true);
    try {
      const updated = await deleteAddress(subnetId, addr.id);
      onUpdated(updated);
    } catch (e) {
      setFormError(e.message);
      setSaving(false);
    }
  };

  const rescan = async () => {
    setRescanning(true);
    try {
      const updated = await rescanAddress(subnetId, addr.id);
      onUpdated(updated);
    } catch (e) {
      setFormError(e.message);
    } finally {
      setRescanning(false);
    }
  };

  return (
    <>
      <tr ref={rowRef} className={highlighted ? "ip-row-highlighted" : ""}>
        <td>
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(addr.id)}
          />
        </td>
        <td className="ip-mono">{addr.address}</td>
        <td>
          <span className={`tool-pill ${STATUS_PILL_CLASS[addr.status]}`}>{STATUS_LABELS[addr.status]}</span>
        </td>
        <td>{addr.hostname || "—"}</td>
        <td>{addr.description || "—"}</td>
        <td>{addr.team || "—"}</td>
        <td>{addr.machineType ? MACHINE_TYPE_LABELS[addr.machineType] : "—"}</td>
        <td>{addr.machineType === "vm" ? addr.vmCluster || "—" : "—"}</td>
        <td>{addr.environment ? ENVIRONMENT_LABELS[addr.environment] : "—"}</td>
        <td>{addr.locked ? "🔒" : "—"}</td>
        <td className="ip-actions-cell">
          <div className="ip-actions-inner">
            {tags && (
              <TagSelector
                value={currentTags.map((t) => t.id)}
                onChange={(newIds) => onAddressTagChange(addr.id, newIds)}
                allTags={tags}
                placeholder="+ Tag"
              />
            )}
            {confirmingDelete ? (
              <>
                <button className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger" onClick={remove} disabled={saving}>
                  {saving ? "…" : "Confirm"}
                </button>
                <button
                  className="tool-btn tool-btn-ghost ip-row-btn"
                  onClick={() => setConfirmingDelete(false)}
                  disabled={saving}
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                {addr.status !== "reserved" && (
                  <button
                    className="tool-btn tool-btn-ghost ip-row-btn"
                    onClick={rescan}
                    disabled={rescanning}
                  >
                    {rescanning ? "…" : "Rescan"}
                  </button>
                )}
                <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEdit}>
                  Edit
                </button>
                <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setConfirmingDelete(true)}>
                  Delete
                </button>
              </>
            )}
          </div>
        </td>
      </tr>

      {modalOpen && (
        <div className="tool-modal-overlay" onClick={closeModal}>
          <div className="tool-modal" onClick={(e) => e.stopPropagation()}>
            <div className="tool-modal-header">
              <h3>Edit Address</h3>
              <button type="button" className="tool-modal-close" onClick={closeModal}>
                ×
              </button>
            </div>
            <form onSubmit={save}>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Address</span>
                </div>
                <input
                  autoFocus
                  className="tool-input"
                  value={draft.address}
                  onChange={(e) => setDraft({ ...draft, address: e.target.value })}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Status</span>
                </div>
                <select
                  className="tool-input"
                  value={draft.status}
                  onChange={(e) => setDraft({ ...draft, status: e.target.value })}
                >
                  {Object.entries(STATUS_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>
                    Hostname <span className="tool-hint">optional</span>
                  </span>
                </div>
                <input
                  className="tool-input"
                  value={draft.hostname}
                  onChange={(e) => setDraft({ ...draft, hostname: e.target.value })}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>
                    Description <span className="tool-hint">optional</span>
                  </span>
                </div>
                <input
                  className="tool-input"
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>
                    Team <span className="tool-hint">optional</span>
                  </span>
                </div>
                <input
                  className="tool-input"
                  value={draft.team}
                  onChange={(e) => setDraft({ ...draft, team: e.target.value })}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Machine type</span>
                </div>
                <select
                  className="tool-input"
                  value={draft.machineType}
                  onChange={(e) => setDraft({ ...draft, machineType: e.target.value, vmCluster: "" })}
                >
                  <option value="">—</option>
                  {Object.entries(MACHINE_TYPE_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>VM cluster</span>
                </div>
                <input
                  className="tool-input"
                  value={draft.vmCluster}
                  onChange={(e) => setDraft({ ...draft, vmCluster: e.target.value })}
                  disabled={draft.machineType !== "vm"}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Environment</span>
                </div>
                <select
                  className="tool-input"
                  value={draft.environment}
                  onChange={(e) => setDraft({ ...draft, environment: e.target.value })}
                >
                  <option value="">—</option>
                  {Object.entries(ENVIRONMENT_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tool-field">
                <label className="tool-hint">
                  <input
                    type="checkbox"
                    checked={draft.locked}
                    onChange={(e) => setDraft({ ...draft, locked: e.target.checked })}
                  />
                  Locked
                </label>
              </div>
              <div className="tool-actions">
                <button
                  className="tool-btn tool-btn-primary"
                  type="submit"
                  disabled={saving || !draft.address.trim()}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost"
                  onClick={closeModal}
                  disabled={saving}
                >
                  Cancel
                </button>
              </div>
              {formError && <div className="tool-error">{formError}</div>}
            </form>
          </div>
        </div>
      )}
    </>
  );
}

function AddAddressForm({ subnetId, onAdded, onError }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [address, setAddress] = useState("");
  const [status, setStatus] = useState("used");
  const [hostname, setHostname] = useState("");
  const [description, setDescription] = useState("");
  const [team, setTeam] = useState("");
  const [machineType, setMachineType] = useState("");
  const [vmCluster, setVmCluster] = useState("");
  const [environment, setEnvironment] = useState("");
  const [locked, setLocked] = useState(false);
  const [adding, setAdding] = useState(false);
  const [findingNext, setFindingNext] = useState(false);
  const [formError, setFormError] = useState(null);

  const reset = () => {
    setAddress("");
    setHostname("");
    setDescription("");
    setStatus("used");
    setTeam("");
    setMachineType("");
    setVmCluster("");
    setEnvironment("");
    setLocked(false);
  };

  const closeModal = () => {
    setModalOpen(false);
    setFormError(null);
    reset();
  };

  const handleFindNextIp = async () => {
    setFormError(null);
    setFindingNext(true);
    try {
      const res = await getNextAvailableIp(subnetId);
      if (res.nextAvailableIp) {
        setAddress(res.nextAvailableIp);
      } else {
        setFormError("No available IP addresses remaining in this subnet.");
      }
    } catch (err) {
      setFormError(err.message);
    } finally {
      setFindingNext(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!address.trim()) return;
    setFormError(null);
    setAdding(true);
    try {
      const updated = await addAddress(
        subnetId,
        address.trim(),
        status,
        hostname.trim() || null,
        description.trim() || null,
        team.trim() || null,
        machineType || null,
        machineType === "vm" ? vmCluster.trim() || null : null,
        environment || null,
        locked
      );
      onAdded(updated);
      reset();
      setModalOpen(false);
    } catch (e2) {
      setFormError(e2.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <>
      <button type="button" className="tool-btn tool-btn-primary" onClick={() => setModalOpen(true)}>
        + Add address
      </button>

      {modalOpen && (
        <div className="tool-modal-overlay" onClick={closeModal}>
          <div className="tool-modal" onClick={(e) => e.stopPropagation()}>
            <div className="tool-modal-header">
              <h3>Add Address</h3>
              <button type="button" className="tool-modal-close" onClick={closeModal}>
                ×
              </button>
            </div>
            <form onSubmit={submit}>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Address</span>
                  <button
                    type="button"
                    className="tool-btn tool-btn-ghost ip-row-btn"
                    onClick={handleFindNextIp}
                    disabled={findingNext}
                    style={{ fontSize: "11px", padding: "2px 6px", textTransform: "none" }}
                  >
                    {findingNext ? "Finding…" : "⚡ Next Available IP"}
                  </button>
                </div>
                <input
                  autoFocus
                  className="tool-input"
                  placeholder="10.0.1.10"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  required
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Status</span>
                </div>
                <select className="tool-input" value={status} onChange={(e) => setStatus(e.target.value)}>
                  {Object.entries(STATUS_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>
                    Hostname <span className="tool-hint">optional</span>
                  </span>
                </div>
                <input
                  className="tool-input"
                  placeholder="hostname (optional)"
                  value={hostname}
                  onChange={(e) => setHostname(e.target.value)}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>
                    Description <span className="tool-hint">optional</span>
                  </span>
                </div>
                <input
                  className="tool-input"
                  placeholder="description (optional)"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>
                    Team <span className="tool-hint">optional</span>
                  </span>
                </div>
                <input
                  className="tool-input"
                  placeholder="team (optional)"
                  value={team}
                  onChange={(e) => setTeam(e.target.value)}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Machine type</span>
                </div>
                <select
                  className="tool-input"
                  value={machineType}
                  onChange={(e) => {
                    setMachineType(e.target.value);
                    setVmCluster("");
                  }}
                >
                  <option value="">Type…</option>
                  {Object.entries(MACHINE_TYPE_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>VM cluster</span>
                </div>
                <input
                  className="tool-input"
                  placeholder="vm cluster"
                  value={vmCluster}
                  onChange={(e) => setVmCluster(e.target.value)}
                  disabled={machineType !== "vm"}
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Environment</span>
                </div>
                <select className="tool-input" value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                  <option value="">Env…</option>
                  {Object.entries(ENVIRONMENT_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tool-field">
                <label className="tool-hint">
                  <input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} />
                  Locked
                </label>
              </div>
               <div className="tool-actions">
                <button className="tool-btn tool-btn-primary" type="submit" disabled={adding || !address.trim()}>
                  {adding ? "Adding…" : "Add address"}
                </button>
                <button type="button" className="tool-btn tool-btn-ghost" onClick={closeModal} disabled={adding}>
                  Cancel
                </button>
              </div>
              {formError && <div className="tool-error">{formError}</div>}
            </form>
          </div>
        </div>
      )}
    </>
  );
}

function BulkEditBar({ subnetId, subnets, selectedIds, onApplied, onMoved, onClear, onError }) {
  const [editOpen, setEditOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [team, setTeam] = useState("");
  const [machineType, setMachineType] = useState("");
  const [vmCluster, setVmCluster] = useState("");
  const [environment, setEnvironment] = useState("");
  const [locked, setLocked] = useState("");
  const [applying, setApplying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [targetSubnetId, setTargetSubnetId] = useState("");
  const [moving, setMoving] = useState(false);

  const moveTargets = subnets.filter((s) => s.id !== subnetId);

  const resetFields = () => {
    setStatus("");
    setTeam("");
    setMachineType("");
    setVmCluster("");
    setEnvironment("");
    setLocked("");
  };

  const closeEdit = () => {
    setEditOpen(false);
    resetFields();
  };

  const submit = async (e) => {
    e.preventDefault();
    onError(null);

    const fields = {};
    if (status !== "") fields.status = status;
    if (team !== "") fields.team = team;
    if (machineType !== "") fields.machineType = machineType;
    if (vmCluster !== "") fields.vmCluster = vmCluster;
    if (environment !== "") fields.environment = environment;
    if (locked === "lock") fields.locked = true;
    else if (locked === "unlock") fields.locked = false;

    if (Object.keys(fields).length === 0) {
      onError("Set at least one field to apply.");
      return;
    }

    setApplying(true);
    try {
      const result = await bulkUpdateAddresses(subnetId, Array.from(selectedIds), fields);
      onApplied(result);
      closeEdit();
    } catch (e) {
      onError(e.message);
    } finally {
      setApplying(false);
    }
  };

  const handleBulkDelete = async () => {
    onError(null);
    const count = selectedIds.size;
    if (
      !window.confirm(
        `Delete ${count} selected address${count === 1 ? "" : "es"}? This cannot be undone.`
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      const result = await bulkDeleteAddresses(subnetId, Array.from(selectedIds));
      onApplied(result);
    } catch (e) {
      onError(e.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleBulkMove = async () => {
    onError(null);
    if (!targetSubnetId) {
      onError("Choose a destination subnet to move to.");
      return;
    }
    setMoving(true);
    try {
      const result = await bulkMoveAddresses(subnetId, Array.from(selectedIds), Number(targetSubnetId));
      onMoved(result);
      setTargetSubnetId("");
      if (result.skipped.length > 0) {
        const names = result.skipped.map((s) => `${s.address || s.addressId}: ${s.reason}`).join("; ");
        onError(
          `Moved ${result.movedCount} of ${result.movedCount + result.skipped.length}. Not moved — ${names}`
        );
      }
    } catch (e) {
      onError(e.message);
    } finally {
      setMoving(false);
    }
  };

  return (
    <div className="ip-bulk-actions">
      <div className="ip-add-row ip-bulk-actions-bar">
        <span className="tool-hint">{selectedIds.size} selected</span>
        <button
          type="button"
          className="tool-btn tool-btn-ghost"
          onClick={() => (editOpen ? closeEdit() : setEditOpen(true))}
          disabled={deleting || moving}
        >
          Edit
        </button>
        <select
          className="tool-input"
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
          disabled={applying || deleting || moving || !targetSubnetId}
        >
          {moving ? "Moving…" : `Move ${selectedIds.size}`}
        </button>
        <button
          type="button"
          className="tool-btn tool-btn-ghost ip-row-btn-danger"
          onClick={handleBulkDelete}
          disabled={applying || deleting || moving}
        >
          {deleting ? "Deleting…" : `Delete ${selectedIds.size}`}
        </button>
        <button type="button" className="tool-btn tool-btn-ghost" onClick={onClear}>
          Clear selection
        </button>
      </div>

      {editOpen && (
        <form className="tool-popover ip-bulk-edit-popover" onSubmit={submit}>
          <div className="tool-field">
            <div className="tool-label">
              <span>Status</span>
            </div>
            <select className="tool-input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Don't change</option>
              {Object.entries(STATUS_LABELS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>Team</span>
            </div>
            <input
              className="tool-input"
              placeholder="team"
              value={team}
              onChange={(e) => setTeam(e.target.value)}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>Machine type</span>
            </div>
            <select
              className="tool-input"
              value={machineType}
              onChange={(e) => setMachineType(e.target.value)}
            >
              <option value="">Don't change</option>
              {Object.entries(MACHINE_TYPE_LABELS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>VM cluster</span>
            </div>
            <input
              className="tool-input"
              placeholder="vm cluster"
              value={vmCluster}
              onChange={(e) => setVmCluster(e.target.value)}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>Environment</span>
            </div>
            <select
              className="tool-input"
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
            >
              <option value="">Don't change</option>
              {Object.entries(ENVIRONMENT_LABELS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="tool-field">
            <div className="tool-label">
              <span>Locked</span>
            </div>
            <select className="tool-input" value={locked} onChange={(e) => setLocked(e.target.value)}>
              <option value="">Don't change</option>
              <option value="lock">Lock</option>
              <option value="unlock">Unlock</option>
            </select>
          </div>
          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" type="submit" disabled={applying}>
              {applying ? "Applying…" : `Apply to ${selectedIds.size}`}
            </button>
            <button type="button" className="tool-btn tool-btn-ghost" onClick={closeEdit} disabled={applying}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function ScanExcludeManager({ subnetId }) {
  const [excludes, setExcludes] = useState([]);
  const [newAddress, setNewAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    setLoading(true);
    (async () => {
      try {
        const data = await listScanExcludes(subnetId);
        setExcludes(data);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [subnetId]);

  const addExclude = async (e) => {
    e.preventDefault();
    if (!newAddress.trim()) return;
    setError(null);
    try {
      const updated = await addScanExclude(subnetId, newAddress.trim());
      setExcludes(updated);
      setNewAddress("");
    } catch (e2) {
      setError(e2.message);
    }
  };

  const removeExclude = async (id) => {
    setError(null);
    try {
      const updated = await removeScanExclude(subnetId, id);
      setExcludes(updated);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="ip-scan-excludes">
      <div className="tool-hint">Scan excludes</div>
      {error && <div className="tool-error">{error}</div>}
      {!loading && excludes.length === 0 && (
        <div className="tool-hint">No excluded addresses.</div>
      )}
      {excludes.length > 0 && (
        <ul className="ip-scan-exclude-list">
          {excludes.map((ex) => (
            <li key={ex.id}>
              <span className="ip-mono">{ex.address}</span>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn"
                onClick={() => removeExclude(ex.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="ip-add-row" onSubmit={addExclude}>
        <input
          className="tool-input"
          style={{ maxWidth: 160 }}
          placeholder="10.0.1.10"
          value={newAddress}
          onChange={(e) => setNewAddress(e.target.value)}
        />
        <button className="tool-btn tool-btn-primary" type="submit" disabled={!newAddress.trim()}>
          Add
        </button>
      </form>
    </div>
  );
}

function SubnetDetail({ subnet, subnets, deleting, onDelete, onDetailUpdated, onSelectSubnet, highlightedAddressId, tags, subnetTagIds = [], onTagChange, addressTagIds = {}, onAddressTagChange }) {
  const [editingHeader, setEditingHeader] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [headerDraft, setHeaderDraft] = useState({
    cidr: subnet.cidr,
    vlan: subnet.vlan ?? "",
    description: subnet.description || "",
  });
  const [headerError, setHeaderError] = useState(null);
  const [headerSaving, setHeaderSaving] = useState(false);
  const [rowError, setRowError] = useState(null);
  const [confirmingScan, setConfirmingScan] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [lastScan, setLastScan] = useState(null);
  const [scanProgress, setScanProgress] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const eventSourceRef = useRef(null);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleSelectAll = () => {
    setSelectedIds((prev) =>
      prev.size === subnet.addresses.length
        ? new Set()
        : new Set(subnet.addresses.map((a) => a.id))
    );
  };

  useEffect(() => {
    if (eventSourceRef.current !== null) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConfirmingDelete(false);
    setEditingHeader(false);
    setHeaderError(null);
    setRowError(null);
    setConfirmingScan(false);
    setScanning(false);
    setScanError(null);
    setScanResult(null);
    setLastScan(null);
    setScanProgress(null);
    setSelectedIds(new Set());

    (async () => {
      try {
        const scans = await listSubnetScans(subnet.id);
        setLastScan(scans.length > 0 ? scans[0] : null);
      } catch {
        // Scan history is a nice-to-have on this screen — if it fails to
        // load, leave lastScan null rather than surfacing another error.
      }
    })();
  }, [subnet.id]);

  const startEditHeader = () => {
    setHeaderDraft({ cidr: subnet.cidr, vlan: subnet.vlan ?? "", description: subnet.description || "" });
    setHeaderError(null);
    setEditingHeader(true);
  };

  const saveHeader = async () => {
    setHeaderError(null);
    setHeaderSaving(true);
    try {
      const vlan = headerDraft.vlan === "" ? null : Number(headerDraft.vlan);
      const updated = await updateSubnet(subnet.id, headerDraft.cidr.trim(), vlan, headerDraft.description.trim() || null);
      onDetailUpdated(updated);
      setEditingHeader(false);
    } catch (e) {
      setHeaderError(e.message);
    } finally {
      setHeaderSaving(false);
    }
  };

  const runAutodiscover = async () => {
    setScanError(null);
    setScanning(true);
    setScanProgress({ completed: 0, total: 0 });
    try {
      const { jobId } = await startAutodiscoverJob(subnet.id);
      const es = new EventSource(autodiscoverStreamUrl(subnet.id, jobId));
      eventSourceRef.current = es;
      let settled = false;
      es.onmessage = async (event) => {
        const payload = JSON.parse(event.data);
        setScanProgress({ completed: payload.completed, total: payload.total });
        if (payload.status === "done") {
          settled = true;
          setScanResult(payload.result);
          es.close();
          eventSourceRef.current = null;
          // payload.result has no finishedAt (only
          // scannedCount/usedCount/freeCount/skippedCount/diff), so
          // hand-building lastScan from it leaves "last scanned" blank.
          // Pull the just-recorded entry from history instead, which has
          // the full record_scan shape including finishedAt.
          try {
            const scans = await listSubnetScans(subnet.id);
            setLastScan(scans.length > 0 ? scans[0] : null);
          } catch {
            // Non-critical — leave lastScan as whatever it was before.
          }
          const refreshed = await getSubnet(subnet.id);
          onDetailUpdated(refreshed);
          setScanning(false);
          setConfirmingScan(false);
          setScanProgress(null);
        } else if (payload.status === "error") {
          settled = true;
          setScanError(payload.error || "Scan failed");
          es.close();
          eventSourceRef.current = null;
          setScanning(false);
          setConfirmingScan(false);
          setScanProgress(null);
        }
      };
      es.onerror = () => {
        if (settled) return;
        setScanError("Lost connection to the scan progress stream.");
        es.close();
        eventSourceRef.current = null;
        setScanning(false);
        setConfirmingScan(false);
        setScanProgress(null);
      };
    } catch (e) {
      setScanError(e.message);
      setScanning(false);
      setConfirmingScan(false);
      setScanProgress(null);
    }
  };

  const downloadCsv = () => {
    const csv = addressesToCsv(subnet.addresses || []);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${subnet.cidr.replace("/", "_")}-addresses.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const unallocated = subnet.totalAddresses - subnet.recordedCount;
  const ancestors = ancestorChain(subnets, subnet.id);
  const children = subnets.filter((s) => s.parentId === subnet.id);

  return (
    <>
      {ancestors.length > 0 && (
        <div className="ip-breadcrumb">
          {ancestors.map((a) => (
            <React.Fragment key={a.id}>
              <button className="ip-breadcrumb-link" onClick={() => onSelectSubnet(a.id)}>
                {a.cidr}
              </button>
              <span className="ip-breadcrumb-sep">›</span>
            </React.Fragment>
          ))}
          <span>{subnet.cidr}</span>
        </div>
      )}
      <div className="tool-section-title">
        {editingHeader ? (
          <span className="ip-header-edit">
            <input
              className="tool-input ip-row-input"
              style={{ maxWidth: 160 }}
              value={headerDraft.cidr}
              onChange={(e) => setHeaderDraft({ ...headerDraft, cidr: e.target.value })}
            />
            <input
              className="tool-input ip-row-input"
              style={{ maxWidth: 100 }}
              placeholder="VLAN"
              value={headerDraft.vlan}
              onChange={(e) => setHeaderDraft({ ...headerDraft, vlan: e.target.value })}
            />
            <input
              className="tool-input ip-row-input"
              placeholder="description"
              value={headerDraft.description}
              onChange={(e) => setHeaderDraft({ ...headerDraft, description: e.target.value })}
            />
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={saveHeader} disabled={headerSaving}>
              {headerSaving ? "Saving…" : "Save"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setEditingHeader(false)}
              disabled={headerSaving}
            >
              Cancel
            </button>
          </span>
        ) : (
          <>
            {subnet.cidr}
            <span className="tool-hint">
              {formatVlan(subnet.vlan)} · {subnet.description || "no description"}
              {children.length > 0
                ? ` · ${children.length} nested subnet${children.length !== 1 ? "s" : ""}`
                : ""}{" "}
              · saved {formatTimestamp(subnet.updatedAt)}
              {lastScan && ` · last scanned ${formatTimestamp(lastScan.finishedAt)}`}
            </span>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEditHeader}>
              Edit
            </button>
          </>
        )}
        {!editingHeader && !confirmingDelete && !confirmingScan && (
          <>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setConfirmingScan(true)}
            >
              Autodiscover
            </button>
            <ScanStatusIcon subnetId={subnet.id} />
          </>
        )}
        {!editingHeader && !confirmingDelete && !confirmingScan && (
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={downloadCsv}
            disabled={!subnet.addresses || subnet.addresses.length === 0}
          >
            Export CSV
          </button>
        )}
        {!editingHeader && !confirmingScan &&
          (confirmingDelete ? (
            <span className="ip-delete-confirm">
              <span className="tool-hint">Delete subnet "{subnet.cidr}"? This can't be undone.</span>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger"
                onClick={() => {
                  setConfirmingDelete(false);
                  onDelete();
                }}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Confirm delete"}
              </button>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              className="tool-btn tool-btn-ghost ip-row-btn ip-delete-subnet-btn"
              onClick={() => setConfirmingDelete(true)}
              disabled={deleting}
            >
              Delete subnet
            </button>
          ))}
        {confirmingScan && (
          <span className="ip-delete-confirm">
            <span className="tool-hint">
              Ping every address in {subnet.cidr}? This may take a while.
            </span>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={runAutodiscover}
              disabled={scanning}
            >
              {scanning
                ? scanProgress && scanProgress.total > 0
                  ? `Scanning ${scanProgress.completed}/${scanProgress.total}…`
                  : "Starting…"
                : "Confirm scan"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setConfirmingScan(false)}
              disabled={scanning}
            >
              Cancel
            </button>
          </span>
        )}
      </div>
      {headerError && <div className="tool-error">{headerError}</div>}
      {scanError && <div className="tool-error">{scanError}</div>}
      {scanResult && !scanError && (
        <div className="tool-hint ip-scan-summary">
          Scanned {scanResult.scannedCount} · {scanResult.usedCount} used ·{" "}
          {scanResult.freeCount} free · {scanResult.skippedCount} skipped
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setScanResult(null)}
          >
            Dismiss
          </button>
          {scanResult.diff &&
            (scanResult.diff.newlyUsed.length > 0 ||
              scanResult.diff.wentQuiet.length > 0 ||
              scanResult.diff.hostnameChanged.length > 0) && (
                <div className="tool-hint ip-scan-diff">
                {scanResult.diff.newlyUsed.length} new · {scanResult.diff.wentQuiet.length} went
                offline · {scanResult.diff.hostnameChanged.length} hostname change
                {scanResult.diff.hostnameChanged.length === 1 ? "" : "s"}
              </div>
            )}
        </div>
      )}

      <UtilizationBar subnet={subnet} />
      <div className="tool-summary">
        <div className="tool-stat">
          <div className="n">{subnet.totalAddresses.toLocaleString()}</div>
          <div className="l">Total addresses</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.usedCount}</div>
          <div className="l">Used</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.reservedCount}</div>
          <div className="l">Reserved</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.freeCount}</div>
          <div className="l">Free (recorded)</div>
        </div>
        <div className="tool-stat">
          <div className="n">{unallocated.toLocaleString()}</div>
          <div className="l">Not recorded</div>
        </div>
      </div>

      {children.length > 0 && (
        <>
          <h3 className="ip-section-sub-title">
            Nested subnets <span className="tool-hint">{children.length}</span>
          </h3>
          <div className="tool-table-wrap ip-table-wrap-full">
            <table className="tool-table">
              <thead>
                <tr>
                  <th>CIDR</th>
                  <th>VLAN</th>
                  <th>Description</th>
                  <th>Recorded</th>
                </tr>
              </thead>
              <tbody>
                {children.map((c) => (
                  <tr key={c.id} className="ip-child-row" onClick={() => onSelectSubnet(c.id)}>
                    <td className="ip-mono">{c.cidr}</td>
                    <td>{formatVlan(c.vlan)}</td>
                    <td>{c.description || "—"}</td>
                    <td>
                      {c.usedCount}u · {c.reservedCount}r · {c.freeCount}f
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <SubnetHeatmap subnet={subnet} subnets={subnets} onCellClick={(ip) => {
        // Find the address in the list and scroll to it
        const addrIndex = subnet.addresses.findIndex((a) => a.address === ip);
        if (addrIndex >= 0) {
          // Highlight and scroll to the address row
          setRowError(null);
          // This will be handled by the highlightedAddressId prop flow
        }
      }} />

      <h3 className="ip-section-sub-title">DHCP Pools</h3>
      <DhcpPoolManager subnetId={subnet.id} subnets={subnets} />

      <h3 className="ip-section-sub-title">Tags</h3>
      <TagSelector
        value={subnetTagIds.map((t) => t.id)}
        onChange={(newIds) => onTagChange(newIds)}
        allTags={tags}
        placeholder="Add tags to this subnet"
      />

      <h3 className="ip-section-sub-title">Addresses</h3>
      {rowError && <div className="tool-error">{rowError}</div>}
      <AddAddressForm subnetId={subnet.id} onAdded={onDetailUpdated} onError={setRowError} />

      {selectedIds.size > 0 && (
        <BulkEditBar
          subnetId={subnet.id}
          subnets={subnets}
          selectedIds={selectedIds}
          onApplied={(updated) => {
            onDetailUpdated(updated);
            setSelectedIds(new Set());
          }}
          onMoved={(result) => {
            onDetailUpdated(result.fromSubnet);
            setSelectedIds(new Set());
          }}
          onClear={() => setSelectedIds(new Set())}
          onError={setRowError}
        />
      )}

      {subnet.addresses.length === 0 ? (
        <div className="tool-empty">No addresses recorded yet — add one above.</div>
      ) : (
        <div className="tool-table-wrap ip-table-wrap-full">
          <table className="tool-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={selectedIds.size > 0 && selectedIds.size === subnet.addresses.length}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th>Address</th>
                <th>Status</th>
                <th>Hostname</th>
                <th>Description</th>
                <th>Team</th>
                <th>Type</th>
                <th>VM Cluster</th>
                <th>Env</th>
                <th>Locked</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {subnet.addresses.map((addr) => (
                <AddressRow
                  key={addr.id}
                  subnetId={subnet.id}
                  addr={addr}
                  selected={selectedIds.has(addr.id)}
                  highlighted={highlightedAddressId === addr.id}
                  onToggleSelect={toggleSelect}
                  onUpdated={onDetailUpdated}
                  onError={setRowError}
                  tags={tags}
                  addressTagIds={addressTagIds}
                  onAddressTagChange={onAddressTagChange}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ScanExcludeManager subnetId={subnet.id} />
    </>
  );
}

function ScanStatusIcon({ subnetId }) {
  const [scanning, setScanning] = useState(false);
  const [addresses, setAddresses] = useState([]);
  const [jobId, setJobId] = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const checkActive = async () => {
      try {
        const result = await getActiveAutodiscoverJob(subnetId);
        if (cancelled) return;
        if (result.jobId != null) {
          if (esRef.current == null) {
            setScanning(true);
            setJobId(result.jobId);
            const es = new EventSource(autodiscoverStreamUrl(subnetId, result.jobId));
            esRef.current = es;
            es.onmessage = (event) => {
              const payload = JSON.parse(event.data);
              setAddresses(payload.addresses || []);
              if (payload.status === "done" || payload.status === "error") {
                es.close();
                esRef.current = null;
                setScanning(false);
              }
            };
          }
        } else {
          setScanning(false);
        }
      } catch {
        // Best-effort polling — a failed check just waits for the next tick.
      }
    };

    checkActive();
    const intervalId = setInterval(checkActive, 5000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      if (esRef.current !== null) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [subnetId]);

  return (
    <span className="ip-scan-status-icon-wrap">
      <span className={`ip-scan-status-icon ${scanning ? "scanning" : "idle"}`} />
      {addresses.length > 0 && (
        <div className="ip-scan-status-popover">
          <div className="tool-hint">
            {scanning ? "Scan in progress" : "Last scan"}
          </div>
          <div className="ip-scan-status-list">
            {addresses.map((a) => (
              <div key={a.address} className="ip-scan-status-row">
                <span className="ip-scan-status-addr">{a.address}</span>
                <span className={`ip-scan-status-badge ${a.status}`}>
                  {a.status === "pending"
                    ? "pending"
                    : a.status === "in_progress"
                    ? "scanning…"
                    : a.alive
                    ? "used"
                    : "free"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}

export default function Ipam() {
  const [subnets, setSubnets] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);
  const [viewMode, setViewMode] = useState("search"); // "search" | "dashboard" | "resubnet"

  const [selectedId, setSelectedId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [highlightedAddressId, setHighlightedAddressId] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const [showSettings, setShowSettings] = useState(false);
  const [scanConcurrencyLimit, setScanConcurrencyLimit] = useState(null);
  const [concurrencyBounds, setConcurrencyBounds] = useState({ min: 1, max: 256 });
  const [settingsError, setSettingsError] = useState(null);
  const [settingsSaving, setSettingsSaving] = useState(false);

  const [allTags, setAllTags] = useState([]);
  const [tagLoading, setTagLoading] = useState(true);
  const [tagError, setTagError] = useState(null);
  const [selectedTagIds, setSelectedTagIds] = useState([]);
  const [subnetTagIds, setSubnetTagIds] = useState({});
  const [addressTagIds, setAddressTagIds] = useState({});

  const refreshList = async () => {
    setListLoading(true);
    setListError(null);
    try {
      const data = await listSubnets();
      setSubnets(data);
    } catch (e) {
      setListError(e.message);
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    refreshList();
  }, []);

  useEffect(() => {
    setTagLoading(true);
    setTagError(null);
    fetchTags()
      .then((tags) => setAllTags(tags))
      .catch((e) => setTagError(e.message))
      .finally(() => setTagLoading(false));
  }, []);

  const loadSubnetTags = async (subnetId) => {
    try {
      const tags = await fetchSubnetTags(subnetId);
      setSubnetTagIds((prev) => ({ ...prev, [subnetId]: tags }));
    } catch {
      // best-effort
    }
  };

  const loadAddressTags = async (addressId) => {
    try {
      const tags = await fetchAddressTags(addressId);
      setAddressTagIds((prev) => ({ ...prev, [addressId]: tags }));
    } catch {
      // best-effort
    }
  };

  const handleTagChange = async (subnetId, newTagIds) => {
    const current = subnetTagIds[subnetId] || [];
    const currentIds = current.map((t) => t.id);
    const toAdd = newTagIds.filter((id) => !currentIds.includes(id));
    const toRemove = currentIds.filter((id) => !newTagIds.includes(id));

    for (const tagId of toAdd) {
      await addSubnetTag(subnetId, tagId);
    }
    for (const tagId of toRemove) {
      await removeSubnetTag(subnetId, tagId);
    }
    await loadSubnetTags(subnetId);
  };

  const handleAddressTagChange = async (addressId, newTagIds) => {
    const current = addressTagIds[addressId] || [];
    const currentIds = current.map((t) => t.id);
    const toAdd = newTagIds.filter((id) => !currentIds.includes(id));
    const toRemove = currentIds.filter((id) => !newTagIds.includes(id));

    for (const tagId of toAdd) {
      await addAddressTag(addressId, tagId);
    }
    for (const tagId of toRemove) {
      await removeAddressTag(addressId, tagId);
    }
    await loadAddressTags(addressId);
  };

  const handleFilterTagRemove = (tagId) => {
    setSelectedTagIds((prev) => prev.filter((id) => id !== tagId));
  };

  const loadSettings = async () => {
    setSettingsError(null);
    try {
      const result = await getIpamSettings();
      setScanConcurrencyLimit(result.scanConcurrencyLimit);
      setConcurrencyBounds({ min: result.scanConcurrencyMin, max: result.scanConcurrencyMax });
    } catch (e) {
      setSettingsError(e.message);
    }
  };

  const openSettings = () => {
    setShowSettings(true);
    loadSettings();
  };

  const saveSettings = async () => {
    setSettingsError(null);
    setSettingsSaving(true);
    try {
      await updateIpamSettings(Number(scanConcurrencyLimit));
      setShowSettings(false);
    } catch (e) {
      setSettingsError(e.message);
    } finally {
      setSettingsSaving(false);
    }
  };

  const selectSubnet = async (id, targetAddressId = null) => {
    setSelectedId(id);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    setHighlightedAddressId(targetAddressId || null);
    try {
      const detail = await getSubnet(id);
      setSelectedDetail(detail);
      // Load tags for this subnet and all its addresses
      await loadSubnetTags(id);
      if (detail && detail.addresses) {
        for (const addr of detail.addresses) {
          await loadAddressTags(addr.id);
        }
      }
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDetailUpdated = (detail) => {
    setSelectedDetail(detail);
    // A CIDR edit (or an address change) can shift the whole nesting tree
    // (this subnet's parent, or other subnets' parents, may have changed) —
    // a full refetch keeps parentId accurate everywhere, not just here.
    refreshList();
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deleteSubnet(selectedId);
      setSelectedId(null);
      setSelectedDetail(null);
      await refreshList();
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <div className="nt-tool-header">
        <h2>IPAM</h2>
        <p>Track subnets with a VLAN tag, then record individual IP addresses as used, free, or reserved.</p>
      </div>

      <div className="tool-panel">
        <div className="ip-header-row">
          <SubnetSearch
            subnets={subnets}
            selectedId={selectedId}
            tags={allTags}
            selectedTagIds={selectedTagIds}
            onTagFilterChange={setSelectedTagIds}
            onSelect={(id, addressId) => {
              setViewMode("search");
              selectSubnet(id, addressId);
            }}
          />
          <AddSubnetForm
            onCreated={async (created) => {
              await refreshList();
              await selectSubnet(created.id);
            }}
          />
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setViewMode(viewMode === "dashboard" ? "search" : "dashboard")}
          >
            {viewMode === "dashboard" ? "Back to search" : "Dashboard"}
          </button>
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setViewMode(viewMode === "resubnet" ? "search" : "resubnet")}
          >
            {viewMode === "resubnet" ? "Back to search" : "Resubnet"}
          </button>
          <div className="ip-settings-wrap">
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={openSettings}
              title="Autodiscovery settings"
            >
              ⚙
            </button>
            {showSettings && (
              <div className="tool-popover ip-settings-popover">
                <div className="tool-hint">Autodiscovery settings</div>
                {scanConcurrencyLimit === null ? (
                  <div className="tool-hint">Loading…</div>
                ) : (
                  <>
                    <label className="tool-hint">
                      Simultaneous scans (hosts pinged at once)
                    </label>
                    <input
                      className="tool-input"
                      type="number"
                      min={concurrencyBounds.min}
                      max={concurrencyBounds.max}
                      value={scanConcurrencyLimit}
                      onChange={(e) => setScanConcurrencyLimit(e.target.value)}
                    />
                    <div className="tool-hint">
                      Range: {concurrencyBounds.min}–{concurrencyBounds.max}
                    </div>
                    {settingsError && <div className="tool-error">{settingsError}</div>}
                    <div className="ip-settings-actions">
                      <button
                        className="tool-btn tool-btn-primary"
                        onClick={saveSettings}
                        disabled={settingsSaving}
                      >
                        {settingsSaving ? "Saving…" : "Save"}
                      </button>
                      <button
                        className="tool-btn tool-btn-ghost"
                        onClick={() => setShowSettings(false)}
                        disabled={settingsSaving}
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {selectedTagIds.length > 0 && (
          <TagFilterBar
            tags={allTags.filter((t) => selectedTagIds.includes(t.id))}
            onRemove={handleFilterTagRemove}
          />
        )}

        {viewMode === "search" && (
          <>
            {listError && <div className="tool-error">{listError}</div>}

            <div className="ip-divider" />

            {!selectedId && !listError && (
              <div className="tool-empty">
                {listLoading
                  ? "Loading subnets…"
                  : subnets.length === 0
                  ? "No subnets yet — add one above to get started."
                  : "Search above to jump to a subnet by CIDR."}
              </div>
            )}

            {selectedId && detailLoading && <div className="tool-empty">Loading…</div>}

            {selectedId && !detailLoading && detailError && <div className="tool-error">{detailError}</div>}

            {selectedId && !detailLoading && selectedDetail && (
              <SubnetDetail
                subnet={selectedDetail}
                subnets={subnets}
                tags={allTags}
                subnetTagIds={subnetTagIds[selectedId] || []}
                onTagChange={(newIds) => handleTagChange(selectedId, newIds)}
                addressTagIds={addressTagIds}
                onAddressTagChange={handleAddressTagChange}
                deleting={deleting}
                onDelete={handleDelete}
                onDetailUpdated={handleDetailUpdated}
                onSelectSubnet={selectSubnet}
                highlightedAddressId={highlightedAddressId}
              />
            )}
          </>
        )}

        {viewMode === "dashboard" && (
          <IpamDashboard
            onSelectSubnet={(id) => {
              setViewMode("search");
              selectSubnet(id);
            }}
            tags={allTags}
          />
        )}

        {viewMode === "resubnet" && (
          <ResubnetReview onMoved={refreshList} />
        )}
      </div>
    </div>
  );
}