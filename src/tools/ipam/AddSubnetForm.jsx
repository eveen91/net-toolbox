import React, { useState } from "react";
import { createSubnet } from "./api.js";

/**
 * "Add a subnet" as a self-contained trigger + collapsible form, so it can
 * live in a header row instead of taking up permanent space in a left
 * column. Owns its own open/closed state and talks to the API directly —
 * the only thing the caller needs to do is handle onCreated(subnet).
 */
export default function AddSubnetForm({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [cidr, setCidr] = useState("");
  const [vlan, setVlan] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const reset = () => {
    setCidr("");
    setVlan("");
    setDescription("");
    setError(null);
  };

  const close = () => {
    setOpen(false);
    reset();
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!cidr.trim()) return;
    setError(null);
    setCreating(true);
    try {
      const vlanValue = vlan.trim() === "" ? null : Number(vlan);
      const created = await createSubnet(cidr.trim(), vlanValue, description.trim() || null);
      reset();
      setOpen(false);
      onCreated(created);
    } catch (e2) {
      setError(e2.message);
    } finally {
      setCreating(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="tool-btn tool-btn-primary ip-add-subnet-trigger" onClick={() => setOpen(true)}>
        + Add subnet
      </button>
    );
  }

  return (
    <div className="tool-popover ip-add-subnet-popover">
      <form className="ip-add-subnet-form" onSubmit={submit}>
        <div className="tool-field">
          <div className="tool-label">
            <span>CIDR</span>
          </div>
          <input
            autoFocus
            className="tool-input"
            placeholder="10.0.1.0/24"
            value={cidr}
            onChange={(e) => setCidr(e.target.value)}
          />
        </div>
        <div className="tool-field">
          <div className="tool-label">
            <span>
              VLAN <span className="tool-hint">optional</span>
            </span>
          </div>
          <input className="tool-input" placeholder="e.g. 120" value={vlan} onChange={(e) => setVlan(e.target.value)} />
        </div>
        <div className="tool-field">
          <div className="tool-label">
            <span>
              Description <span className="tool-hint">optional</span>
            </span>
          </div>
          <input
            className="tool-input"
            placeholder="e.g. App servers — east DC"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="tool-actions">
          <button className="tool-btn tool-btn-primary" type="submit" disabled={creating || !cidr.trim()}>
            {creating ? "Adding…" : "Add subnet"}
          </button>
          <button type="button" className="tool-btn tool-btn-ghost" onClick={close} disabled={creating}>
            Cancel
          </button>
        </div>
        {error && <div className="tool-error">{error}</div>}
      </form>
    </div>
  );
}