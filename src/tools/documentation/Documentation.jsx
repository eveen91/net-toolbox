import React,{useEffect,useRef,useState} from 'react';
import {useAuth} from '../../auth/AuthContext.jsx';
import useUnsavedChanges from '../../components/useUnsavedChanges.js';
import DCForm from './DCForm.jsx';
import ConfluenceProfiles from './ConfluenceProfiles.jsx';
import {canDocument} from './permissions.js';
import * as api from './api.js';
import './documentation.css';

export default function Documentation() {
  const {user}=useAuth();const canWrite=canDocument(user,'write');
  const [showDocuments,setShowDocuments]=useState(true);
  const [query,setQuery]=useState(''),[status,setStatus]=useState(''),[template,setTemplate]=useState('');
  const [view,setView]=useState('edit');
  const [activeTab,setActiveTab]=useState('general');
  const [record,setRecord]=useState(null),[generation,setGeneration]=useState(0),[page,setPage]=useState(null);
  const [offset,setOffset]=useState(0),[reload,setReload]=useState(0),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[listError,setListError]=useState(''),[notice,setNotice]=useState('');
  const request=useRef(0),alive=useRef(true);
  useUnsavedChanges(dirty,busy);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;request.current++;};},[]);
  useEffect(()=>{let active=true;setListError('');setPage(null);const timer=setTimeout(()=>api.listForms(offset,{query,status,template}).then(result=>{if(active)setPage(result);}).catch(failure=>{if(active)setListError(failure.message);}),200);return()=>{active=false;clearTimeout(timer);};},[offset,reload,query,status,template]);
  const guard=()=>!busy&&(!dirty||window.confirm('Discard unsaved DC documentation changes?'));
  const open=async id=>{
    if(!guard())return;
    const ticket=++request.current;setBusy(true);setError('');setNotice('');
    try {const result=await api.getForm(id);if(alive.current&&ticket===request.current){setShowDocuments(false);setRecord(result);setActiveTab('general');setView('edit');setDirty(false);setGeneration(value=>value+1);}}
    catch(failure){if(alive.current)setError(failure.message);}finally{if(alive.current)setBusy(false);}
  };
  const updated=result=>{if(!alive.current)return;setRecord(result);setDirty(false);setReload(value=>value+1);setGeneration(value=>value+1);setNotice('Document updated.');};
  const save=async form=>{
    const result=await api.saveForm(form,record);
    if(!alive.current)return;
    setShowDocuments(false);setRecord(result);setDirty(false);setNotice('Document saved.');setReload(value=>value+1);setGeneration(value=>value+1);
  };
  return <div className="dc-doc-tool">
    <div className="nt-tool-header dc-doc-header"><div><h2>Documentation</h2><p>Network, device and operational documentation, organized into chapters.</p></div>{canWrite&&<button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>{if(guard()){setShowDocuments(false);setRecord(null);setActiveTab('general');setView('edit');setDirty(false);setNotice('');setError('');setGeneration(value=>value+1);}}}>New document</button>}</div>
    {canDocument(user,'admin')&&<ConfluenceProfiles/>}
    <details className="tool-panel dc-doc-saved" open={showDocuments} onToggle={event=>setShowDocuments(event.currentTarget.open)}><summary>Saved documentation{page?` (${page.total})`:''}</summary><div className="dc-doc-list-filters"><label>Search documents<input className="tool-input" value={query} maxLength={100} onChange={event=>{setQuery(event.target.value);setOffset(0);}}/></label><label>Status<select className="tool-input" aria-label="Document status filter" value={status} onChange={event=>{setStatus(event.target.value);setOffset(0);}}><option value="">All statuses</option><option value="draft">Draft</option><option value="review">In review</option><option value="published">Published</option></select></label><label>Type<select className="tool-input" aria-label="Document type filter" value={template} onChange={event=>{setTemplate(event.target.value);setOffset(0);}}><option value="">All types</option><option value="network">Network / DC</option><option value="switch">Switch</option><option value="firewall">Firewall</option><option value="runbook">Runbook</option></select></label></div>
      {listError?<p role="alert" className="tool-error">{listError} <button type="button" className="tool-btn tool-btn-ghost" onClick={()=>setReload(value=>value+1)}>Retry</button></p>:!page?<p role="status">Loading saved documents…</p>:<>
        {!page.items.length&&<p className="tool-hint">No saved documents yet.</p>}
        <ul>{page.items.map(item=><li key={item.id} className="dc-doc-saved-row" data-editing={item.id===record?.id}><div><strong>{item.title}</strong><span>{item.templateId} · {item.status} · {item.dcName} · {new Date(item.updatedAt).toLocaleString()}{item.id===record?.id?' · Open':''}</span></div><button type="button" disabled={busy} className="tool-btn tool-btn-ghost" aria-label={`${canWrite?'Edit':'View'} ${item.title}`} onClick={()=>open(item.id)}>{canWrite?'Edit':'View'}</button></li>)}</ul>
        {page.total>20&&<div className="dc-doc-pager"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||!offset} onClick={()=>setOffset(value=>value-20)}>Previous</button><span>{offset+1}–{Math.min(offset+20,page.total)} of {page.total}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||offset+20>=page.total} onClick={()=>setOffset(value=>value+20)}>Next</button></div>}
      </>}
    </details>
    {error&&<p role="alert" className="tool-error">{error}</p>}
    {notice&&<p role="status" className="dc-doc-notice">{notice}</p>}
    {record&&<div className="tool-panel dc-doc-editing" aria-label="Editing documentation"><strong>{canWrite&&record.status==='draft'?'Editing':'Document'}: {record.form.title}</strong><span>{record.form.dcName} · Document revision {record.version}</span></div>}
    <DCForm key={generation} record={record} author={user?.username} user={user} onUpdated={updated} onDirty={setDirty} onBusy={setBusy} onSave={save} locked={busy} activeTab={activeTab} onTabChange={setActiveTab} view={view} onViewChange={setView}/>
  </div>;
}
