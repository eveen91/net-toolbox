import React, { useEffect, useRef, useState } from "react";

export function allocationDraftToRequest(draft) {
  return {
    status: draft.status,
    hostname: draft.hostname.trim() || null,
    description: draft.description.trim() || null,
    team: draft.team.trim() || null,
    machineType: draft.machineType || null,
    vmCluster: draft.machineType === "vm" ? draft.vmCluster.trim() || null : null,
    environment: draft.environment || null,
    locked: draft.locked,
  };
}

const initialDraft = {
  status: "reserved",
  hostname: "",
  description: "",
  team: "",
  machineType: "",
  vmCluster: "",
  environment: "",
  locked: false,
};

export default function AllocateNextAddressForm({ subnet, onAllocate, onCancel }) {
  const titleRef = useRef(null);
  const [draft, setDraft] = useState(initialDraft);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    titleRef.current?.focus();
    setDraft(initialDraft);
    setError(null);
  }, [subnet.id]);

  const update = (fields) => setDraft((current) => ({ ...current, ...fields }));
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await onAllocate(allocationDraftToRequest(draft));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="tool-modal-overlay" onClick={pending ? undefined : onCancel}>
      <section className="tool-modal ip-allocate-modal" role="dialog" aria-modal="true" aria-labelledby="ip-allocate-title" aria-busy={pending} onClick={(event) => event.stopPropagation()}>
        <div className="tool-modal-header">
          <div>
            <div className="ip-address-popover-title" id="ip-allocate-title" ref={titleRef} tabIndex="-1">Allocate next IP</div>
            <div className="tool-hint">Creates a reservation immediately in {subnet.cidr}. This cannot be previewed or saved later.</div>
          </div>
          <button type="button" className="tool-modal-close" onClick={onCancel} disabled={pending} aria-label="Close">×</button>
        </div>
        <form className="ip-address-popover-form" onSubmit={submit}>
          <div className="ip-allocate-grid">
            <div className="tool-field"><label className="tool-label" htmlFor="ip-allocate-status">Status</label><select id="ip-allocate-status" className="tool-input" value={draft.status} onChange={(event) => update({ status: event.target.value })} disabled={pending}><option value="reserved">Reserved</option><option value="used">Used</option></select></div>
            <div className="tool-field"><label className="tool-label" htmlFor="ip-allocate-hostname">Hostname</label><input id="ip-allocate-hostname" autoFocus className="tool-input" value={draft.hostname} onChange={(event) => update({ hostname: event.target.value })} disabled={pending} /></div>
            <div className="tool-field ip-allocate-wide"><label className="tool-label" htmlFor="ip-allocate-description">Description</label><input id="ip-allocate-description" className="tool-input" value={draft.description} onChange={(event) => update({ description: event.target.value })} disabled={pending} /></div>
            <div className="tool-field"><label className="tool-label" htmlFor="ip-allocate-team">Team</label><input id="ip-allocate-team" className="tool-input" value={draft.team} onChange={(event) => update({ team: event.target.value })} disabled={pending} /></div>
            <div className="tool-field"><label className="tool-label" htmlFor="ip-allocate-machine-type">Machine Type</label><select id="ip-allocate-machine-type" className="tool-input" value={draft.machineType} onChange={(event) => update({ machineType: event.target.value, vmCluster: "" })} disabled={pending}><option value="">—</option><option value="physical">Physical</option><option value="vm">VM</option></select></div>
            {draft.machineType === "vm" && <div className="tool-field"><label className="tool-label" htmlFor="ip-allocate-vm-cluster">VM Cluster</label><input id="ip-allocate-vm-cluster" className="tool-input" value={draft.vmCluster} onChange={(event) => update({ vmCluster: event.target.value })} disabled={pending} /></div>}
            <div className="tool-field"><label className="tool-label" htmlFor="ip-allocate-environment">Environment</label><select id="ip-allocate-environment" className="tool-input" value={draft.environment} onChange={(event) => update({ environment: event.target.value })} disabled={pending}><option value="">—</option><option value="prod">Prod</option><option value="test">Test</option><option value="dev">Dev</option></select></div>
          </div>
          <label className="ip-address-popover-locked" htmlFor="ip-allocate-locked"><input id="ip-allocate-locked" type="checkbox" checked={draft.locked} onChange={(event) => update({ locked: event.target.checked })} disabled={pending} />Locked</label>
          {error && <div className="tool-error" role="alert">{error}</div>}
          <div className="ip-address-popover-actions"><button className="tool-btn tool-btn-primary" type="submit" disabled={pending}>{pending ? "Allocating…" : "Allocate and reserve"}</button><button className="tool-btn tool-btn-ghost" type="button" onClick={onCancel} disabled={pending}>Cancel</button></div>
        </form>
      </section>
    </div>
  );
}
