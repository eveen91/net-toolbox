import IpamAddressField from './IpamAddressField.jsx';
import React,{useEffect,useRef,useState} from 'react';
import {TRANSCEIVERS,effectivePort} from './logic.js';
import ConnectionReview from './ConnectionReview.jsx';
import DestinationPicker from './DestinationPicker.jsx';
import { updatePortAssignment,placePortInIpam } from './api.js';
export default function PortEditor({device,port,onSaved,onDirty,onBusy,onReload}) {
  const [label,setLabel]=useState(port.label||''),[destination,setDestination]=useState(port.leadsTo||'');
  const [target,setTarget]=useState(null),[review,setReview]=useState(null);
  const [pickerOpen,setPickerOpen]=useState(false);
  const destinationInput=useRef(null),pickerTrigger=useRef(null);
  const closePicker=()=>{setPickerOpen(false);pickerTrigger.current?.focus();};
  const [transceiver,setTransceiver]=useState(port.transceiver||'');
  const activePort=effectivePort({...port,transceiver:transceiver||null});
  const [address,setAddress]=useState(port.ipAddress||'');
  const [mode,setMode]=useState(port.portMode||''),[access,setAccess]=useState(port.accessVlan??''),[allowed,setAllowed]=useState(port.trunkVlans||''),[native,setNative]=useState(port.nativeVlan??'');
  const [version]=useState(device.version),[busy,setBusy]=useState(false),[error,setError]=useState(null),[stale,setStale]=useState(false);
  useEffect(()=>{onDirty(transceiver!==(port.transceiver||'')||!!target||address!==(port.ipAddress||'')||label!==(port.label||'')||destination!==(port.leadsTo||'')||mode!==(port.portMode||'')||String(access)!==String(port.accessVlan??'')||allowed!==(port.trunkVlans||'')||String(native)!==String(port.nativeVlan??''));},[address,label,destination,mode,access,allowed,native,port,onDirty,target,transceiver]);
  useEffect(()=>setReview(null),[address,label,destination,mode,access,allowed,native,target,transceiver]);
  const save=async(clear=false,confirmation=null)=>{
    setError(null);setBusy(true);onBusy(true);
    try {
      const saved=await updatePortAssignment(device.id,port.id,{...(port.family==='sfp'?{transceiver:transceiver||null}:{}),ipAddress:address.trim()||null,label:label.trim()||null,leadsTo:clear?null:destination.trim()||null,expectedVersion:version,...(!clear&&target?{targetPortId:target.port.id,targetVersion:target.device.version,...(confirmation?{replacementToken:confirmation}:{})}:{}),portMode:mode||null,accessVlan:mode==='access'&&access!==''?Number(access):null,trunkVlans:mode==='trunk'?allowed:null,nativeVlan:mode==='trunk'&&native!==''?Number(native):null});
      const current=saved.ports.find(p=>p.id===port.id);
      setTransceiver(current.transceiver||'');setAddress(current.ipAddress||'');
      setLabel(current.label||'');setDestination(current.leadsTo||'');setMode(current.portMode||'');
      setAccess(current.accessVlan??'');setAllowed(current.trunkVlans||'');setNative(current.nativeVlan??'');
      let placement=null;
      if(current.ipAddress){
        try{placement=await placePortInIpam(saved.id,current.id,saved.version);}
        catch(error){placement={status:'error',message:`Hardware was saved, but IPAM placement could not complete. ${error.message}`};}
      }
      setReview(null);setTarget(null);onSaved(saved,placement?{result:placement,deviceId:saved.id,portId:current.id,version:saved.version}:null);
    } catch(e) {if(e.detail?.code==='connection_change_required'){setReview(e.detail);setError(null);}else{setReview(null);setError(e.message);}setStale(e.detail?.code==='stale_version');}
    finally {setBusy(false);onBusy(false);}
  };
  return <form className="sv-port-editor" onSubmit={e=>{e.preventDefault();if(!review)save();}}>
    <h3>{port.name} <span className="tool-hint">{activePort.effectiveSpeedGbps}G</span></h3>
    {port.connectionId&&<p className="tool-hint">Physical cable #{port.connectionId} · Choose another device and port to review a replacement. Manual edits change the note only.</p>}
    <fieldset disabled={busy} className="sv-form-fields">
      {port.family==='sfp'&&<label>SFP module<select aria-label="SFP module" className="tool-input" value={transceiver} onChange={event=>{setTransceiver(event.target.value);setTarget(null);setReview(null);setPickerOpen(false);}}><option value="">Use group default · {port.speedGbps}G SFP</option>{Object.entries(TRANSCEIVERS).map(([value,item])=><option key={value} value={value}>{item.label}</option>)}</select><span className="tool-hint">Applies to this socket only. Records installed hardware; does not change device configuration or verify module support.</span></label>}
      <div className="sv-fields"><label>Port label<input className="tool-input" maxLength={50} value={label} onChange={e=>setLabel(e.target.value)}/></label><label>Leads to<input ref={destinationInput} className="tool-input" maxLength={200} value={destination} onChange={e=>{setDestination(e.target.value);setTarget(null);setReview(null);}} placeholder="Device / socket or destination"/></label></div>
      <button ref={pickerTrigger} type="button" className="tool-btn tool-btn-ghost" aria-expanded={pickerOpen} onClick={()=>setPickerOpen(value=>!value)}>Choose existing device</button>
      <p className="tool-hint">You can also type any destination above. Selecting a device and port saves both ends together. Typing manually saves a text note only.</p>
      {pickerOpen&&<DestinationPicker sourcePort={activePort} deviceId={device.id} disabled={busy} onSelect={selection=>{setTarget(selection.port?selection:null);setReview(null);setDestination(selection.port?`${selection.device.name} / ${selection.port.name}`:selection.device.name);setPickerOpen(false);destinationInput.current?.focus();}} onClose={closePicker}/>}
      {target&&<p role="status" className="tool-hint">Selected: {target.device.name} / {target.port.name}. Save assignment updates both devices and the rack connection diagram.</p>}
      {port.family!=='sas'&&<><IpamAddressField value={address} onChange={setAddress} disabled={busy}/>
      <p className="tool-hint" id="sv-port-ip-hint">IPv4 or IPv6, with an optional prefix. This address belongs to the interface; VLAN configuration is optional.</p>
      <h4>VLAN configuration (optional)</h4>
      <div className="sv-fields">
        <label>Port mode<select aria-label="Port mode" className="tool-input" value={mode} onChange={e=>{setMode(e.target.value);setAccess('');setAllowed('');setNative('');}}><option value="">Not configured</option><option value="access">Access</option><option value="trunk">Trunk</option></select></label>
        {mode==='access'&&<label>Access VLAN<input className="tool-input" type="number" min={1} max={4094} step={1} required value={access} onChange={e=>setAccess(e.target.value)}/></label>}
        {mode==='trunk'&&<><label>Allowed VLANs<input className="tool-input" required maxLength={2000} placeholder="10,20,100-110 or all" value={allowed} onChange={e=>setAllowed(e.target.value)}/></label><label>Native VLAN (optional)<input className="tool-input" type="number" min={1} max={4094} step={1} value={native} onChange={e=>setNative(e.target.value)}/></label></>}
      </div>
      <p className="tool-hint">VLAN IDs: 1–4094. Saved documentation; no device configuration is applied.</p></>}
      {review&&<ConnectionReview review={review} busy={busy} onConfirm={()=>save(false,review.token)} onCancel={()=>setReview(null)}/> }
      {!review&&<button type="submit" className="tool-btn tool-btn-primary">{busy?'Saving…':'Save assignment'}</button>}
      {port.leadsTo&&<button type="button" className="tool-btn tool-btn-ghost" onClick={()=>save(true)}>Clear assignment</button>}
    </fieldset>
    {error&&<p className="tool-error" role="alert">{error}{stale&&<button type="button" className="tool-btn tool-btn-ghost" onClick={onReload}>Reload current device</button>}</p>}
  </form>;
}
