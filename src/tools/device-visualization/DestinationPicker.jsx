import React,{useEffect,useRef,useState} from 'react';
import {listDevices,getDevice} from './api.js';
import {compatiblePorts,FAMILY_NAMES,effectivePort,portDescription} from './logic.js';

export default function DestinationPicker({deviceId,sourcePort,onSelect,onClose,disabled=false}) {
  const [query,setQuery]=useState(''),[offset,setOffset]=useState(0),[page,setPage]=useState(null);
  const [error,setError]=useState(null),[revision,setRevision]=useState(0);
  const portHeading=useRef(null);
  const [chosen,setChosen]=useState(null),[details,setDetails]=useState(null),[portError,setPortError]=useState(null);
  useEffect(()=>{if(chosen)portHeading.current?.focus();},[chosen]);
  useEffect(()=>{let active=true;setDetails(null);setPortError(null);if(chosen)getDevice(chosen.id).then(result=>{if(active)setDetails(result);}).catch(failure=>{if(active)setPortError(failure.message);});return()=>{active=false;};},[chosen,revision]);
  useEffect(()=>{
    let active=true;setPage(null);setError(null);
    const timer=setTimeout(()=>listDevices({query:query.trim(),limit:20,offset}).then(result=>{
      if(!active)return;
      if(offset&&offset>=result.total){setOffset(Math.max(0,Math.floor(Math.max(0,result.total-1)/20)*20));return;}
      setPage(result);
    }).catch(failure=>{if(active)setError(failure.message);}),200);
    return()=>{active=false;clearTimeout(timer);};
  },[query,offset,revision]);
  const matchingPorts=compatiblePorts(sourcePort,details?.ports||[]);
  const connector=FAMILY_NAMES[sourcePort?effectivePort(sourcePort).effectiveFamily:null]||sourcePort?.family||'unknown';
  const items=page?.items.filter(item=>item.id!==deviceId)||[];
  return <section className="sv-destination-picker" aria-label="Choose destination device" onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onClose();}}}>
    {!chosen&&<><label>Find existing device<input className="tool-input" type="search" autoFocus onKeyDown={event=>{if(event.key==='Enter')event.preventDefault();}} maxLength={100} value={query} disabled={disabled} onChange={event=>{setQuery(event.target.value);setOffset(0);}} placeholder="Name, model or description"/></label>
    <p className="tool-hint">Choose a device, then a port. Save assignment connects both ends and fills Leads to on both devices.</p>
    {error?<p className="tool-error" role="alert">{error}<button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>setRevision(value=>value+1)}>Retry devices</button></p>:!page?<p role="status">Loading devices…</p>:<>
      {items.length?<ul className="sv-destination-options">{items.map(item=><li key={item.id}><button type="button" disabled={disabled} onClick={()=>setChosen(item)}><strong>{item.name}</strong><span>{item.deviceType==='cable-management'?'Cable management panel':item.deviceType}{item.model?` · ${item.model}`:''}</span><small>{item.rackId?`${item.dataCenterName} / ${item.rackName} · U${item.rackPosition}`:'Unassigned to a rack'}</small></button></li>)}</ul>:<p className="tool-hint">No other devices on this page. Change the search or browse another page, or enter a destination manually.</p>}
      <div className="sv-destination-actions"><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled||!offset} onClick={()=>setOffset(value=>value-20)}>Previous devices</button><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled||offset+20>=page.total} onClick={()=>setOffset(value=>value+20)}>Next devices</button></div>
    </>}
    </>}
    {chosen&&<><h4 ref={portHeading} tabIndex={-1}>{chosen.name} · Choose destination port</h4><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>setChosen(null)}>Back to devices</button><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>onSelect({device:chosen,port:null})}>Use device name only</button>
      <p className="tool-hint">Matching {sourcePort?.name}: {connector} · {sourcePort?effectivePort(sourcePort).effectiveSpeedGbps:'?'}G. Assigned matching ports remain available with replacement confirmation.</p>
      {portError?<p className="tool-error" role="alert">{portError}<button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>setRevision(value=>value+1)}>Retry ports</button></p>:!details?<p role="status">Loading ports…</p>:matchingPorts.length?<ul className="sv-destination-options">{matchingPorts.map(port=><li key={port.id}><button type="button" disabled={disabled} onClick={()=>onSelect({device:details,port})}><strong>{port.name} · {portDescription(port)}</strong><span>{port.connectionId||port.leadsTo?'Assigned · review required':'Free'}{port.connectionId?` · Cable #${port.connectionId}`:''}</span><small>Leads to: {port.leadsTo||'Not set'} · Label: {port.label||'Not set'}</small><small>IP: {port.ipAddress||'Not set'} · VLAN: {port.portMode?`${port.portMode} ${port.accessVlan||port.trunkVlans}`:'Not configured'}</small></button></li>)}</ul>:<p className="tool-hint">No matching {connector} {sourcePort?effectivePort(sourcePort).effectiveSpeedGbps:'?'}G ports on this device. Choose another device or enter a destination manually.</p>}
    </>}
    <button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={onClose}>Close device picker</button>
  </section>;
}
