import React, { useEffect, useRef, useState } from "react";
import TagSelector from "./TagSelector.jsx";
import { formatTimestamp } from "./logic.js";
import { addAddress, deleteAddress, rescanAddress, updateAddress } from "./api.js";

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

const STATUS_PILL_CLASSES = {
  used: "tool-pill-muted",
  free: "tool-pill-ok",
  reserved: "tool-pill-warn",
};

function draftFromAddress(address) {
  return {
    status: address?.status || "used",
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
  coords,
  placement,
  onClose,
  onUpdated,
  tags = [],
  addressTags = [],
  onAddressTagChange,
  onTagCreated,
}) {
  const popoverRef = useRef(null);
  const closeButtonRef = useRef(null);
  const selectionVersionRef = useRef(0);
  const [mode, setMode] = useState(address ? MODE_VIEW : MODE_ADD);
  const [draft, setDraft] = useState(() => draftFromAddress(address));
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const pending = pendingAction !== null;

  useEffect(() => {
    selectionVersionRef.current += 1;
    setMode(address ? MODE_VIEW : MODE_ADD);
    setDraft(draftFromAddress(address));
    setConfirmingDelete(false);
    setError(null);
    setPendingAction(null);
  // A refreshed subnet replaces the address object. Reset only when the user
  // selects another IP, so background updates never discard an active draft.
  }, [ip]);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, [ip, mode]);

  useEffect(() => {
    const handleMouseDown = (event) => {
      if (popoverRef.current && !popoverRef.current.contains(event.target)) onClose();
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const handleAdd = async (event) => {
    event.preventDefault();
    if (pending) return;
    setError(null);
    setPendingAction("add");
    const requestVersion = selectionVersionRef.current;
    try {
      const updated = await addAddress(
        subnetId,
        ip,
        draft.status,
        draft.hostname.trim() || null,
        draft.description.trim() || null,
        null,
        null,
        null,
        null,
        false
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
        draft.locked
      );
      onUpdated(updated);
      if (selectionVersionRef.current === requestVersion) setMode(MODE_VIEW);
    } catch (requestError) {
      if (selectionVersionRef.current === requestVersion) setError(requestError.message);
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
    setError(null);
    setPendingAction("delete");
    const requestVersion = selectionVersionRef.current;
    try {
      const updated = await deleteAddress(subnetId, address.id);
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
    setDraft(draftFromAddress(address));
    setConfirmingDelete(false);
    setError(null);
    setMode(MODE_EDIT);
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
  const isModal = mode === MODE_ADD || mode === MODE_EDIT;
  const title =
    mode === MODE_ADD
      ? `Add IP Address: ${ip}`
      : mode === MODE_EDIT
      ? `Edit IP Address: ${ip}`
      : `IP Address: ${ip}`;

  return (
    <div
      className={isModal ? "tool-modal-overlay" : undefined}
      onClick={isModal ? onClose : undefined}
    >
      <div
        ref={popoverRef}
        className={isModal ? "tool-modal" : `ip-address-popover ip-address-popover-${placement}`}
        style={isModal ? undefined : style}
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
          {mode === MODE_ADD ? (
            <span className="tool-pill tool-pill-ok ip-address-popover-status">Available</span>
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
          onClick={onClose}
          disabled={pending}
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {mode === MODE_ADD && (
        <form className="ip-address-popover-form" onSubmit={handleAdd}>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-status-${ip}`}>Status</label>
            <select
              id={`ip-address-status-${ip}`}
              className="tool-input"
              value={draft.status}
              onChange={(event) => setDraft({ ...draft, status: event.target.value })}
              disabled={pending}
            >
              <option value="used">Used</option>
              <option value="reserved">Reserved</option>
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
              disabled={pending}
            />
          </div>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-description-${ip}`}>Description <span className="tool-hint">optional</span></label>
            <input
              id={`ip-address-description-${ip}`}
              className="tool-input"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              disabled={pending}
            />
          </div>
          <div className="ip-address-popover-actions">
            <button className="tool-btn tool-btn-primary" type="submit" disabled={pending}>
              {pendingAction === "add" ? "Adding..." : "Add address"}
            </button>
            <button className="tool-btn tool-btn-ghost" type="button" onClick={onClose} disabled={pending}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode === MODE_VIEW && address && (
        <>
          <div className="ip-address-popover-details">
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
              disabled={pending}
              onTagCreated={onTagCreated}
            />
          </div>
          {confirmingDelete ? (
            <div className="ip-address-popover-confirm">
              <div>Delete this address record? This cannot be undone.</div>
              <div className="ip-address-popover-actions">
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost ip-row-btn-danger"
                  onClick={handleDelete}
                  disabled={pending}
                >
                  {pendingAction === "delete" ? "Deleting..." : "Confirm delete"}
                </button>
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost"
                  onClick={() => setConfirmingDelete(false)}
                  disabled={pending}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="ip-address-popover-actions">
              {address.status !== "reserved" && (
                <button type="button" className="tool-btn tool-btn-ghost" onClick={handleRescan} disabled={pending}>
                  {pendingAction === "rescan" ? "Rescanning..." : "Rescan"}
                </button>
              )}
              <button type="button" className="tool-btn tool-btn-ghost" onClick={startEdit} disabled={pending}>
                Edit
              </button>
              <button
                type="button"
                className="tool-btn tool-btn-ghost ip-row-btn-danger"
                onClick={() => setConfirmingDelete(true)}
                disabled={pending}
              >
                Delete
              </button>
            </div>
          )}
        </>
      )}

      {mode === MODE_EDIT && address && (
        <form className="ip-address-popover-form" onSubmit={handleUpdate}>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-status-${ip}`}>Status</label>
            <select id={`ip-address-status-${ip}`} className="tool-input" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })} disabled={pending}>
              <option value="used">Used</option>
              <option value="free">Free</option>
              <option value="reserved">Reserved</option>
            </select>
          </div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-hostname-${ip}`}>Hostname</label><input id={`ip-address-hostname-${ip}`} className="tool-input" value={draft.hostname} onChange={(event) => setDraft({ ...draft, hostname: event.target.value })} disabled={pending} /></div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-description-${ip}`}>Description</label><input id={`ip-address-description-${ip}`} className="tool-input" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} disabled={pending} /></div>
          <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-team-${ip}`}>Team</label><input id={`ip-address-team-${ip}`} className="tool-input" value={draft.team} onChange={(event) => setDraft({ ...draft, team: event.target.value })} disabled={pending} /></div>
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-machine-type-${ip}`}>Machine Type</label>
            <select
              id={`ip-address-machine-type-${ip}`}
              className="tool-input"
              value={draft.machineType}
              onChange={(event) => setDraft({ ...draft, machineType: event.target.value, vmCluster: "" })}
              disabled={pending}
            >
              <option value="">-</option>
              <option value="physical">Physical</option>
              <option value="vm">VM</option>
            </select>
          </div>
          {draft.machineType === "vm" && (
            <div className="tool-field"><label className="tool-label" htmlFor={`ip-address-vm-cluster-${ip}`}>VM Cluster</label><input id={`ip-address-vm-cluster-${ip}`} className="tool-input" value={draft.vmCluster} onChange={(event) => setDraft({ ...draft, vmCluster: event.target.value })} disabled={pending} /></div>
          )}
          <div className="tool-field">
            <label className="tool-label" htmlFor={`ip-address-environment-${ip}`}>Environment</label>
            <select id={`ip-address-environment-${ip}`} className="tool-input" value={draft.environment} onChange={(event) => setDraft({ ...draft, environment: event.target.value })} disabled={pending}>
              <option value="">-</option>
              <option value="prod">Prod</option>
              <option value="test">Test</option>
              <option value="dev">Dev</option>
            </select>
          </div>
          <label className="ip-address-popover-locked" htmlFor={`ip-address-locked-${ip}`}>
            <input id={`ip-address-locked-${ip}`} type="checkbox" checked={draft.locked} onChange={(event) => setDraft({ ...draft, locked: event.target.checked })} disabled={pending} />
            Locked
          </label>
          <div className="ip-address-popover-actions">
            <button className="tool-btn tool-btn-primary" type="submit" disabled={pending}>
              {pendingAction === "update" ? "Saving..." : "Save changes"}
            </button>
            <button className="tool-btn tool-btn-ghost" type="button" onClick={cancelEdit} disabled={pending}>
              Cancel
            </button>
          </div>
        </form>
      )}

          {pending && <div className="sr-only" aria-live="polite">{pendingAction} in progress</div>}
          {error && <div className="tool-error" role="alert">{error}</div>}
      </div>
      </div>
    </div>
  );
}
