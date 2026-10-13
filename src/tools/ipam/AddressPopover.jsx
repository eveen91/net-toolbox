import React, { useEffect, useRef, useState } from "react";
import useUnsavedChanges from "../../components/useUnsavedChanges.js";
import AuditTimeline from "./AuditTimeline.jsx";
import TagSelector from "./TagSelector.jsx";
import { formatTimestamp, isOutsidePointerStart } from "./logic.js";
import { useAccessibleDialog } from "./hooks/useAccessibleDialog.js";
import { addAddress, deleteAddress, getSubnetAddresses, releaseAddress, rescanAddress, updateAddress } from "./api.js";

const MODE_ADD = "add";
const MODE_VIEW = "view";
const MODE_EDIT = "edit";

const MACHINE_TYPE_LABELS = {
  physical: "Physical",
  vm: "VM",
};

const ENVIRONMENT_LABELS = {
  prod: "Prod",
  test: "Test",
  dev: "Dev",
};

const STATUS_LABELS = {
  used: "Used",
  free: "Free",
  reserved: "Reserved",
};

const ALLOCATION_TYPE_LABELS = {
  gateway: "Gateway", static: "Static", dhcp: "DHCP", vip: "VIP", loopback: "Loopback",
  infrastructure: "Infrastructure", network: "Network", broadcast: "Broadcast",
};

const STATUS_PILL_CLASSES = {
  used: "tool-pill-muted",
  free: "tool-pill-ok",
  reserved: "tool-pill-warn",
};

export function addressDraftToRequest(draft) {
  return {
    status: draft.status,
    allocationType: draft.allocationType,
    hostname: draft.hostname.trim() || null,
    description: draft.description.trim() || null,
    team: draft.team.trim() || null,
    machineType: draft.machineType || null,
    vmCluster: draft.machineType === "vm" ? draft.vmCluster.trim() || null : null,
    environment: draft.environment || null,
    locked: Boolean(draft.locked),
  };
}

function draftFromAddress(address) {
  return {
    status: address?.status || "used",
    allocationType: address?.allocationType || "static",
    hostname: address?.hostname || "",
    description: address?.description || "",
    team: address?.team || "",
    machineType: address?.machineType || "",
    vmCluster: address?.vmCluster || "",
    environment: address?.environment || "",
    locked: Boolean(address?.locked),
  };
}

function Detail({ label, children }) {
  return (
    <>
      <div className="ip-address-popover-detail-label">{label}</div>
        <div className="ip-address-popover-detail-value">{children ?? "-"}</div>
    </>
  );
}

