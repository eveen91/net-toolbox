import React,{useEffect,useState} from 'react';
import {placeDevice} from './api.js';
import LocationFields from './LocationFields.jsx';

export default function PlacementEditor({device,onSaved,onCancel,onDirty,onBusy}) {
  const [draft,setDraft]=useState({...device,heightU:device.heightU??1});
  const [error,setError]=useState(null),[busy,setBusy]=useState(false);
  useEffect(()=>{onDirty(draft.rackId!==device.rackId||draft.rackPosition!==device.rackPosition||draft.heightU!==device.heightU);},[draft,device,onDirty]);
  const save=async(event)=>{
    event.preventDefault();setError(null);setBusy(true);onBusy(true);
    try{const result=await placeDevice(device.id,{expectedVersion:device.version,rackId:draft.rackId||null,rackPosition:draft.rackId?draft.rackPosition:null,heightU:draft.heightU});onSaved(result);}
    catch(failure){setError(failure.message);}
    finally{setBusy(false);onBusy(false);}
  };
  return <form className="di-placement" onSubmit={save}><h3>Place {device.name}</h3><LocationFields draft={draft} disabled={busy} deviceAccess={false} fixedHeight={device.deviceType==='cable-management'} onChange={patch=>setDraft(old=>({...old,...patch}))}/>
    {error&&<p role="alert" className="tool-error">{error} Close this editor and reload the rack to review current data if another user changed it.</p>}
    <button className="tool-btn tool-btn-primary" disabled={busy}>{busy?'Saving…':'Save placement'}</button><button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={onCancel}>Close placement</button>
  </form>;
}
