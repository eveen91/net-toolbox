import React, { useCallback, useEffect, useState } from "react";
import { fetchArchives, restoreArchive } from "./api.js";

export function archiveLabel(entry) {
  const data = entry.snapshot;
  return data.cidr || data.address || `${data.start_ip} – ${data.end_ip}`;
}

export default function ArchiveReview({ canWrite, onRestored }) {
  const [entries, setEntries] = useState([]);
  const [type, setType] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null);
  const [review, setReview] = useState(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setEntries(await fetchArchives()); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const restore = async (entry) => {
    if (!canWrite || pending !== null) return;
    setPending(entry.id);
    setError(null);
    try {
      await restoreArchive(entry.id);
      setEntries((items) => items.filter((item) => item.id !== entry.id));
      setReview(null);
      await onRestored?.();
    } catch (requestError) { setError(requestError.message); }
    finally { setPending(null); }
  };
  const filtered = entries.filter((entry) => !type || entry.resource_type === type);

  return <div>
    <h3>Archive</h3>
    <p className="tool-hint">Archived records can be restored before their retention expires. Restoration checks conflicts with current inventory.</p>
    <div className="ip-quality-toolbar">
      <label htmlFor="ip-archive-type">Resource type</label>
      <select id="ip-archive-type" className="tool-input ip-row-input" value={type} onChange={(event) => setType(event.target.value)} disabled={pending !== null}>
        <option value="">All resources</option><option value="subnet">Subnets</option><option value="address">Addresses</option><option value="dhcp_pool">DHCP pools</option>
      </select>
      <button type="button" className="tool-btn tool-btn-ghost" onClick={load} disabled={loading || pending !== null}>Refresh</button>
    </div>
    {error && <div className="tool-error" role="alert">{error}</div>}
    {loading ? <div className="tool-empty" role="status">Loading archived records…</div> : filtered.length === 0 ? <div className="tool-empty">No archived records match this filter.</div> :
      <div className="tool-table-wrap ip-table-wrap-full"><table className="tool-table">
        <thead><tr><th>Resource</th><th>Type</th><th>Reason</th><th>Archived</th><th>Retention expires</th><th>Action</th></tr></thead>
        <tbody>{filtered.map((entry) => <tr key={entry.id}>
          <td className="ip-mono">{archiveLabel(entry)}</td><td>{entry.resource_type}</td><td>{entry.reason}</td><td>{new Date(entry.archived_at).toLocaleString()}</td><td>{new Date(entry.expires_at).toLocaleString()}</td>
          <td>{canWrite && <button type="button" className="tool-btn tool-btn-ghost ip-row-btn" disabled={pending !== null} onClick={() => setReview(entry)}>Review restore</button>}</td>
        </tr>)}</tbody>
      </table></div>}
    {canWrite && review && <div className="tool-hint" role="status">
      Restore <strong>{archiveLabel(review)}</strong>{review.resource_type === "subnet" ? ` with ${(review.snapshot.addresses || []).length} addresses and ${(review.snapshot.dhcpPools || []).length} DHCP pools` : ""}?
      <div className="tool-actions"><button type="button" className="tool-btn tool-btn-primary" onClick={() => restore(review)} disabled={pending !== null}>{pending !== null ? "Restoring…" : "Restore record"}</button><button type="button" className="tool-btn tool-btn-ghost" onClick={() => setReview(null)} disabled={pending !== null}>Cancel</button></div>
    </div>}
  </div>;
}
