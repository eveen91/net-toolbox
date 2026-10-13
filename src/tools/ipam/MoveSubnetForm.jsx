import React, { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext.jsx";
import { listSubnetMoveTargets, previewSubnetMove, moveSubnetToTenant } from "./api.js";

export default function MoveSubnetForm({ subnet, onMoved, disabled }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [targets, setTargets] = useState(null);
  const [target, setTarget] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open || !user) return;
    let active = true;
    setTargets(null); setError(null);
    listSubnetMoveTargets().then(data => { if (active) setTargets(data); })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [open, user, retry]);
  if (!user) return null;
  const review = async () => {
    setBusy(true); setError(null); setPreview(null);
    try { setPreview(await previewSubnetMove(subnet.id, target)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    setBusy(true); setError(null);
    try { onMoved(await moveSubnetToTenant(subnet.id, target, preview.version)); }
    catch (e) { setError(e.message); setPreview(null); }
    finally { setBusy(false); }
  };
  return <div className="ip-move-subnet">
    <button className="tool-btn tool-btn-ghost" disabled={busy || disabled} aria-expanded={open} onClick={() => { setOpen(!open); setPreview(null); }}>Move to tenant</button>
    {open && <div>
      {error && <p className="tool-error" role="alert">{error}</p>}
      {!targets && !error && <p role="status">Loading tenants…</p>}
      {!targets && error && <button className="tool-btn" onClick={() => setRetry(n => n + 1)}>Retry</button>}
      {targets?.length === 0 && <p className="tool-hint">No other tenants with IPAM write access. Create a tenant and grant access in tenant settings.</p>}
      {targets?.length > 0 && <fieldset disabled={busy || disabled}>
        <label>Destination tenant <select className="tool-input" value={target} onChange={e => { setTarget(e.target.value); setPreview(null); setError(null); }}>
          <option value="">Select tenant…</option>{targets.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select></label>
        {!preview && <button className="tool-btn" disabled={!target} onClick={review}>{busy ? "Checking…" : "Review move"}</button>}
        {preview && <div>
          <p>Move <strong>{preview.cidr}</strong> from <strong>{preview.sourceTenantName}</strong> to <strong>{preview.targetTenantName}</strong>?</p>
          <p>{preview.subnetCount} subnets (including this subnet), {preview.addressCount} address records, {preview.dhcpPoolCount} DHCP pools, {preview.reservationCount} range reservations and {preview.tagCount} tags.</p>
          <p className="tool-hint">Includes scan exclusions, {preview.scanCount} completed scans and {preview.auditCount} audit entries. All nested subnets will leave the source tenant. Destination data will never be overwritten.</p>
          {preview.scheduleCount > 0 && <p className="tool-hint">{preview.scheduleCount} scan schedules will be moved as disabled. Enable them in the destination tenant when ready.</p>}
          <p className="tool-hint">Archived records and data quality mutes stay in the source tenant.</p>
          <button className="tool-btn" onClick={confirm}>{busy ? "Moving…" : "Confirm move"}</button>
          <button className="tool-btn tool-btn-ghost" onClick={() => setPreview(null)}>Cancel</button>
        </div>}
      </fieldset>}
    </div>}
  </div>;
}
