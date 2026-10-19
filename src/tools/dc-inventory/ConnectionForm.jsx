import React,{useEffect,useState} from 'react';
import {listDevices,getDevicePorts,connectPorts} from './api.js';
import {portDescription,compatiblePorts} from '../device-visualization/logic.js';
import {locationText} from './connectionLayout.js';
function usePorts(id,revision) {
  const [state,setState]=useState({});
  useEffect(()=>{let active=true;setState({loading:!!id});if(id)getDevicePorts(id).then(data=>{if(active)setState({data});}).catch(error=>{if(active)setState({error:error.message});});return()=>{active=false;};},[id,revision]);
  return state;
}
export default function ConnectionForm({rack,onSaved,onCancel,onDirty,onBusy}) {
  const [sourceId,setSourceId]=useState(''),[targetId,setTargetId]=useState(''),[sourcePort,setSourcePort]=useState(''),[targetPort,setTargetPort]=useState('');
  const [query,setQuery]=useState(''),[offset,setOffset]=useState(0),[page,setPage]=useState(null),[pageError,setPageError]=useState(null);
  const [label,setLabel]=useState(''),[error,setError]=useState(null),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
  const source=usePorts(sourceId,revision),target=usePorts(targetId,revision);
  useEffect(()=>{onDirty(!!(sourceId||targetId||label));},[sourceId,targetId,label,onDirty]);
  useEffect(()=>{let active=true;setPage(null);setPageError(null);const timer=setTimeout(()=>listDevices({query,offset,limit:25}).then(data=>{if(active)setPage(data);}).catch(error=>{if(active)setPageError(error.message);}),200);return()=>{active=false;clearTimeout(timer);};},[query,offset,revision]);
  const save=async event=>{
    event.preventDefault();if(!source.data||!target.data)return;setBusy(true);onBusy(true);setError(null);
    try{await connectPorts({sourcePortId:Number(sourcePort),targetPortId:Number(targetPort),sourceVersion:source.data.device.version,targetVersion:target.data.device.version,label:label.trim()||null});onSaved();}
    catch(failure){setError(failure.message);}
    finally{setBusy(false);onBusy(false);}
  };
  const portField=(title,state,value,change)=><label>{title}<select aria-label={title} className="tool-input" required value={value} disabled={!state.data||state.loading} onChange={event=>change(event.target.value)}><option value="">Choose a free port</option>{state.data?.items.filter(port=>title!=='Destination port'||!sourcePort||compatiblePorts(source.data?.items.find(item=>item.id===Number(sourcePort)),[port]).length).map(port=><option key={port.id} value={port.id} disabled={!!port.connectionId}>{port.name} · {portDescription(port)}{port.connectionId?' · connected':''}</option>)}</select>{state.loading&&<span role="status">Loading ports…</span>}{state.error&&<span role="alert">{state.error}</span>}{state.data&&!state.data.items.length&&<span>No network ports on this device.</span>}</label>;
  return <form className="di-connection-form di-placement" onSubmit={save}><h3>Add physical connection</h3><p className="tool-hint">Choose both cable ends. Existing “Leads to” notes remain separate.</p><fieldset disabled={busy} className="di-form-fields"><div className="di-fields">
    <section><h4>Selected rack · {rack.name}</h4><label>Source device<select aria-label="Source device" className="tool-input" required value={sourceId} onChange={event=>{setSourceId(event.target.value);setSourcePort('');}}><option value="">Choose a device</option>{rack.devices.filter(d=>d.deviceType!=='cable-management').map(d=><option key={d.id} value={d.id}>{d.name} · U{d.rackPosition}</option>)}</select></label>{portField('Source port',source,sourcePort,value=>{setSourcePort(value);setTargetPort('');})}</section>
    <section><h4>Destination · any rack or unassigned</h4><label>Find destination device<input className="tool-input" type="search" maxLength={100} value={query} onChange={event=>{setQuery(event.target.value);setOffset(0);setTargetId('');setTargetPort('');}}/></label><label>Destination device<select aria-label="Destination device" className="tool-input" required disabled={!page} value={targetId} onChange={event=>{setTargetId(event.target.value);setTargetPort('');}}><option value="">Choose a device</option>{page?.items.filter(d=>d.deviceType!=='cable-management'&&d.id!==Number(sourceId)).map(d=><option key={d.id} value={d.id}>{d.name} · {locationText(d)}</option>)}</select></label>{pageError&&<p role="alert">{pageError}</p>}{!page&&!pageError&&<p role="status">Loading devices…</p>}<div className="di-actions"><button type="button" className="tool-btn tool-btn-ghost" disabled={!offset||!page} onClick={()=>{setOffset(v=>v-25);setTargetId('');setTargetPort('');}}>Previous devices</button><button type="button" className="tool-btn tool-btn-ghost" disabled={!page||offset+25>=page.total} onClick={()=>{setOffset(v=>v+25);setTargetId('');setTargetPort('');}}>Next devices</button></div>{portField('Destination port',target,targetPort,setTargetPort)}</section>
    <label>Cable label (optional)<input className="tool-input" maxLength={100} value={label} onChange={event=>setLabel(event.target.value)}/></label>
  </div>{error&&<p className="tool-error" role="alert">{error} Your selections are retained; reload ports to review current availability.</p>}<div className="di-actions"><button className="tool-btn tool-btn-primary" disabled={!source.data||!target.data||!sourcePort||!targetPort||sourceId===targetId}>{busy?'Saving…':'Connect ports'}</button><button type="button" className="tool-btn tool-btn-ghost" onClick={()=>{setSourcePort('');setTargetPort('');setRevision(v=>v+1);}}>Reload ports</button><button type="button" className="tool-btn tool-btn-ghost" onClick={onCancel}>Cancel connection</button></div></fieldset></form>;
}
