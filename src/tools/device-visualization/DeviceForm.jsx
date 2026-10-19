import React,{useEffect,useState} from 'react';
import { createDevice,previewDeviceUpdate,updateDevice } from './api.js';
import { PORT_NAMING,FAMILIES,FAMILY_NAMES,SPEEDS,limitsForType,VENDORS,newCard,usesCards,CONTROLLERS,newStorageCard,initialDraft,payload,validateDraft,removedPorts,isStorage } from './logic.js';
import DriveBays from './DriveBays.jsx';
import NetworkCardFields from './NetworkCardFields.jsx';
import LocationFields from '../dc-inventory/LocationFields.jsx';
export default function DeviceForm({device,onSaved,onCancel,onDirty,onBusy,onReload,initialValues={},onCreate=createDevice,ipamSource=null}) {
  const [draft,setDraft]=useState(()=>({...initialDraft(device),...(!device?initialValues:{})}));
  const [baseline]=useState(()=>JSON.stringify({...initialDraft(device),...(!device?initialValues:{})}));
  const [ipPort,setIpPort]=useState('management');
  const targetPort=draft.managementPort?ipPort:'data';
  const [preview,setPreview]=useState(null),[error,setError]=useState(null),[stale,setStale]=useState(false),[busy,setBusy]=useState(false);
  useEffect(()=>{onDirty(JSON.stringify(draft)!==baseline||!!ipamSource&&ipPort!=='management');},[draft,baseline,onDirty,ipamSource,ipPort]);
  const change=patch=>{setDraft(d=>({...d,...patch}));setPreview(null);setError(null);setStale(false);};
  const total=(draft.networkCards||draft.portGroups).reduce((n,g)=>n+g.count,0);
  const lost=removedPorts(device,draft).filter(p=>p.label||p.leadsTo||p.portMode||p.ipAddress||p.connectionId||p.transceiver);
  const perform=async(confirm=false)=>{
    setError(null);setBusy(true);onBusy(true);
    try {
      validateDraft(draft);
      if(!Number.isInteger(draft.heightU)||draft.heightU<1||draft.heightU>100)throw new Error('Record the device height (1–100U) before saving.');
      const data=payload(draft,device?.version);
      if(!device) {onSaved(await onCreate(data,targetPort));return;}
      if(!confirm) {
        const review=await previewDeviceUpdate(device.id,data);
        if(review.removedAssignedPortCount||review.removedLabelledPortCount||review.removedConfiguredPortCount) {setPreview(review);return;}
      }
      onSaved(await updateDevice(device.id,{...data,confirmPortDataRemoval:confirm}));
    } catch(e) {setError(e.message);setPreview(null);setStale(e.detail?.code==='stale_version');}
    finally {setBusy(false);onBusy(false);}
  };
  const typeChange=type=>{
    const next={...draft,deviceType:type,vendor:type==='firewall'?'checkpoint':null};
    if(type==='switch')Object.assign(next,{portNaming:'family',portUnit:1,portSlot:1});
    else {delete next.portNaming;delete next.portUnit;delete next.portSlot;}
    if(usesCards(type)){delete next.portGroups;next.networkCards=type==='storage'?CONTROLLERS.map(c=>newStorageCard(c)):[newCard()];}
    else {delete next.networkCards;next.portGroups=initialDraft().portGroups;}
    delete next.driveBayCount;delete next.occupiedBays;delete next.expansionPortCount;
    if(isStorage(type))Object.assign(next,{driveBayCount:24,occupiedBays:[],expansionPortCount:2});
    if(type==='storage-shelf')Object.assign(next,{heightU:2,managementPort:false,portGroups:[]});
    if(type==='cable-management')Object.assign(next,{heightU:1,managementPort:false,portGroups:[]});
    setDraft(next);setPreview(null);
  };
  return <form className="sv-form" onSubmit={e=>{e.preventDefault();perform(false);}}>
    <h3>{device?'Edit device':'New device'}</h3>
    <fieldset disabled={busy} className="sv-form-fields">
      <div className="sv-fields">
        <label>Device type<select aria-label="Device type" className="tool-input" value={draft.deviceType} disabled={!!device} onChange={e=>typeChange(e.target.value)}><option value="switch">Switch</option><option value="router">Router</option><option value="firewall">Firewall</option><option value="server">Server</option><option value="storage">Storage head / array</option><option disabled={!!ipamSource} value="storage-shelf">Storage expansion shelf</option><option disabled={!!ipamSource} value="cable-management">Rackmount Cable Management Panel (1U)</option></select></label>
        {draft.deviceType==='firewall'&&<label>Vendor<select aria-label="Vendor" className="tool-input" value={draft.vendor} onChange={e=>change({vendor:e.target.value})}>{Object.entries(VENDORS).map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>}
        <label>Name<input className="tool-input" required maxLength={100} value={draft.name} onChange={e=>change({name:e.target.value})}/></label>
        <label>Model (optional)<input className="tool-input" maxLength={100} value={draft.model} onChange={e=>change({model:e.target.value})}/></label>
      </div>
      {draft.deviceType==='switch'&&<fieldset className="sv-nic-form"><legend>Port naming</legend>
        <label>Naming convention<select aria-label="Naming convention" className="tool-input" value={draft.portNaming} onChange={e=>change({portNaming:e.target.value})}>{Object.entries(PORT_NAMING).map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></label>
        {draft.portNaming!=='family'&&draft.portNaming!=='port'&&<label>Unit / stack member<input className="tool-input" type="number" min={1} max={16} step={1} value={draft.portUnit} onChange={e=>change({portUnit:Number(e.target.value)})}/></label>}
        {draft.portNaming==='unit-slot-port'&&<label>Slot<input className="tool-input" type="number" min={0} max={16} step={1} value={draft.portSlot} onChange={e=>change({portSlot:Number(e.target.value)})}/></label>}
        <p className="tool-hint">Numeric formats count Ethernet, then SFP, then QSFP continuously. Adding earlier ports renumbers later display names; IDs and configuration stay intact.</p>
      </fieldset>}
      {!['cable-management','storage-shelf'].includes(draft.deviceType)&&<label className="sv-management-option"><input type="checkbox" checked={draft.managementPort} onChange={e=>change({managementPort:e.target.checked})}/> {draft.deviceType==='storage'?'Dedicated management ports (one per controller · Ethernet 1G)':'Dedicated management port (MGMT · Ethernet 1G)'}</label>}
      {ipamSource&&<fieldset className="sv-nic-form"><legend>Address from IPAM</legend><label>IP address<input className="tool-input" readOnly value={ipamSource.address}/></label><label>Assign IP to<select aria-label="Assign IP to" className="tool-input" value={targetPort} onChange={event=>setIpPort(event.target.value)}><option value="management" disabled={!draft.managementPort}>Dedicated MGMT port{draft.deviceType==='storage'?' · Controller A':''}</option><option value="data">First data port</option></select></label><p className="tool-hint">Saving creates the device, assigns this IP and marks the IPAM address used. Choose a rack below or leave the device unassigned.</p></fieldset>}
      <label>Description<textarea className="tool-textarea" maxLength={500} value={draft.description} onChange={e=>change({description:e.target.value})}/></label>
      <LocationFields fixedHeight={draft.deviceType==='cable-management'} draft={draft} onChange={change} disabled={busy}/>
      {isStorage(draft.deviceType)&&<fieldset className="sv-nic-form"><legend>Disks and expansion</legend>
        <label>Drive bay count<input className="tool-input" aria-label="Drive bay count" type="number" min={0} max={120} step={1} value={draft.driveBayCount} onChange={event=>change({driveBayCount:Number(event.target.value)})}/></label>
        {draft.deviceType==='storage'?<label>Storage expansion ports<input className="tool-input" type="number" aria-label="Storage expansion ports" min={0} max={16} step={1} value={draft.expansionPortCount} onChange={event=>change({expansionPortCount:Number(event.target.value)})}/></label>:<p className="tool-hint">Two SAS expansion ports · connect to a storage head or daisy-chain another shelf.</p>}
        {(draft.occupiedBays||[]).some(n=>n>draft.driveBayCount)&&<p className="tool-error" role="alert">Occupied bays exceed the new count. Restore the count and mark those bays empty first.</p>}
        <DriveBays count={Math.max(draft.driveBayCount,0,...(draft.occupiedBays||[]))} occupied={draft.occupiedBays} onChange={occupiedBays=>change({occupiedBays})} disabled={busy}/>
      </fieldset>}
      {draft.deviceType==='storage'?<div className="sv-storage-fields">{CONTROLLERS.map(controller=><section key={controller} aria-label={`Controller ${controller} configuration`}><NetworkCardFields title={`Controller ${controller}`} limit={8} cards={draft.networkCards.filter(c=>c.controller===controller)} onChange={cards=>change({networkCards:[...draft.networkCards.filter(c=>c.controller!==controller),...cards]})} onAdd={()=>change({networkCards:[...draft.networkCards,newStorageCard(controller,draft.networkCards)]})}/></section>)}</div>:draft.deviceType==='server'?<NetworkCardFields cards={draft.networkCards} onChange={cards=>change({networkCards:cards})}/>:<div className="sv-group-fields">{draft.portGroups.map((g,index)=><fieldset key={g.family}><legend>{FAMILY_NAMES[g.family]}</legend>
        <label>Sockets (0–{limitsForType(draft.deviceType)[g.family]})<input className="tool-input" type="number" min={0} max={limitsForType(draft.deviceType)[g.family]} step={1} value={g.count} onChange={e=>change({portGroups:draft.portGroups.map((item,i)=>i===index?{...item,count:Number(e.target.value)}:item)})}/></label>
        <label>Speed<select aria-label="Speed" className="tool-input" value={g.speedGbps} onChange={e=>change({portGroups:draft.portGroups.map((item,i)=>i===index?{...item,speedGbps:Number(e.target.value)}:item)})}>{SPEEDS[g.family].map(s=><option key={s} value={s}>{s}G</option>)}</select></label>
      </fieldset>)}</div>}
      {!['cable-management','storage-shelf'].includes(draft.deviceType)&&<p className={total<1||total>128?'tool-error':'tool-hint'}>{total} / 128 data sockets · minimum 1{draft.managementPort ? (draft.deviceType==='storage'?" · +2 MGMT":" · +1 MGMT") : ""}</p>}
      {lost.length>0&&!preview&&<p className="tool-hint">This draft removes data on {lost.length} ports. Review is required before saving.</p>}
      {preview&&<div className="sv-review" role="region" aria-label="Port removal review"><h4>Review removed port data</h4><p>{preview.removedPortCount} sockets removed, {preview.removedAssignedPortCount} destinations and {preview.removedLabelledPortCount} labels lost, {preview.removedConfiguredPortCount} IP/VLAN configurations, modules or cable connections lost.</p><ul>{preview.removedPorts.filter(p=>p.label||p.leadsTo||p.portMode||p.ipAddress||p.connectionId||p.transceiver).map(p=><li key={p.id}><strong>{p.name}</strong> · {p.label||'no label'} · {p.leadsTo||'unassigned'}{p.connectionId?` · cable #${p.connectionId}`:''}{p.ipAddress?` · IP ${p.ipAddress}`:''}{p.portMode?` · ${p.portMode} VLAN ${p.accessVlan||p.trunkVlans}`:''}</li>)}</ul>
        <button className="tool-btn tool-btn-primary" type="button" onClick={()=>perform(true)}>Confirm removal and save</button><button className="tool-btn tool-btn-ghost" type="button" onClick={()=>setPreview(null)}>Cancel review</button>
      </div>}
      {!preview&&<button className="tool-btn tool-btn-primary" type="submit">{busy?'Saving…':'Save device'}</button>}
      <button className="tool-btn tool-btn-ghost" type="button" onClick={onCancel}>Cancel</button>
    </fieldset>
    {error&&<p className="tool-error" role="alert">{error}{stale&&<button className="tool-btn tool-btn-ghost" type="button" onClick={onReload}>Reload current device</button>}</p>}
    <span role="status" className="sv-sr-only">{busy?'Saving device…':''}</span>
  </form>;
}