export default function AddressPopover({
  ip,
  address,
  subnetId,
  coords = { x: 0, y: 0, arrowOffset: 0 },
  placement,
  onClose,
  onUpdated,
  tags = [],
  addressTags = [],
  onAddressTagChange,
  onTagCreated,
  canWrite = true,
  canScan = true,
  canAdmin = true,
  inspector = false,
}) {
  const popoverRef = useRef(null);
  const closeButtonRef = useRef(null);
  const selectionVersionRef = useRef(0);
  const [mode, setMode] = useState(address ? MODE_VIEW : MODE_ADD);
  const [draft, setDraft] = useState(() => draftFromAddress(address));
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [viewSection, setViewSection] = useState("details");
  const editVersionRef = useRef(address?.updatedAt);
  const [conflict, setConflict] = useState(false);
  const pending = pendingAction !== null;
  const dirty = mode !== MODE_VIEW && JSON.stringify(draft) !== JSON.stringify(draftFromAddress(address));
  useUnsavedChanges(dirty, pending);
  const requestClose = () => {
    if (pending) return;
    if (dirty && !window.confirm("Discard unsaved address changes?")) return;
    onClose();
  };
  const isModal = !inspector && (mode === MODE_ADD || mode === MODE_EDIT);
  const { dialogRef } = useAccessibleDialog(isModal, requestClose, { restoreFocus: false });

  useEffect(() => {
    selectionVersionRef.current += 1;
    setMode(address ? MODE_VIEW : MODE_ADD);
    setDraft(draftFromAddress(address));
    setConfirmingDelete(false);
    setError(null);
    setPendingAction(null);
    setConflict(false);
    setViewSection("details");
  // A refreshed subnet replaces the address object. Reset only when the user
  // selects another IP, so background updates never discard an active draft.
  }, [ip]);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, [ip, mode]);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (!inspector && isOutsidePointerStart(popoverRef.current, event.target)) requestClose();
    };
    const handleKeyDown = (event) => {
      if (!isModal && event.key === "Escape" && popoverRef.current?.contains(event.target)) requestClose();
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, inspector, dirty, pending, isModal]);

  const handleAdd = async (event) => {
    event.preventDefault();
    if (pending) return;
    setError(null);
    setPendingAction("add");
    const requestVersion = selectionVersionRef.current;
    try {
      const payload = addressDraftToRequest(draft);
      const updated = await addAddress(
        subnetId, ip, payload.status, payload.hostname, payload.description,
        null, null, null, null, false, payload.allocationType
      );
      onUpdated(updated);
      if (selectionVersionRef.current === requestVersion) onClose(ip);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) setError(requestError.message);
    } finally {
      if (selectionVersionRef.current === requestVersion) setPendingAction(null);
    }
  };

  const handleUpdate = async (event) => {
    event.preventDefault();
    if (!address || pending) return;
    setError(null);
    setPendingAction("update");
    const requestVersion = selectionVersionRef.current;
    try {
      const updated = await updateAddress(
        subnetId,
        address.id,
        address.address,
        draft.status,
        draft.hostname.trim() || null,
        draft.description.trim() || null,
        draft.team.trim() || null,
        draft.machineType || null,
        draft.machineType === "vm" ? draft.vmCluster.trim() || null : null,
        draft.environment || null,
        draft.locked,
        draft.allocationType,
        editVersionRef.current
      );
      onUpdated(updated);
      if (selectionVersionRef.current === requestVersion) setMode(MODE_VIEW);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) { setError(requestError.message); setConflict(requestError.message.includes("modified by another user")); }
    } finally {
      if (selectionVersionRef.current === requestVersion) setPendingAction(null);
    }
  };

  const handleRescan = async () => {
    if (!address || pending) return;
    setError(null);
    setPendingAction("rescan");
    const requestVersion = selectionVersionRef.current;
    try {
      const updated = await rescanAddress(subnetId, address.id);
      onUpdated(updated);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) setError(requestError.message);
    } finally {
      if (selectionVersionRef.current === requestVersion) setPendingAction(null);
    }
  };

  const handleDelete = async () => {
    if (!address || pending) return;
    const releasing = address.status === "free";
    const reason = releasing ? null : window.prompt("Archive reason:");
    if (!releasing && !reason?.trim()) return;
    setError(null);
    setPendingAction(releasing ? "release" : "delete");
    const requestVersion = selectionVersionRef.current;
    try {
      const updated = releasing
        ? await releaseAddress(subnetId, address.id)
        : await deleteAddress(subnetId, address.id, reason.trim());
      onUpdated(updated);
      if (selectionVersionRef.current === requestVersion) onClose(ip);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) setError(requestError.message);
    } finally {
      if (selectionVersionRef.current === requestVersion) setPendingAction(null);
    }
  };

  const handleTagChange = async (newIds) => {
    if (!address || pending || !onAddressTagChange) return;
    setError(null);
    setPendingAction("tags");
    const requestVersion = selectionVersionRef.current;
    try {
      await onAddressTagChange(address.id, newIds);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) setError(requestError.message);
    } finally {
      if (selectionVersionRef.current === requestVersion) setPendingAction(null);
    }
  };

  const startEdit = () => {
    editVersionRef.current = address.updatedAt;
    setDraft(draftFromAddress(address));
    setConfirmingDelete(false);
    setError(null);
    setMode(MODE_EDIT);
  };

  const reloadAddress = async () => {
    if (pending) return;
    setPendingAction("reload");
    const requestVersion = selectionVersionRef.current;
    try {
      const page = await getSubnetAddresses(subnetId, { addressStart: ip, addressEnd: ip, limit: 1 });
      const current = page.addresses.find((item) => item.id === address.id);
      if (!current) throw new Error("Address no longer exists. Close this editor and refresh inventory.");
      if (selectionVersionRef.current !== requestVersion) return;
      setDraft(draftFromAddress(current));
      editVersionRef.current = current.updatedAt;
      setError(null);
      setConflict(false);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) setError(requestError.message);
    } finally {
      if (selectionVersionRef.current === requestVersion) setPendingAction(null);
    }
  };

  const cancelEdit = () => {
    setDraft(draftFromAddress(address));
    setError(null);
    setMode(MODE_VIEW);
  };

  const style = {
    left: `${coords.x}px`,
    top: `${coords.y}px`,
    "--ip-popover-arrow-offset": `${coords.arrowOffset}px`,
  };
  const title =
    mode === MODE_ADD
      ? `Add IP Address: ${ip}`
      : mode === MODE_EDIT
      ? `Edit IP Address: ${ip}`
      : `IP Address: ${ip}`;

  return (
    <div className={inspector ? "ip-inspector-shell" : isModal ? "tool-modal-overlay" : undefined}>
      <div
        ref={(node) => { popoverRef.current = node; dialogRef.current = node; }}
        className={inspector ? "ip-address-inspector" : isModal ? "tool-modal" : `ip-address-popover ip-address-popover-${placement}`}
        style={isModal || inspector ? undefined : style}
        role="dialog"
        aria-modal={isModal || undefined}
        aria-labelledby={`ip-address-dialog-title-${ip}`}
        aria-busy={pending}
        onClick={isModal ? (event) => event.stopPropagation() : undefined}
      >
      <div className={isModal ? undefined : "ip-address-popover-scroll"}>
      <div className={isModal ? "tool-modal-header" : "ip-address-popover-header"}>
        <div>
          <div className="ip-address-popover-title" id={`ip-address-dialog-title-${ip}`}>
            {title}
          </div>
          {mode === MODE_ADD && <div className="tool-hint">IPv4 only. Network and broadcast addresses cannot be assigned.</div>}
          {mode === MODE_ADD ? (
            <span className="tool-pill tool-pill-muted ip-address-popover-status">Not recorded</span>
          ) : (
            <span className={`tool-pill ${STATUS_PILL_CLASSES[address?.status] || "tool-pill-muted"} ip-address-popover-status`}>
              {STATUS_LABELS[address?.status] || address?.status || "-"}
            </span>
          )}
        </div>
        <button
          type="button"
          ref={closeButtonRef}
          className={isModal ? "tool-modal-close" : "ip-address-popover-close"}
          onClick={requestClose}
          disabled={pending}
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {mode === MODE_ADD && !canWrite && <div className="tool-hint">This address is not recorded. Your role has read-only access.</div>}
      {mode === MODE_ADD && canWrite && (
        <form className="ip-address-popover-form" onSubmit={handleAdd}>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-status-${ip}`}>Status</label>
            <select
              id={`ip-address-status-${ip}`}
              className="tool-input"
              value={draft.status}
              onChange={(event) => setDraft({ ...draft, status: event.target.value })}
              disabled={pending || !canWrite}
            >
              <option value="used">Used</option>
              <option value="reserved">Reserved</option>
            </select>
          </div>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-allocation-type-${ip}`}>Allocation type</label>
            <select id={`ip-address-allocation-type-${ip}`} className="tool-input" value={draft.allocationType} onChange={(event) => setDraft({ ...draft, allocationType: event.target.value })} disabled={pending || !canWrite}>
              {Object.entries(ALLOCATION_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-hostname-${ip}`}>Hostname <span className="tool-hint">optional</span></label>
            <input
              id={`ip-address-hostname-${ip}`}
              autoFocus
              className="tool-input"
              value={draft.hostname}
              onChange={(event) => setDraft({ ...draft, hostname: event.target.value })}
              disabled={pending || !canWrite}
            />
          </div>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-description-${ip}`}>Description <span className="tool-hint">optional</span></label>
            <input
              id={`ip-address-description-${ip}`}
              className="tool-input"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              disabled={pending || !canWrite}
            />
          </div>
          <div className="ip-address-popover-actions">
            <button className="tool-btn tool-btn-primary" type="submit" disabled={pending || !canWrite}>
              {pendingAction === "add" ? "Adding..." : "Add address"}
            </button>
            <button className="tool-btn tool-btn-ghost" type="button" onClick={requestClose} disabled={pending || !canWrite}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode === MODE_VIEW && address && (
        <>
          <div className="ip-address-popover-tabs" role="tablist" aria-label="Address sections">
            <button type="button" role="tab" aria-selected={viewSection === "details"} aria-controls={`ip-address-details-${address.id}`} className={viewSection === "details" ? "active" : ""} onClick={() => setViewSection("details")}>Details</button>
            <button type="button" role="tab" aria-selected={viewSection === "history"} aria-controls={`ip-address-history-${address.id}`} className={viewSection === "history" ? "active" : ""} onClick={() => setViewSection("history")}>History</button>
          </div>
          {viewSection === "details" ? <div id={`ip-address-details-${address.id}`} role="tabpanel">
          <div className="ip-address-popover-details">
            <Detail label="Allocation type">{ALLOCATION_TYPE_LABELS[address.allocationType] || address.allocationType || "Static"}</Detail>
            <Detail label="Hostname">{address.hostname || "-"}</Detail>
            <Detail label="Description">{address.description || "-"}</Detail>
            <Detail label="Team">{address.team || "-"}</Detail>
            <Detail label="Machine Type">{MACHINE_TYPE_LABELS[address.machineType] || "-"}</Detail>
            {address.machineType === "vm" && <Detail label="VM Cluster">{address.vmCluster || "-"}</Detail>}
            <Detail label="Environment">{ENVIRONMENT_LABELS[address.environment] || "-"}</Detail>
            <Detail label="Locked">{address.locked ? "Yes" : "No"}</Detail>
            <Detail label="Updated">{formatTimestamp(address.updatedAt)}</Detail>
          </div>
          <div className={`ip-address-popover-tags${pendingAction === "tags" ? " pending" : ""}`}>
            <div className="ip-address-popover-detail-label">Tags</div>
            <TagSelector
              value={addressTags.map((tag) => tag.id)}
              onChange={handleTagChange}
              allTags={tags}
              placeholder={pendingAction === "tags" ? "Saving tags..." : "Add tags"}
              disabled={pending || !canWrite}
              onTagCreated={onTagCreated}
              canCreate={canAdmin}
            />
          </div>
          {confirmingDelete ? (
            <div className="ip-address-popover-confirm">
              <div>{address.status === "free" ? "Release this free address? Its stored metadata will be cleared and it will disappear from the address list." : "Archive this address record? It can be restored from Archive before retention expires."}</div>
              <div className="ip-address-popover-actions">
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost ip-row-btn-danger"
                  onClick={handleDelete}
                  disabled={pending || !canWrite}
                >
                  {pendingAction === "release" ? "Releasing..." : pendingAction === "delete" ? "Deleting..." : address.status === "free" ? "Confirm release" : "Confirm delete"}
                </button>
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost"
                  onClick={() => setConfirmingDelete(false)}
                  disabled={pending || !canWrite}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="ip-address-popover-actions">
              {canScan && address.status !== "reserved" && (
                <button type="button" className="tool-btn tool-btn-ghost" onClick={handleRescan} disabled={pending}>
                  {pendingAction === "rescan" ? "Rescanning..." : "Rescan"}
                </button>
              )}
              <button type="button" className="tool-btn tool-btn-ghost" onClick={startEdit} disabled={pending || !canWrite}>
                Edit
              </button>
              <button
                type="button"
                className="tool-btn tool-btn-ghost ip-row-btn-danger"
                onClick={() => setConfirmingDelete(true)}
                disabled={pending || !canWrite}
              >
                {address.status === "free" ? "Release" : "Delete"}
              </button>
            </div>
          )}
          </div> : (
            <div id={`ip-address-history-${address.id}`} role="tabpanel">
              <AuditTimeline key={address.id} addressId={address.id} title={`${address.address} history`} pageSize={10} compact showTarget={false} />
            </div>
          )}
        </>
      )}

      {mode === MODE_EDIT && address && (
        <form className="ip-address-popover-form" onSubmit={handleUpdate}>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-status-${ip}`}>Status</label>
            <select id={`ip-address-status-${ip}`} className="tool-input" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })} disabled={pending || !canWrite}>
              <option value="used">Used</option>
              <option value="free">Free</option>
              <option value="reserved">Reserved</option>
            </select>
          </div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-allocation-type-${ip}`}>Allocation type</label><select id={`ip-address-allocation-type-${ip}`} className="tool-input" value={draft.allocationType} onChange={(event) => setDraft({ ...draft, allocationType: event.target.value })} disabled={pending || !canWrite}>{Object.entries(ALLOCATION_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-hostname-${ip}`}>Hostname</label><input id={`ip-address-hostname-${ip}`} className="tool-input" value={draft.hostname} onChange={(event) => setDraft({ ...draft, hostname: event.target.value })} disabled={pending || !canWrite} /></div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-description-${ip}`}>Description</label><input id={`ip-address-description-${ip}`} className="tool-input" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} disabled={pending || !canWrite} /></div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-team-${ip}`}>Team</label><input id={`ip-address-team-${ip}`} className="tool-input" value={draft.team} onChange={(event) => setDraft({ ...draft, team: event.target.value })} disabled={pending || !canWrite} /></div>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-machine-type-${ip}`}>Machine Type</label>
            <select
              id={`ip-address-machine-type-${ip}`}
              className="tool-input"
              value={draft.machineType}
              onChange={(event) => setDraft({ ...draft, machineType: event.target.value, vmCluster: "" })}
              disabled={pending || !canWrite}
            >
              <option value="">-</option>
              <option value="physical">Physical</option>
              <option value="vm">VM</option>
            </select>
          </div>
          {draft.machineType === "vm" && (
            <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-vm-cluster-${ip}`}>VM Cluster</label><input id={`ip-address-vm-cluster-${ip}`} className="tool-input" value={draft.vmCluster} onChange={(event) => setDraft({ ...draft, vmCluster: event.target.value })} disabled={pending || !canWrite} /></div>
          )}
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-environment-${ip}`}>Environment</label>
            <select id={`ip-address-environment-${ip}`} className="tool-input" value={draft.environment} onChange={(event) => setDraft({ ...draft, environment: event.target.value })} disabled={pending || !canWrite}>
              <option value="">-</option>
              <option value="prod">Prod</option>
              <option value="test">Test</option>
              <option value="dev">Dev</option>
            </select>
          </div>
          <label className="ip-address-popover-locked" htmlFor={`ip-address-locked-${ip}`}>
            <input id={`ip-address-locked-${ip}`} type="checkbox" checked={draft.locked} onChange={(event) => setDraft({ ...draft, locked: event.target.checked })} disabled={pending || !canWrite} />
            Locked
          </label>
          <div className="ip-address-popover-actions">
            <button className="tool-btn tool-btn-primary" type="submit" disabled={pending || !canWrite}>
              {pendingAction === "update" ? "Saving..." : "Save changes"}
            </button>
            <button className="tool-btn tool-btn-ghost" type="button" onClick={cancelEdit} disabled={pending || !canWrite}>
              Cancel
            </button>
          </div>
        </form>
      )}

          {pending && <div className="sr-only" aria-live="polite">{pendingAction} in progress</div>}
          {error && <div className="tool-error" role="alert">{error}{conflict && <button type="button" className="tool-btn tool-btn-ghost ip-row-btn" onClick={reloadAddress} disabled={pending}>Reload current values</button>}</div>}
      </div>
      </div>
    </div>
  );
}
