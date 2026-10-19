import React,{useState} from 'react';
import {canDocument} from './permissions.js';
import * as api from './api.js';
import SourceTables,{Provenance} from './SourceTables.jsx';

export default function DocumentWorkflow({record,dirty,locked,onBusy,onUpdated,user}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[description,setDescription]=useState(''),[preview,setPreview]=useState(null);
 const run=async operation=>{if(busy||locked)return;setBusy(true);onBusy(true);setError('');try{await operation();}catch(failure){setError(failure.message);}finally{setBusy(false);onBusy(false);}};
 const transition=action=>run(async()=>{onUpdated(await api.transition(record.id,record.version,action,description));});
 if(!record)return null;
 const validation=record.validation||{blocking:[],advisories:[]};
 return <section className="tool-panel dc-doc-workflow" aria-label="Document workflow"><div className="dc-doc-version-actions"><strong>Status: {record.status||'draft'}</strong>{record.publishedVersion&&<span>Latest published version {record.publishedVersion}</span>}</div>
 {validation.blocking.length>0&&<details><summary>{validation.blocking.length} fields required for review</summary><ul>{validation.blocking.map((issue,index)=><li key={index}>{issue.message}</li>)}</ul></details>}
 {dirty&&<p className="tool-hint">Save changes before review, publication or infrastructure refresh.</p>}
 <fieldset className="dc-doc-fieldset" disabled={busy||locked||dirty}>
 {canDocument(user,'write')&&record.status==='draft'&&<div className="dc-doc-version-actions"><button type="button" className="tool-btn tool-btn-primary" onClick={()=>transition('submit')}>Submit for review</button>{record.form.scopeSpec?.kind!=='none'&&record.form.scopeSpec?.id&&<button type="button" className="tool-btn tool-btn-ghost" onClick={()=>run(async()=>setPreview(await api.previewRefresh(record.id,record.version)))}>Preview infrastructure changes</button>}</div>}
 {record.status==='review'&&canDocument(user,'publish')&&<><label>Review / publication note (optional)<input className="tool-input" maxLength={1000} value={description} onChange={event=>setDescription(event.target.value)}/></label><button type="button" className="tool-btn tool-btn-primary" onClick={()=>transition('publish')}>Publish reviewed version</button></>}
 {record.status!=='draft'&&canDocument(user,'write')&&<button type="button" className="tool-btn tool-btn-ghost" onClick={()=>transition('draft')}>{record.status==='published'?'Start new draft':'Return to draft'}</button>}
 </fieldset>
 {error&&<p role="alert" className="tool-error">{error}</p>}
 {preview&&<div className="dc-doc-refresh"><h4>Infrastructure changes</h4>{preview.changes.length?<ul>{preview.changes.map(change=><li key={change.id}>{change.title}: {change.before} → {change.after} rows (content may also have changed)</li>)}</ul>:<p>No table content changes.</p>}<Provenance snapshot={preview.snapshot}/><details><summary>Inspect refreshed tables</summary><SourceTables snapshot={preview.snapshot}/></details><div className="dc-doc-version-actions"><button type="button" className="tool-btn tool-btn-primary" disabled={busy||locked||dirty} onClick={()=>run(async()=>{onUpdated(await api.applyRefresh(record.id,record.version,preview.snapshot.digest));})}>Apply infrastructure refresh</button><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>setPreview(null)}>Close preview</button></div></div>}
 </section>;
}
