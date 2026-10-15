import React,{useEffect,useState} from 'react';
import {saveResource,deleteResource} from './api.js';
export default function ResourceForm({kind,entity,dataCenterId,onSaved,onCancel,onDirty,onBusy}) {
  const [draft,setDraft]=useState({name:entity?.name||'',description:entity?.description||'',heightU:entity?.heightU||42});
  const [busy,setBusy]=useState(false),[error,setError]=useState(null),[confirm,setConfirm]=useState(false);
  const isRack=kind==='racks';
  useEffect(()=>{onDirty(draft.name!==(entity?.name||'')||draft.description!==(entity?.description||'')||(isRack&&draft.heightU!==(entity?.heightU||42)));},[draft,entity,isRack,onDirty]);
  const submit=async(event,remove=false)=>{
    event?.preventDefault();setError(null);setBusy(true);onBusy(true);
    try{
      const result=remove?await deleteResource(kind,entity.id,{expectedVersion:entity.version,confirmDelete:true}):await saveResource(kind,{name:draft.name.trim(),description:draft.description.trim()||null,...(isRack?{heightU:draft.heightU,...(!entity?{dataCenterId}:{})}:{}),...(entity?{expectedVersion:entity.version}:{})},entity?.id);
      onSaved(result,kind);
    }catch(failure){setError(failure.message);}
    finally{setBusy(false);onBusy(false);}
  };
  return <form className="di-resource-form tool-panel" onSubmit={submit}><h3>{entity?'Edit':'Add'} {isRack?'rack':'data center'}</h3><fieldset disabled={busy} className="di-form-fields">
    <div className="di-fields"><label>Name<input className="tool-input" maxLength={100} required value={draft.name} onChange={e=>setDraft(old=>({...old,name:e.target.value}))}/></label>{isRack&&<label>Rack height (U)<input className="tool-input" type="number" min={1} max={100} step={1} required value={draft.heightU} onChange={e=>setDraft(old=>({...old,heightU:Number(e.target.value)}))}/></label>}</div>
    <label>Description<textarea className="tool-textarea" maxLength={500} value={draft.description} onChange={e=>setDraft(old=>({...old,description:e.target.value}))}/></label>
    <button className="tool-btn tool-btn-primary">{busy?'Saving…':'Save location'}</button><button type="button" className="tool-btn tool-btn-ghost" onClick={onCancel}>Close location</button>
    {entity&&!confirm&&<button type="button" className="tool-btn tool-btn-ghost" onClick={()=>setConfirm(true)}>Delete {isRack?'rack':'data center'}</button>}
    {confirm&&<div className="di-delete-review" role="region" aria-label="Location deletion review"><p>Delete {entity.name}? A rack must be empty; a data center must have no racks.</p><button type="button" className="tool-btn tool-btn-primary" onClick={()=>submit(null,true)}>Confirm location deletion</button><button type="button" className="tool-btn tool-btn-ghost" onClick={()=>setConfirm(false)}>Cancel deletion</button></div>}
  </fieldset>{error&&<p role="alert" className="tool-error">{error} Close and reopen this form after reloading if another user changed this location.</p>}</form>;
}
