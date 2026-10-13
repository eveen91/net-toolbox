import React, { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext.jsx";
import { listRoutingMoveTargets, previewRoutingHostMove, moveRoutingHost } from "./api.js";

export default function MoveHostForm({ host, onMoved }) {
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
    setTargets(null);
    setError(null);
    listRoutingMoveTargets().then(data => { if (active) setTargets(data); })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [open, user, retry]);
  if (!user) return null;
  const review = async () => {
    setBusy(true); setError(null); setPreview(null);
    try { setPreview(await previewRoutingHostMove(host, target)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    setBusy(true); setError(null);
    try { const result = await moveRoutingHost(host, target, preview.version); onMoved(result); }
    catch (e) { setError(e.message); setPreview(null); }
    finally { setBusy(false); }
  };
  return <div className="rm-move-host">
    <button className="tool-btn tool-btn-ghost" onClick={() => { setOpen(!open); setPreview(null); }} disabled={busy} aria-expanded={open}>Move to tenant</button>
    {open && <div>
      {error && <p className="tool-error" role="alert">{error}</p>}
      {!targets && !error && <p role="status">Loading tenants…</p>}
      {!targets && error && <button className="tool-btn" onClick={() => setRetry(n => n + 1)}>Retry</button>}
      {targets?.length === 0 && <p className="tool-hint">No other tenants with Routing Map access. Create a tenant and grant access in tenant settings.</p>}
      {targets?.length > 0 && <fieldset disabled={busy}>
        <label>Destination tenant <select value={target} onChange={e => { setTarget(e.target.value); setPreview(null); setError(null); }}>
          <option value="">Select tenant…</option>{targets.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select></label>
        {!preview && <button className="tool-btn" disabled={!target} onClick={review}>{busy ? "Checking…" : "Review move"}</button>}
        {preview && <div>
          <p>Move <strong>{host}</strong> with {preview.routeCount} routes and {preview.interfaceCount} interfaces from <strong>{preview.sourceTenantName}</strong> to <strong>{preview.targetTenantName}</strong>?</p>
          <p className="tool-hint">The host will be removed from the source tenant. Existing destination hosts will never be overwritten.</p>
          <button className="tool-btn" onClick={confirm}>{busy ? "Moving…" : "Confirm move"}</button>
          <button className="tool-btn tool-btn-ghost" onClick={() => setPreview(null)}>Cancel</button>
        </div>}
      </fieldset>}
    </div>}
  </div>;
}
