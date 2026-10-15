import React,{useEffect,useState} from 'react';
import {createCablePanel} from './api.js';

export default function CablePanelForm({rack,onDirty,onBusy,onSaved,onCancel}) {
  const [name,setName]=useState('');
  const [position,setPosition]=useState('');
  const defaultName=`${rack.name.slice(0,50)} · Cable management · U${position||'…'}`;
  const [error,setError]=useState(null),[busy,setBusy]=useState(false);
  useEffect(()=>{onDirty(position!==''||name!=='');},[position,name,onDirty]);
  const save=async event=>{
    event.preventDefault();setError(null);setBusy(true);onBusy(true);
    try{onSaved(await createCablePanel({name:(name||defaultName).trim(),rackId:rack.id,rackPosition:Number(position)}));}
    catch(failure){setError(failure.message);}
    finally{setBusy(false);onBusy(false);}
  };
  return <form className="di-placement" onSubmit={save}><h3>Add cable management panel</h3><p className="tool-hint">{rack.dataCenterName} / {rack.name} · Fixed height 1U · No network ports</p>
    <fieldset className="di-form-fields" disabled={busy}><div className="di-fields"><label>Name<input className="tool-input" required maxLength={100} value={name||defaultName} onChange={event=>setName(event.target.value)}/></label><label>Starting U<input className="tool-input" required type="number" min={1} max={rack.heightU} step={1} value={position} onChange={event=>setPosition(event.target.value)}/></label></div>
      <button className="tool-btn tool-btn-primary">{busy?'Adding…':'Add panel'}</button><button type="button" className="tool-btn tool-btn-ghost" onClick={onCancel}>Cancel</button>
    </fieldset>{error&&<p role="alert" className="tool-error">{error}</p>}
  </form>;
}
