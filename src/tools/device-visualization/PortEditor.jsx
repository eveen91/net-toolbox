import React,{useEffect,useState} from 'react';
import { updatePortAssignment } from './api.js';
export default function PortEditor({device,port,onSaved,onDirty,onBusy,onReload}) {
  const [label,setLabel]=useState(port.label||''),[destination,setDestination]=useState(port.leadsTo||'');
  const [address,setAddress]=useState(port.ipAddress||'');
  const [mode,setMode]=useState(port.portMode||''),[access,setAccess]=useState(port.accessVlan??''),[allowed,setAllowed]=useState(port.trunkVlans||''),[native,setNative]=useState(port.nativeVlan??'');
  const [version]=useState(device.version),[busy,setBusy]=useState(false),[error,setError]=useState(null),[stale,setStale]=useState(false);
  useEffect(()=>{onDirty(address!==(port.ipAddress||'')||label!==(port.label||'')||destination!==(port.leadsTo||'')||mode!==(port.portMode||'')||String(access)!==String(port.accessVlan??'')||allowed!==(port.trunkVlans||'')||String(native)!==String(port.nativeVlan??''));},[address,label,destination,mode,access,allowed,native,port,onDirty]);
  const save=async(clear=false)=>{
    setError(null);setBusy(true);onBusy(true);
    try {
      const saved=await updatePortAssignment(device.id,port.id,{ipAddress:address.trim()||null,label:label.trim()||null,leadsTo:clear?null:destination.trim()||null,expectedVersion:version,portMode:mode||null,accessVlan:mode==='access'&&access!==''?Number(access):null,trunkVlans:mode==='trunk'?allowed:null,nativeVlan:mode==='trunk'&&native!==''?Number(native):null});
      const current=saved.ports.find(p=>p.id===port.id);
      setAddress(current.ipAddress||'');
      setLabel(current.label||'');setDestination(current.leadsTo||'');setMode(current.portMode||'');
      setAccess(current.accessVlan??'');setAllowed(current.trunkVlans||'');setNative(current.nativeVlan??'');
      onSaved(saved);
    } catch(e) {setError(e.message);setStale(e.detail?.code==='stale_version');}
    finally {setBusy(false);onBusy(false);}
  };
  return <form className="sv-port-editor" onSubmit={e=>{e.preventDefault();save();}}>
    <h3>{port.name} <span className="tool-hint">{port.speedGbps}G</span></h3>
    <fieldset disabled={busy} className="sv-form-fields">
      <div className="sv-fields"><label>Port label<input className="tool-input" maxLength={50} value={label} onChange={e=>setLabel(e.target.value)}/></label><label>Leads to<input className="tool-input" maxLength={200} value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Device / socket or destination"/></label></div>
      <label>IP address (optional)<input className="tool-input" maxLength={64} value={address} onChange={e=>setAddress(e.target.value)} placeholder="192.0.2.1/24 or 2001:db8::1/64" aria-describedby="sv-port-ip-hint" spellCheck={false}/></label>
      <p className="tool-hint" id="sv-port-ip-hint">IPv4 or IPv6, with an optional prefix. This address belongs to the interface; VLAN configuration is optional.</p>
      <h4>VLAN configuration (optional)</h4>
      <div className="sv-fields">
        <label>Port mode<select aria-label="Port mode" className="tool-input" value={mode} onChange={e=>{setMode(e.target.value);setAccess('');setAllowed('');setNative('');}}><option value="">Not configured</option><option value="access">Access</option><option value="trunk">Trunk</option></select></label>
        {mode==='access'&&<label>Access VLAN<input className="tool-input" type="number" min={1} max={4094} step={1} required value={access} onChange={e=>setAccess(e.target.value)}/></label>}
        {mode==='trunk'&&<><label>Allowed VLANs<input className="tool-input" required maxLength={2000} placeholder="10,20,100-110 or all" value={allowed} onChange={e=>setAllowed(e.target.value)}/></label><label>Native VLAN (optional)<input className="tool-input" type="number" min={1} max={4094} step={1} value={native} onChange={e=>setNative(e.target.value)}/></label></>}
      </div>
      <p className="tool-hint">VLAN IDs: 1–4094. Saved documentation; no device configuration is applied.</p>
      <button type="submit" className="tool-btn tool-btn-primary">{busy?'Saving…':'Save assignment'}</button>
      {port.leadsTo&&<button type="button" className="tool-btn tool-btn-ghost" onClick={()=>save(true)}>Clear assignment</button>}
    </fieldset>
    {error&&<p className="tool-error" role="alert">{error}{stale&&<button type="button" className="tool-btn tool-btn-ghost" onClick={onReload}>Reload current device</button>}</p>}
  </form>;
}
