import React,{useEffect,useRef,useState} from 'react';
import ViewTabs from '../../components/ViewTabs.jsx';
import useUnsavedChanges from '../../components/useUnsavedChanges.js';
import useCatalog from './useCatalog.js';
import {getRack,listDevices} from './api.js';
import ResourceForm from './ResourceForm.jsx';
import PlacementEditor from './PlacementEditor.jsx';
import RackElevation from './RackElevation.jsx';
import CablePanelForm from './CablePanelForm.jsx';
import InventoryHistory from './InventoryHistory.jsx';
import {unitRange} from './rackLogic.js';
import './dc-inventory.css';

export default function DcInventory() {
  const [dcId,setDCId]=useState(null),[rackId,setRackId]=useState(null),[revision,setRevision]=useState(0);
  const {dc,racks,loading,error:catalogError,moreDC,moreRacks,retry}=useCatalog(dcId,false,revision);
  const [dcOverride,setDCOverride]=useState(null),[loadedRack,setRack]=useState(null),[rackError,setRackError]=useState(null),[rackLoading,setRackLoading]=useState(false);
  const [view,setView]=useState('rack'),[editor,setEditor]=useState(null),[selected,setSelected]=useState(null);
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [unassigned,setUnassigned]=useState(null),[query,setQuery]=useState(''),[offset,setOffset]=useState(0),[deviceError,setDeviceError]=useState(null);
  const firstDC=useRef(false),firstRack=useRef(false);
  useUnsavedChanges(dirty,busy);
  const guard=action=>{if(busy)return;if(dirty&&!window.confirm('Discard unsaved inventory changes?'))return;setDirty(false);setEditor(null);setSelected(null);action();};
  useEffect(()=>{if(!firstDC.current&&dc.items.length){firstDC.current=true;setDCId(dc.items[0].id);}},[dc]);
  useEffect(()=>{if(dcId&&!rackId&&!firstRack.current&&racks.items.some(item=>item.dataCenterId===dcId)){firstRack.current=true;setRackId(racks.items.find(item=>item.dataCenterId===dcId).id);}},[dcId,rackId,racks]);
  useEffect(()=>{
    let active=true;setRack(null);setRackError(null);setRackLoading(!!rackId);
    if(rackId)getRack(rackId).then(result=>{if(active)setRack(result);}).catch(failure=>{if(active)setRackError(failure.message);}).finally(()=>{if(active)setRackLoading(false);});
    return()=>{active=false;};
  },[rackId,revision]);
  useEffect(()=>{
    let active=true;setUnassigned(null);setDeviceError(null);
    listDevices({unassigned:true,query,limit:25,offset}).then(result=>{if(!active)return;if(offset&&offset>=result.total){setOffset(Math.max(0,Math.floor(Math.max(0,result.total-1)/25)*25));return;}setUnassigned(result);}).catch(failure=>{if(active)setDeviceError(failure.message);});
    return()=>{active=false;};
  },[query,offset,revision]);
  const rack=loadedRack?.id===rackId?loadedRack:null;
  const activeDC=dc.items.find(item=>item.id===dcId)||(dcOverride?.id===dcId?dcOverride:null);
  const savedResource=(result,kind)=>{
    setDirty(false);setEditor(null);setRevision(value=>value+1);setNotice(result.deleted?'Location deleted.':'Location saved.');
    if(kind==='datacenters'){setDCOverride(result.deleted?null:result);setDCId(result.deleted?null:result.id);setRackId(null);firstRack.current=false;}
    else setRackId(result.deleted?null:result.id);
  };
  const savedPlacement=result=>{setDirty(false);setSelected(null);setRevision(value=>value+1);setNotice(`Placement saved for ${result.name}.`);if(result.rackId){setDCId(result.dataCenterId);setRackId(result.rackId);setView('rack');}};
  const chooseDevice=device=>guard(()=>setSelected(device));
  return <div className="di-tool"><div className="nt-tool-header di-heading"><div><h2>DC Inventory</h2><p>Locate Device Visualization equipment by data center, rack and rack unit.</p></div><div className="di-actions"><button className="tool-btn tool-btn-primary" disabled={busy} onClick={()=>guard(()=>setEditor({kind:'datacenters'}))}>Add data center</button><button className="tool-btn tool-btn-ghost" disabled={busy||!dcId} onClick={()=>guard(()=>setEditor({kind:'racks'}))}>Add rack</button><button className="tool-btn tool-btn-ghost" disabled={busy||!rack} onClick={()=>guard(()=>setEditor({kind:'cable-panel'}))}>Add cable management panel (1U)</button></div></div>
    {notice&&<p role="status" className="di-notice">{notice}</p>}
    <div className="tool-panel di-location-bar"><label>Data center<select aria-label="Data center" className="tool-input" disabled={busy||loading.dc} value={dcId||''} onChange={event=>guard(()=>{setDCId(Number(event.target.value)||null);setRackId(null);firstRack.current=false;})}><option value="">Choose a data center</option>{activeDC&&!dc.items.some(item=>item.id===activeDC.id)&&<option value={activeDC.id}>{activeDC.name}</option>}{dc.items.map(item=><option key={item.id} value={item.id}>{item.name} · {item.rackCount} racks</option>)}</select></label>
      <label>Rack<select aria-label="Rack" className="tool-input" disabled={busy||!dcId||loading.racks} value={rackId||''} onChange={event=>guard(()=>setRackId(Number(event.target.value)||null))}><option value="">Choose a rack</option>{rack&&!racks.items.some(item=>item.id===rack.id)&&<option value={rack.id}>{rack.name}</option>}{racks.items.map(item=><option key={item.id} value={item.id}>{item.name} · {item.usedU}/{item.heightU}U</option>)}</select></label>
      <div className="di-actions"><button className="tool-btn tool-btn-ghost" disabled={busy||!activeDC} onClick={()=>guard(()=>setEditor({kind:'datacenters',entity:activeDC}))}>Edit data center</button><button className="tool-btn tool-btn-ghost" disabled={busy||!rack} onClick={()=>guard(()=>setEditor({kind:'racks',entity:rack}))}>Edit rack</button><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>guard(()=>setRevision(value=>value+1))}>Reload inventory</button></div>
      {dc.items.length<dc.total&&<button className="tool-btn tool-btn-ghost" disabled={loading.dc} onClick={moreDC}>Load more data centers</button>}{racks.items.length<racks.total&&<button className="tool-btn tool-btn-ghost" disabled={loading.racks} onClick={moreRacks}>Load more racks</button>}
      {catalogError&&<p role="alert" className="tool-error">{catalogError}<button className="tool-btn tool-btn-ghost" onClick={retry}>Retry locations</button></p>}
    </div>
    {editor?.kind==='cable-panel'?<CablePanelForm rack={rack} onDirty={setDirty} onBusy={setBusy} onSaved={result=>{setEditor(null);savedPlacement(result);}} onCancel={()=>guard(()=>{})}/>:editor&&<ResourceForm key={`${editor.kind}-${editor.entity?.id||'new'}`} {...editor} dataCenterId={dcId} onDirty={setDirty} onBusy={setBusy} onSaved={savedResource} onCancel={()=>guard(()=>{})}/>}
    <div className="tool-panel"><ViewTabs label="Inventory views" value={view} onChange={value=>guard(()=>setView(value))} items={[{id:'rack',label:'Rack elevation'},{id:'unassigned',label:'Unassigned'},{id:'history',label:'History'}]}/>
      {selected&&<PlacementEditor key={`${selected.id}-${selected.version}`} device={selected} onDirty={setDirty} onBusy={setBusy} onSaved={savedPlacement} onCancel={()=>guard(()=>{})}/>}
      {view==='history'&&<InventoryHistory key={revision}/>}
      {view==='rack'&&(rackLoading?<p role="status">Loading rack…</p>:rackError?<p role="alert" className="tool-error">{rackError}<button className="tool-btn tool-btn-ghost" onClick={()=>setRevision(value=>value+1)}>Retry rack</button></p>:!rack?<div className="tool-empty">{!dcId?'Add or choose a data center to start.':'Add or choose a rack. Its height and installed devices will appear here.'}</div>:<div className="di-rack-workspace"><RackElevation rack={rack} selectedId={selected?.id} onSelect={chooseDevice} disabled={busy}/><section className="di-installed" aria-label="Installed devices"><h3>{rack.dataCenterName} / {rack.name}</h3><p>{rack.deviceCount} {rack.deviceCount===1?'device':'devices'} · {rack.usedU}U occupied · {rack.heightU-rack.usedU}U free</p><p className="tool-hint">Rack capacity: {rack.heightU}U. Device positions refer to their lowest occupied U.</p>{rack.devices.length?<DeviceTable devices={rack.devices} disabled={busy} onSelect={chooseDevice}/>:<div className="tool-empty">This rack is empty. Assign equipment from the Unassigned list.</div>}</section></div>)}
      {view==='unassigned'&&<section aria-label="Unassigned devices"><h3>Unassigned devices</h3><p className="tool-hint">All devices come from Device Visualization. Their existing ports and network documentation stay attached.</p><label className="di-search">Find device<input className="tool-input" type="search" maxLength={100} value={query} onChange={event=>guard(()=>{setQuery(event.target.value);setOffset(0);})}/></label>{deviceError?<p role="alert" className="tool-error">{deviceError}<button className="tool-btn tool-btn-ghost" onClick={()=>setRevision(value=>value+1)}>Retry devices</button></p>:!unassigned?<p role="status">Loading devices…</p>:<><p>{unassigned.total} {query?'matching unassigned devices':'devices without a rack'}</p>{unassigned.items.length?<DeviceTable devices={unassigned.items} disabled={busy} onSelect={chooseDevice}/>:<div className="tool-empty">No unassigned devices match this view.</div>}<div className="di-actions"><button className="tool-btn tool-btn-ghost" disabled={busy||offset===0} onClick={()=>guard(()=>setOffset(value=>value-25))}>Previous devices</button><button className="tool-btn tool-btn-ghost" disabled={busy||offset+25>=unassigned.total} onClick={()=>guard(()=>setOffset(value=>value+25))}>Next devices</button></div></>}</section>}
    </div>
  </div>;
}
function DeviceTable({devices,disabled,onSelect}) {
  return <div className="tool-table-wrap"><table className="tool-table di-device-table"><thead><tr><th>Device</th><th>Type / model</th><th>Height</th><th>Position</th><th>Action</th></tr></thead><tbody>{devices.map(device=><tr key={device.id}><td data-label="Device">{device.name}</td><td data-label="Type / model">{device.deviceType==='cable-management'?'Cable management panel':device.deviceType}{device.model?` · ${device.model}`:''}</td><td data-label="Height">{device.heightU?`${device.heightU}U`:'Not recorded'}</td><td data-label="Position">{unitRange(device)}</td><td data-label="Action"><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>onSelect(device)} aria-label={`Place ${device.name}`}>{device.rackId?'Move / unassign':'Assign to rack'}</button></td></tr>)}</tbody></table></div>;
}
