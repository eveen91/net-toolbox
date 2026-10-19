import React,{useEffect,useRef,useState} from 'react';
import * as api from './api.js';
import ConfluencePublication from './ConfluencePublication.jsx';

export function previewFrame(content){return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'none'; base-uri 'none'"><style>body{font:14px/1.5 system-ui,sans-serif;color:#172538;background:#fff;padding:16px;overflow-wrap:anywhere}table{border-collapse:collapse;display:block;overflow:auto;max-width:100%}td,th{border:1px solid #cbd5e1;padding:8px;vertical-align:top}pre{white-space:pre-wrap;background:#f1f5f9;padding:12px}h1{font-size:24px}h2{font-size:20px}h3{font-size:16px}a{color:#2563a6}</style></head><body>${content}</body></html>`;}

export default function ConfluencePreview({id,version,kind,locked,onBusy}) {
  const [profiles,setProfiles]=useState(null),[profileId,setProfileId]=useState(''),[history,setHistory]=useState(null),[offset,setOffset]=useState(0),[reload,setReload]=useState(0);
  const [preview,setPreview]=useState(null),[selected,setSelected]=useState('root'),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const alive=useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{
    let active=true;
    Promise.all([api.listConfluenceProfiles(),api.listConfluencePreviews(id,version,offset)]).then(([values,history])=>{if(active){setProfiles(values.items);setHistory(history);setProfileId(current=>values.items.some(p=>String(p.id)===current)?current:String(values.items.find(p=>p.enabled)?.id||''));}}).catch(failure=>{if(active)setError(failure.message);});
    return()=>{active=false;};
  },[id,version,offset,reload]);
  const perform=async task=>{
    if(busy||locked)return;setBusy(true);onBusy(true);setError('');
    try{const result=await task();if(alive.current){setPreview(result);setSelected('root');setReload(value=>value+1);}}
    catch(failure){if(alive.current)setError(failure.message);}finally{if(alive.current){setBusy(false);onBusy(false);}}
  };
  if(kind!=='published')return <div className="tool-panel"><h3>Confluence preview</h3><p className="tool-hint">Publish the reviewed document locally, then preview that immutable published version for Confluence.</p></div>;
  const profile=profiles?.find(p=>String(p.id)===profileId),page=preview?.pages.find(p=>p.key===selected);
  return <section className="tool-panel dc-doc-confluence-preview" aria-label="Confluence publication preview"><h3>Confluence publication preview · version {version}</h3>
    <p className="tool-hint">Compare the published version with your configured Confluence space.</p>
    {error&&<p role="alert" className="tool-error">{error} <button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>setReload(value=>value+1)}>Reload Confluence destinations</button></p>}
    {!profiles?<p role="status">Loading Confluence destinations…</p>:!profiles.length?<p className="tool-hint">Configure a destination in Confluence connections. Managing connections requires Documentation Manage Confluence permission.</p>:<div className="dc-doc-version-actions"><label>Confluence destination<select className="tool-input" aria-label="Confluence destination" disabled={busy||locked} value={profileId} onChange={event=>setProfileId(event.target.value)}><option value="">Choose destination</option>{profiles.map(p=><option key={p.id} value={p.id} disabled={!p.enabled}>{p.name} · {p.spaceKey}{!p.enabled?' · Disabled':''}</option>)}</select></label>
      <button type="button" className="tool-btn tool-btn-primary" disabled={busy||locked||!profile?.enabled} onClick={()=>perform(()=>api.prepareConfluencePreview(id,version,profile.id,profile.version))}>{busy?'Reading Confluence…':'Prepare Confluence preview'}</button></div>}
    {history?.items.length>0&&<details><summary>Saved Confluence previews ({history.total})</summary><ul className="dc-doc-version-list">{history.items.map(item=><li key={item.id}><span>{item.profileName} · {new Date(item.createdAt).toLocaleString()} · {item.hasConflicts?'Conflicts':'No detected conflicts'}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>perform(()=>api.getConfluencePreview(id,version,item.id))}>Open preview {new Date(item.createdAt).toLocaleString()}</button></li>)}</ul>{history.total>20&&<div className="dc-doc-pager"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||!offset} onClick={()=>setOffset(value=>value-20)}>Previous Confluence previews</button><span>{offset+1}–{Math.min(offset+20,history.total)} of {history.total}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||offset+20>=history.total} onClick={()=>setOffset(value=>value+20)}>Next Confluence previews</button></div>}</details>}
    {preview&&<><div className="dc-doc-preview-summary" role="status"><strong>{preview.hasConflicts?'Conflicts require review':'Read-only plan prepared'}</strong><p>{preview.profileName} · {preview.baseUrl} · Space {preview.spaceKey}{preview.parentPageId?` · Parent ${preview.parentPageId}`:' · Space root'}</p><p>{preview.pages.length} pages · {preview.pages.reduce((n,p)=>n+p.attachments.length,0)} PNG attachments · Captured {new Date(preview.createdAt).toLocaleString()}</p>{preview.profileChanged&&<p className="tool-error">The connection changed or was disabled after this preview. Prepare a new preview with the current destination.</p>}{preview.advisories.map((value,i)=><p className="tool-hint" key={i}>{value}</p>)}</div>
      <label>Planned page<select className="tool-input" aria-label="Planned page" value={selected} onChange={event=>setSelected(event.target.value)}>{preview.pages.map(p=><option key={p.key} value={p.key}>{p.parentKey?'↳ ':''}{p.label} · {p.action}</option>)}</select></label>
      {page&&<div className="dc-doc-confluence-page"><h4>{page.title}</h4><p>Action: <strong>{page.action}</strong> · {page.parentKey?`Parent: ${preview.pages.find(p=>p.key===page.parentKey)?.label||page.parentKey}`:'Document root'}{page.remoteVersion?` · Remote version ${page.remoteVersion}`:''}</p>{page.destinationUrl&&<a href={page.destinationUrl} target="_blank" rel="noreferrer">Open destination page</a>}
        {!!page.issues.length&&<ul className="tool-error" aria-label="Page conflicts">{page.issues.map((issue,i)=><li key={i}>{issue}</li>)}</ul>}{page.advisories.map((value,i)=><p key={i} className="tool-hint">{value}</p>)}
        <iframe className="dc-doc-confluence-frame" title={`Planned content: ${page.title}`} sandbox="" srcDoc={previewFrame(page.previewHtml)}/>
        {!!page.attachments.length&&<><h4>Planned PNG attachments</h4><ul className="dc-doc-attachment-list">{page.attachments.map(asset=><li key={asset.filename}><strong>{asset.title} · {asset.action}</strong><span>{asset.filename} · {asset.bytes} bytes</span>{asset.issues.map((issue,i)=><p className="tool-error" key={i}>{issue}</p>)}</li>)}</ul><p className="tool-hint">The frozen images are available in Saved diagrams below and in the ZIP export.</p></>}
        <details><summary>Content diff against Confluence</summary>{page.diffTruncated&&<p className="tool-hint">Diff limited to 2,000 lines. Full planned storage is below.</p>}<pre className="dc-doc-diff">{page.diff||'No content changes.'}</pre></details>
        <details><summary>Confluence storage representation</summary><pre className="dc-doc-diff">{page.storage}</pre></details>
      </div>}
      {!!preview.retainedPages.length&&<p className="tool-hint">{preview.retainedPages.length} previously mapped pages are outside this hierarchy and will be retained. No deletions are planned.</p>}
    </>}
    <ConfluencePublication id={id} version={version} plan={preview} locked={locked||busy} onBusy={onBusy}/>
  </section>;
}
