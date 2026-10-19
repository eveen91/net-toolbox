import React,{useEffect,useRef,useState} from 'react';
import useUnsavedChanges from '../../components/useUnsavedChanges.js';
import * as api from './api.js';

const empty=()=>({name:'',baseUrl:'',spaceKey:'',parentPageId:'',token:'',caPem:'',timeoutSeconds:10,authMode:'pat',enabled:true});
export function profilePayload(form){return {...form,parentPageId:form.parentPageId||null,token:form.token||null,timeoutSeconds:Number(form.timeoutSeconds)};}

export function ConnectionCheck({result}) {
  if(!result)return null;
  return <div className={result.ok?'dc-doc-notice':'tool-error'} role={result.ok?'status':'alert'}>
    <strong>{result.ok?'Read-only connection test passed':'Connection test failed'}{result.profileName?` · ${result.profileName}`:''}</strong>
    {result.ok?<p>Confluence {result.serverVersion} · {result.identity} · {result.spaceName} ({result.spaceKey}){result.parentTitle?` · Parent: ${result.parentTitle}`:''}. Storage and attachment reads verified. Publication and upload permissions have not been tested.</p>:<p>{result.message}</p>}
    <p className="tool-hint">Checked {new Date(result.checkedAt).toLocaleString()} · Profile revision {result.profileVersion}</p>
  </div>;
}

export default function ConfluenceProfiles(){
  const [page,setPage]=useState(null),[record,setRecord]=useState(null),[form,setForm]=useState(empty),[editing,setEditing]=useState(false);
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[result,setResult]=useState(null),[reload,setReload]=useState(0);
  const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useUnsavedChanges(dirty,busy);
  useEffect(()=>{let active=true;api.listConfluenceProfiles().then(value=>{if(active)setPage(value);}).catch(failure=>{if(active)setError(failure.message);});return()=>{active=false;};},[reload]);
  const perform=async task=>{
    if(busy)return;setBusy(true);setError('');setNotice('');
    try{await task();}catch(failure){if(alive.current)setError(failure.message);}finally{if(alive.current)setBusy(false);}
  };
  const guard=()=>!busy&&(!dirty||window.confirm('Discard unsaved Confluence connection changes?'));
  const edit=item=>{if(guard())perform(async()=>{
    const value=await api.getConfluenceProfile(item.id);
    if(alive.current){setRecord(value);setForm({...empty(),...Object.fromEntries(Object.keys(empty()).map(key=>[key,key==='token'?'':value[key]??empty()[key]]))});setEditing(true);setDirty(false);setResult(value.lastCheck);}
  });};
  const change=(key,value)=>{setForm(current=>({...current,[key]:value}));setDirty(true);setResult(null);};
  return <details className="tool-panel dc-doc-confluence-profiles"><summary>Confluence connections</summary>
    <p className="tool-hint">Configure the local Server / Data Center destination. This phase tests reads and prepares a publication preview; it does not modify Confluence pages or attachments.</p>
    {error&&<p role="alert" className="tool-error">{error} <button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>setReload(value=>value+1)}>Reload connections</button></p>}
    {notice&&<p role="status" className="dc-doc-notice">{notice}</p>}
    {!page?<p role="status">Loading Confluence connections…</p>:<ul className="dc-doc-version-list">{!page.items.length&&<li>No connections configured.</li>}{page.items.map(item=><li key={item.id}><div><strong>{item.name}{!item.enabled?' · Disabled':''}</strong><span>{item.baseUrl} · {item.spaceKey}</span></div><div className="dc-doc-version-actions">
      <button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>edit(item)}>Edit connection {item.name}</button>
      <button type="button" className="tool-btn tool-btn-ghost" disabled={busy||dirty||!item.enabled} onClick={()=>perform(async()=>{const value=await api.checkConfluenceProfile(item.id,item.version);if(alive.current){setResult(value);setReload(v=>v+1);}})}>Test connection {item.name}</button>
    </div></li>)}</ul>}
    <button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>{if(guard()){setRecord(null);setForm(empty());setEditing(true);setDirty(false);setResult(null);setError('');}}}>Add Confluence connection</button>
    {editing&&<form className="dc-doc-connection-form" onSubmit={event=>{event.preventDefault();perform(async()=>{
      const value=await api.saveConfluenceProfile(profilePayload(form),record);
      if(alive.current){setRecord(value);setForm(current=>({...current,token:''}));setDirty(false);setResult(null);setReload(v=>v+1);setNotice('Confluence connection saved. The token is stored encrypted.');}
    });}}><fieldset disabled={busy}><legend>{record?'Edit Confluence connection':'New Confluence connection'}</legend><div className="dc-doc-fields">
      <label>Connection name<input className="tool-input" required maxLength={100} value={form.name} onChange={e=>change('name',e.target.value)}/></label>
      <label>Confluence base URL<input className="tool-input" required type="url" placeholder="https://confluence.example.local/confluence" maxLength={500} value={form.baseUrl} onChange={e=>change('baseUrl',e.target.value)}/></label>
      <label>Space key<input className="tool-input" required maxLength={255} value={form.spaceKey} onChange={e=>change('spaceKey',e.target.value)}/></label>
      <label>Parent page ID (optional)<input className="tool-input" inputMode="numeric" pattern="[1-9][0-9]*" maxLength={30} value={form.parentPageId} onChange={e=>change('parentPageId',e.target.value)}/></label>
      <label>Personal access token{record?.hasToken?' (leave blank to keep saved token)':' *'}<input className="tool-input" type="password" autoComplete="new-password" required={!record?.hasToken} maxLength={8192} value={form.token} onChange={e=>change('token',e.target.value)}/></label>
      <label>Request timeout (seconds)<input className="tool-input" type="number" required min={3} max={30} value={form.timeoutSeconds} onChange={e=>change('timeoutSeconds',e.target.value)}/></label>
      <label className="dc-doc-connection-ca">Trusted internal CA certificates (PEM, optional)<textarea className="tool-input" rows={4} maxLength={65536} placeholder="-----BEGIN CERTIFICATE-----" value={form.caPem} onChange={e=>change('caPem',e.target.value)}/></label>
      <label><input type="checkbox" checked={form.enabled} onChange={e=>change('enabled',e.target.checked)}/> Connection enabled</label>
    </div><p className="tool-hint">HTTPS certificate verification is always enabled. Enter public CA certificates only. PAT authentication requires Confluence 7.9 or later; the test detects the version and available REST reads.</p>
    <div className="dc-doc-version-actions"><button type="submit" className="tool-btn tool-btn-primary" disabled={busy}>{busy?'Processing…':'Save Confluence connection'}</button><button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>{if(guard()){setEditing(false);setDirty(false);setForm(empty());setRecord(null);}}}>Close connection editor</button></div></fieldset></form>}
    <ConnectionCheck result={result}/>
  </details>;
}
