import React, { useCallback, useEffect, useRef, useState } from 'react';
import ViewTabs from '../../components/ViewTabs.jsx';
import useUnsavedChanges from '../../components/useUnsavedChanges.js';
import { canLeaveWorkspace } from '../../components/navigation.js';
import ConfigurationEditor from './ConfigurationEditor.jsx';
import VersionHistory from './VersionHistory.jsx';
import { emptyConfiguration, toConfiguration } from './fields.js';
import * as api from './api.js';
import './dhcp-generator.css';

export default function DhcpGenerator() {
  const [list, setList] = useState({ items: [], total: 0 });
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);
  const [item, setItem] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');
  const [screen, setScreen] = useState('configuration');
  const [preview, setPreview] = useState(null);
  const [description, setDescription] = useState('');
  const [audit, setAudit] = useState(null);
  const [auditOffset, setAuditOffset] = useState(0);
  const [auditError, setAuditError] = useState(null);
  const alive = useRef(true);
  const selection = useRef(0);
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(item?.configuration || emptyConfiguration());
  useUnsavedChanges(dirty, busy);
  useEffect(() => { alive.current = true; return () => { alive.current = false; selection.current++; }; }, []);

  useEffect(() => {
    let current = true;
    const timer = setTimeout(() => {
      setListLoading(true); setListError(null);
      api.listConfigurations(query, offset).then(page => { if (current) setList(page); })
        .catch(e => { if (current) setListError(e.message); }).finally(() => { if (current) setListLoading(false); });
    }, query ? 250 : 0);
    return () => { current = false; clearTimeout(timer); };
  }, [query, offset, refreshKey]);

  const reportError = useCallback(e => setError(e), []);
  const select = async id => {
    if (!canLeaveWorkspace()) return;
    const ticket = ++selection.current;
    setLoading(true); setError(null); setPreview(null); setDescription(''); setScreen('configuration');
    setItem(null); setDraft(null); setAudit(null); setAuditOffset(0);
    try {
      const current = await api.getConfiguration(id);
      if (ticket === selection.current) { setItem(current); setDraft(current.configuration); }
    } catch (e) { if (ticket === selection.current) setError(e); }
    finally { if (ticket === selection.current) setLoading(false); }
  };
  const work = async operation => {
    if (busy) return;
    setBusy(true); setError(null); setNotice('');
    try { await operation(); } catch (e) { if (alive.current) setError(e); }
    finally { if (alive.current) setBusy(false); }
  };
  const saved = current => {
    if (!alive.current) return;
    setItem(current); setDraft(current.configuration); setPreview(null);
    setRefreshKey(key => key + 1);
    setNotice(`Saved ${current.name} · draft revision ${current.revision}.`);
  };
  const save = () => work(async () => {
    const configuration = toConfiguration(draft);
    saved(item ? await api.saveConfiguration(item.id, item.revision, configuration) : await api.createConfiguration(configuration));
  });
  const fresh = () => {
    if (!canLeaveWorkspace()) return;
    selection.current++; setLoading(false); setItem(null); setDraft(emptyConfiguration()); setScreen('configuration'); setPreview(null); setError(null); setDescription('');
  };
  const restore = version => {
    if (!canLeaveWorkspace()) return;
    if (!window.confirm(`Replace the working draft with version ${version.number}? Published versions and their artifacts will remain unchanged.`)) return;
    work(async () => { const current = await api.restoreVersion(item.id, item.revision, version.id); saved(current); setScreen('configuration'); });
  };
  const importJSON = event => {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file || !canLeaveWorkspace()) return;
    if (item && !window.confirm(`Replace the saved working draft for ${item.name} with this JSON configuration?`)) return;
    work(async () => {
      if (file.size > 1024 * 1024) throw new Error('JSON configuration exceeds 1 MiB.');
      let configuration;
      try { configuration = JSON.parse(await file.text()); } catch { throw new Error('Choose a valid generator configuration JSON file.'); }
      saved(item ? await api.saveConfiguration(item.id, item.revision, configuration) : await api.createConfiguration(configuration));
      if (alive.current) setScreen('configuration');
    });
  };
  const exportJSON = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(toConfiguration(draft), null, 2)+'\n'], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = 'dhcp-configuration.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  useEffect(() => {
    if (screen !== 'audit' || !item) return;
    let current = true;
    setAudit(null); setAuditError(null);
    api.getAudit(item.id, auditOffset).then(value => { if (current) setAudit(value); })
      .catch(e => { if (current) setAuditError(e.message); });
    return () => { current = false; };
  }, [screen, item?.id, auditOffset, refreshKey]);

  return <div className="dhcp-tool">
    <header className="nt-tool-header dhcp-page-heading"><div><h2>DHCP Generator</h2><p>Prepare Check Point Gaia DHCPv4 configuration and keep immutable published versions.</p></div>
      <button className="tool-btn tool-btn-primary" disabled={busy} onClick={fresh}>New configuration</button></header>
    {notice && <p className="dhcp-notice" role="status">{notice}</p>}
    <div className="dhcp-workspace">
      <aside className="tool-panel dhcp-sidebar" aria-label="DHCP configurations"><label className="dhcp-field">Find firewall<input className="tool-input" type="search" value={query} maxLength={100} onChange={event => { setQuery(event.target.value); setOffset(0); }} /></label>
        {listLoading && <p role="status">Loading configurations…</p>}
        {listError && <div className="tool-error" role="alert">{listError}<button className="tool-btn tool-btn-ghost" onClick={() => setRefreshKey(key => key + 1)}>Retry list</button></div>}
        {!listLoading && !listError && !list.total && <p className="tool-hint">{query ? 'No firewalls match this search.' : 'No configurations yet. Create one or import generator JSON.'}</p>}
        <ul className="dhcp-configuration-list">{list.items.map(current => <li key={current.id}><button className={item?.id === current.id ? 'active' : ''} disabled={busy} aria-pressed={item?.id === current.id} onClick={() => select(current.id)}><strong>{current.name}</strong><span>Gaia {current.profile} · r{current.revision} · {current.subnetCount} subnets</span></button></li>)}</ul>
        <div className="dhcp-pagination"><span>{list.total} configurations</span><button className="tool-btn tool-btn-ghost" disabled={busy || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Previous</button><button className="tool-btn tool-btn-ghost" disabled={busy || offset + 20 >= list.total} onClick={() => setOffset(value => value + 20)}>Next</button></div>
        <label className="dhcp-file-import"><span>Import generator JSON</span><input type="file" accept=".json,application/json" disabled={busy || loading} onChange={importJSON} /></label>
      </aside>
      <section className="tool-panel dhcp-main" aria-label="DHCP workspace">
        {loading && <p role="status">Loading configuration…</p>}
        {error && <div className="tool-error" role="alert">{error.message}{error.status === 409 && <p>Your local draft is preserved. Reload the saved configuration only after reviewing your changes.</p>}
          {item && <button className="tool-btn tool-btn-ghost" disabled={busy} onClick={() => select(item.id)}>Reload saved draft</button>}</div>}
        {!draft && !loading && !error && <div className="tool-empty">Select a firewall or create a configuration to manage subnets, DHCP pools and reservations.</div>}
        {draft && <>
          <div className="dhcp-section-heading"><div><h3>{item?.name || 'New configuration'}</h3><p className="tool-hint">{item ? `Draft revision ${item.revision}` : 'Not saved yet'}{dirty ? ' · Unsaved changes' : ''}</p></div><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={exportJSON}>Export JSON draft</button></div>
          <ViewTabs items={[{ id: 'configuration', label: 'Configuration' }, { id: 'preview', label: 'Validate & publish' }, { id: 'versions', label: 'Versions' }, { id: 'audit', label: 'Audit' }]} value={screen} label="DHCP views" onChange={value => { if (!busy) setScreen(value); }} />
          {screen === 'configuration' && <ConfigurationEditor key={item?.id || 'new'} draft={draft} busy={busy} onChange={value => { setDraft(value); setPreview(null); }} onSave={save} saved={Boolean(item)} />}
          {screen === 'preview' && <section aria-label="DHCP validation and publication"><h3>Validate saved draft</h3><p className="tool-hint">Save your changes before validation. Publication stores a complete configuration snapshot and its generated artifact.</p>
            <button className="tool-btn tool-btn-primary" disabled={busy || !item || dirty} onClick={() => work(async () => { const result = await api.previewConfiguration(item.id, item.revision); if (alive.current) setPreview(result); })}>{busy ? 'Working…' : 'Validate & preview'}</button>
            {(!item || dirty) && <p className="tool-hint">Return to Configuration and save the working draft first.</p>}
            {preview && <><div className="dhcp-validation-report" role="status"><strong>Data validation passed</strong><span>Syntax: {preview.report.syntax_status === 'parser_unavailable' ? 'Not checked — no parser configured' : preview.report.syntax_status}</span><span>Gaia compatibility: not verified on the appliance</span><span>{preview.report.artifact_bytes} bytes · SHA-256 {preview.report.sha256}</span></div>
              <pre className="dhcp-code" tabIndex={0} aria-label="Generated DHCP configuration">{preview.content}</pre>
              <label className="dhcp-field">Version description<textarea className="tool-textarea" maxLength={2000} value={description} disabled={busy} onChange={event => setDescription(event.target.value)} placeholder="Describe this configuration change" /></label>
              <button className="tool-btn tool-btn-primary" disabled={busy || dirty || !description.trim()} onClick={() => work(async () => { const version = await api.publishVersion(item.id, item.revision, description.trim()); if (!alive.current) return; setRefreshKey(key => key + 1); setDescription(''); setScreen('versions'); setNotice(`Published ${item.name} · version ${version.number}.`); })}>Publish version</button>
            </>}
          </section>}
          {screen === 'versions' && (item ? <VersionHistory key={item.id} item={item} refreshKey={refreshKey} busy={busy} onRestore={restore} onError={reportError} /> : <div className="tool-empty">Save a configuration before creating versions.</div>)}
          {screen === 'audit' && <section aria-label="DHCP audit"><h3>Configuration history</h3>{auditError && <p role="alert" className="tool-error">{auditError}<button className="tool-btn tool-btn-ghost" onClick={() => setRefreshKey(value => value + 1)}>Retry audit</button></p>}
            {!item ? <p className="tool-hint">Save a configuration to start its history.</p> : !audit && !auditError ? <p role="status">Loading audit…</p> : audit && <><ol className="dhcp-audit-list">{audit.items.map(entry => <li key={entry.id}><strong>{entry.action.replaceAll('_', ' ')}</strong><span>{entry.actorName || 'Open mode'} · {new Date(entry.createdAt).toLocaleString()}</span><details><summary>Change details</summary><pre className="dhcp-code">{JSON.stringify({ before: entry.oldValue, after: entry.newValue }, null, 2)}</pre></details></li>)}</ol>
              <div className="dhcp-pagination"><span>{audit.total} events</span><button className="tool-btn tool-btn-ghost" disabled={auditOffset === 0} onClick={() => setAuditOffset(value => Math.max(0, value - 20))}>Previous</button><button className="tool-btn tool-btn-ghost" disabled={auditOffset + 20 >= audit.total} onClick={() => setAuditOffset(value => value + 20)}>Next</button></div></>}
          </section>}
        </>}
      </section>
    </div>
  </div>;
}
