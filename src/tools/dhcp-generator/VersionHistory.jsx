import React, { useEffect, useRef, useState } from 'react';
import { listVersions, getVersion, compareVersions, downloadArtifact } from './api.js';

export default function VersionHistory({ item, refreshKey, busy, onRestore, onError }) {
  const [page, setPage] = useState({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const [selected, setSelected] = useState(null);
  const [comparison, setComparison] = useState([]);
  const [diff, setDiff] = useState(null);
  const [pending, setPending] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    const ticket = ++sequence.current;
    setLoading(true); setError(null);
    listVersions(item.id, offset).then(result => { if (sequence.current === ticket) setPage(result); })
      .catch(e => { if (sequence.current === ticket) setError(e.message); })
      .finally(() => { if (sequence.current === ticket) setLoading(false); });
    return () => { sequence.current++; };
  }, [item.id, offset, refreshKey, retry]);
  const work = async action => {
    if (pending || busy) return;
    const ticket = sequence.current;
    setPending(true);
    try { await action(ticket); } catch (e) { if (sequence.current === ticket) onError(e); }
    finally { if (sequence.current === ticket) setPending(false); }
  };
  const choose = version => work(async ticket => { const data = await getVersion(item.id, version.id); if (sequence.current === ticket) setSelected(data); });
  const toggle = version => {
    setDiff(null);
    setComparison(previous => previous.some(value => value.id === version.id) ? previous.filter(value => value.id !== version.id) : [...previous.slice(-1), version]);
  };
  return <section aria-label="Published DHCP versions">
    <div className="dhcp-section-heading"><div><h3>Published versions</h3><p className="tool-hint">Artifacts and their snapshots are immutable. Restore copies a version into the working draft.</p></div>
      <button className="tool-btn tool-btn-ghost" disabled={busy || pending || comparison.length !== 2} onClick={() => work(async ticket => {
        const [before, after] = [...comparison].sort((a, b) => a.number - b.number);
        const result = await compareVersions(item.id, before.id, after.id); if (sequence.current === ticket) setDiff(result);
      })}>Compare selected versions</button></div>
    {error && <div className="tool-error" role="alert">{error}<button className="tool-btn tool-btn-ghost" onClick={() => setRetry(value => value + 1)}>Retry versions</button></div>}
    {loading ? <p role="status">Loading versions…</p> : !page.total && !error ? <div className="tool-empty">No published versions. Save and validate a draft, then publish it with a description.</div> : <>
      <div className="tool-table-wrap"><table className="tool-table dhcp-history-table"><thead><tr><th>Select</th><th>Version</th><th>Description</th><th>Author / created</th><th>Actions</th></tr></thead>
        <tbody>{page.items.map(version => <tr key={version.id}>
          <td data-label="Compare"><input type="checkbox" aria-label={`Select version ${version.number} for comparison`} checked={comparison.some(value => value.id === version.id)} disabled={busy || pending} onChange={() => toggle(version)} /></td>
          <td data-label="Version">v{version.number}<div className="tool-hint">Draft r{version.draftRevision}</div></td>
          <td data-label="Description">{version.description}</td><td data-label="Created">{version.actorName || 'Open mode'}<div className="tool-hint">{new Date(version.createdAt).toLocaleString()}</div></td>
          <td data-label="Actions"><div className="dhcp-row-actions"><button className="tool-btn tool-btn-ghost" disabled={busy || pending} onClick={() => choose(version)}>Details</button>
            <button className="tool-btn tool-btn-ghost" disabled={busy || pending} onClick={() => work(() => downloadArtifact(item.id, version))}>Download</button>
            <button className="tool-btn tool-btn-ghost" disabled={busy || pending} onClick={() => onRestore(version)}>Restore draft</button></div></td>
        </tr>)}</tbody></table></div>
      <div className="dhcp-pagination"><span>{offset + 1}–{Math.min(offset + page.items.length, page.total)} of {page.total}</span>
        <button className="tool-btn tool-btn-ghost" disabled={busy || pending || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Previous</button>
        <button className="tool-btn tool-btn-ghost" disabled={busy || pending || offset + 20 >= page.total} onClick={() => setOffset(value => value + 20)}>Next</button></div>
    </>}
    {selected && <div className="dhcp-version-detail"><h3>Version {selected.number}</h3><p>{selected.description}</p>
      <p className="tool-hint">Gaia {selected.profile} · Generator {selected.generatorVersion} · {selected.artifactBytes} bytes · {selected.report.syntax_status}</p>
      <label className="dhcp-field">SHA-256<input className="tool-input" readOnly value={selected.sha256} /></label>
      <details><summary>Configuration snapshot</summary><pre className="dhcp-code">{JSON.stringify(selected.configuration, null, 2)}</pre></details>
    </div>}
    {diff && <section aria-label="Version differences"><h3>Version {diff.before} → {diff.after}</h3><pre className="dhcp-code">{diff.text || 'No artifact differences.'}</pre><details><summary>Configuration JSON differences</summary><pre className="dhcp-code">{diff.configurationText || 'No configuration differences.'}</pre></details></section>}
  </section>;
}
