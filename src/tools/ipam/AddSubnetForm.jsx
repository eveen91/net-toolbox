import React, { useState } from "react";
import { createSubnet } from "./api.js";

export default function AddSubnetForm({ onCreated }) {
  const [modalOpen, setModalOpen] = useState(false);
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

  const closeModal = () => {
    setModalOpen(false);
    reset();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!cidr.trim()) return;
    setError(null);
    setCreating(true);
    try {
      const vlanValue = vlan.trim() === "" ? null : Number(vlan);
      const created = await createSubnet(cidr.trim(), vlanValue, description.trim() || null);
      reset();
      setModalOpen(false);
      onCreated(created);
    } catch (e2) {
      setError(e2.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <button type="button" className="tool-btn tool-btn-primary" onClick={() => setModalOpen(true)}>
        + Add subnet
      </button>

      {modalOpen && (
        <div className="tool-modal-overlay" onClick={closeModal}>
          <div className="tool-modal" onClick={(e) => e.stopPropagation()}>
            <div className="tool-modal-header">
              <h3>Add Subnet</h3>
              <button type="button" className="tool-modal-close" onClick={closeModal}>
                ×
              </button>
            </div>
            <form onSubmit={handleSubmit}>
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
                  required
                />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>VLAN <span className="tool-hint">optional</span></span>
                </div>
                <input className="tool-input" placeholder="e.g. 120" value={vlan} onChange={(e) => setVlan(e.target.value)} />
              </div>
              <div className="tool-field">
                <div className="tool-label">
                  <span>Description <span className="tool-hint">optional</span></span>
                </div>
                <input
                  className="tool-input"
                  placeholder="e.g. App servers — east DC"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="tool-actions">
                <button
                  type="submit"
                  className="tool-btn tool-btn-primary"
                  disabled={creating || !cidr.trim()}
                >
                  {creating ? "Adding…" : "Add subnet"}
                </button>
                <button
                  type="button"
                  className="tool-btn tool-btn-ghost"
                  onClick={closeModal}
                  disabled={creating}
                >
                  Cancel
                </button>
              </div>
              {error && <div className="tool-error">{error}</div>}
            </form>
          </div>
        </div>
      )}
    </>
  );
}
