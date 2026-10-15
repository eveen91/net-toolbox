import React,{useCallback,useEffect,useRef,useState} from 'react';
import DeviceForm from './DeviceForm.jsx';
import DeviceCanvas from './DeviceCanvas.jsx';
import PortTable from './PortTable.jsx';
import ConnectionMap from './ConnectionMap.jsx';
import { isAppliance } from './connections.js';
import ViewTabs from '../../components/ViewTabs.jsx';
import useUnsavedChanges from '../../components/useUnsavedChanges.js';
import PortEditor from './PortEditor.jsx';
import DeviceHistory from './DeviceHistory.jsx';
import { listDevices,getDevice,deleteDevice } from './api.js';
import { VENDORS } from './logic.js';
import './device-visualization.css';
export default function DeviceVisualization() {
  const [page,setPage]=useState({items:[],total:0}),[query,setQuery]=useState(''),[type,setType]=useState(''),[vendor,setVendor]=useState(''),[offset,setOffset]=useState(0);
  const [selectedId,setSelectedId]=useState(null),[device,setDevice]=useState(null),[selectedPort,setSelectedPort]=useState(null),[mode,setMode]=useState('browse');
  const [listLoading,setListLoading]=useState(true),[listError,setListError]=useState(null),[detailLoading,setDetailLoading]=useState(false),[detailError,setDetailError]=useState(null);
  const [draftEpoch,setDraftEpoch]=useState(0);
  const [busy,setBusy]=useState(false),[dirty,setDirty]=useState(false),[notice,setNotice]=useState(''),[confirmDelete,setConfirmDelete]=useState(false),[deleteError,setDeleteError]=useState(null);
  const [listOpen,setListOpen]=useState(true);
  const [portView,setPortView]=useState(()=>typeof window !== 'undefined' && window.matchMedia('(max-width: 899px)').matches?'table':'panel');
  useUnsavedChanges(dirty,busy);
  const alive=useRef(true),portRef=useRef(null);
  portRef.current=selectedPort;
  const selectionSeq=useRef(0),listSeq=useRef(0),selectedRef=useRef(null),modeRef=useRef('browse');
  selectedRef.current=selectedId;modeRef.current=mode;
  const select=useCallback(async id=>{
    const ticket=++selectionSeq.current;
    setSelectedId(id);setSelectedPort(null);setDevice(null);setDetailError(null);setDetailLoading(true);setMode('browse');setConfirmDelete(false);setDeleteError(null);setDirty(false);
    try {const data=await getDevice(id);if(ticket===selectionSeq.current){setDevice(data);if(isAppliance(data))setListOpen(false);setPortView(data.deviceType==='cable-management'?'panel':isAppliance(data)?'connections':window.matchMedia('(max-width: 899px)').matches?'table':'panel');}}
    catch(e){if(ticket===selectionSeq.current)setDetailError(e.message);}
    finally {if(ticket===selectionSeq.current)setDetailLoading(false);}
  },[]);
  const refresh=useCallback(async()=>{
    if(!alive.current)return;
    const ticket=++listSeq.current;setListLoading(true);setListError(null);
    try {
      const data=await listDevices({query,deviceType:type,vendor,limit:20,offset});
      if(ticket!==listSeq.current)return;
      if(offset>0&&offset>=data.total){setOffset(Math.max(0,Math.floor(Math.max(0,data.total-1)/20)*20));return;}
      setPage(data);
      if(!selectedRef.current&&modeRef.current==='browse'&&data.items.length)select(data.items[0].id);
    } catch(e){if(ticket===listSeq.current)setListError(e.message);}
    finally {if(ticket===listSeq.current)setListLoading(false);}
  },[query,type,vendor,offset,select]);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;selectionSeq.current++;listSeq.current++;};},[]);
  useEffect(()=>{refresh();},[refresh]);
  const guard=action=>{
    if(busy)return;
    if(dirty) {
      if(!window.confirm('Discard unsaved changes?'))return;
      setDraftEpoch(n=>n+1);setMode('browse');setSelectedPort(null);setConfirmDelete(false);
    }
    setDirty(false);action();
  };
  const saved=data=>{
    if(!alive.current)return;
    if(selectedRef.current!==data.id){setPortView(data.deviceType==='cable-management'?'panel':isAppliance(data)?'connections':window.matchMedia('(max-width: 899px)').matches?'table':'panel');if(isAppliance(data))setListOpen(false);}
    setSelectedId(data.id);setDevice(data);setDirty(false);setMode('browse');setNotice(`Saved ${data.name}.`);setConfirmDelete(false);refresh();
    const portId=portRef.current;
    if(portId)requestAnimationFrame(()=>{if(alive.current&&selectedRef.current===data.id&&portRef.current===portId)(document.getElementById(`sv-map-port-${portId}`)||document.getElementById(`sv-port-${portId}`))?.focus();});
  };
  const remove=async()=>{
    setBusy(true);setDeleteError(null);
    try {
      await deleteDevice(device.id,{expectedVersion:device.version,confirmDelete:true});
      if(!alive.current)return;
      setNotice(`Deleted ${device.name}. History remains available under device #${device.id}.`);
      selectionSeq.current++;selectedRef.current=null;setSelectedId(null);setDevice(null);setSelectedPort(null);setConfirmDelete(false);setDirty(false);refresh();
    } catch(e){setDeleteError(e.message);}
    finally {setBusy(false);}
  };
  const port=device?.ports.find(p=>p.id===selectedPort);
  const choosePort=id=>guard(()=>{setSelectedPort(id);setListOpen(false);});
  return <div className="sv-tool">
    <div className="nt-tool-header sv-page-heading"><div><h2>Device Visualization</h2><p>Document interfaces and connections on routers, firewalls, switches, servers and storage arrays.</p></div><div className="sv-heading-actions">
      <button className="tool-btn tool-btn-ghost" aria-expanded={listOpen} onClick={()=>setListOpen(value=>!value)}>Browse devices</button>
      <button className="tool-btn tool-btn-primary" disabled={busy} onClick={()=>guard(()=>{setMode('create');setSelectedPort(null);setConfirmDelete(false);})}>New device</button>
    </div></div>
    <p className="sv-notice" role="status" aria-live="polite">{notice||''}</p>
    <div className={`sv-layout ${listOpen?"":"sv-list-hidden"} ${port&&mode==='browse'&&!confirmDelete?"sv-has-inspector":""}`}>
      <aside className="tool-panel sv-sidebar" aria-label="Device list">
        <fieldset disabled={busy} className="sv-form-fields">
          <label>Search devices<input className="tool-input" maxLength={100} value={query} onChange={e=>{const value=e.target.value;guard(()=>{setQuery(value);setOffset(0);});}}/></label>
          <div className="sv-filters"><label>Type<select aria-label="Type" className="tool-input" value={type} onChange={e=>{const value=e.target.value;guard(()=>{setType(value);if(value&&value!=='firewall')setVendor('');setOffset(0);});}}><option value="">All types</option><option value="switch">Switch</option><option value="router">Router</option><option value="firewall">Firewall</option><option value="server">Server</option><option value="storage">Storage array</option><option value="cable-management">Cable management panel</option></select></label><label>Vendor<select aria-label="Vendor" className="tool-input" value={vendor} disabled={type!==''&&type!=='firewall'} onChange={e=>{const value=e.target.value;guard(()=>{setVendor(value);setOffset(0);});}}><option value="">All vendors</option>{Object.entries(VENDORS).map(([id,name])=><option value={id} key={id}>{name}</option>)}</select></label></div>
        </fieldset>
        {listLoading&&<p role="status">Loading devices…</p>}
        {listError&&<p className="tool-error" role="alert">{listError}<button className="tool-btn tool-btn-ghost" onClick={refresh}>Retry list</button></p>}
        {!listLoading&&!page.total&&!listError&&<p className="tool-hint">{query||type||vendor?'No devices match these filters.':'No devices saved yet. Create a device to map its ports.'}</p>}
        <ul className="sv-device-list">{page.items.map(item=><li key={item.id}><button disabled={busy} aria-pressed={item.id===selectedId} className={item.id===selectedId?'sv-device-active':''} onClick={()=>guard(()=>select(item.id))}><strong>{item.name}</strong><span>{item.deviceType==='firewall'?VENDORS[item.vendor]:item.deviceType} · {item.portCount} ports · {item.assignedPortCount} assigned</span></button></li>)}</ul>
        <p className="tool-hint">{page.total} devices{page.total?` · ${offset+1}–${Math.min(offset+20,page.total)}`:''}</p>
        <div className="sv-pagination"><button className="tool-btn tool-btn-ghost" disabled={busy||offset===0} onClick={()=>guard(()=>setOffset(n=>Math.max(0,n-20)))}>Previous</button><button className="tool-btn tool-btn-ghost" disabled={busy||offset+20>=page.total} onClick={()=>guard(()=>setOffset(n=>n+20))}>Next</button></div>
        <button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>guard(()=>{setMode('history');setSelectedPort(null);})}>Device history</button>
      </aside>
      <section className="tool-panel sv-detail" aria-label="Device details">
        {(mode==='create'||mode==='edit')&&<DeviceForm key={`${mode}-${device?.id||'new'}-${device?.version||0}-${draftEpoch}`} device={mode==='edit'?device:null} onSaved={saved} onCancel={()=>guard(()=>setMode('browse'))} onDirty={setDirty} onBusy={setBusy} onReload={()=>guard(()=>select(selectedId))}/>}
        {mode==='history'&&<DeviceHistory key={selectedId||'lookup'} deviceId={selectedId}/>}
        {mode==='browse'&&<>
          {detailLoading&&<p role="status">Loading device…</p>}
          {detailError&&<p className="tool-error" role="alert">{detailError}<button className="tool-btn tool-btn-ghost" onClick={()=>select(selectedId)}>Retry device</button></p>}
          {!device&&!detailLoading&&!detailError&&<div className="tool-empty">Create or select a device to view its physical ports.</div>}
          {device&&!detailLoading&&<>
            <header className="sv-device-heading"><div><h3>{device.name}</h3><p className="tool-hint">{device.rackId?`${device.dataCenterName} / ${device.rackName} · U${device.rackPosition}–U${device.rackPosition+device.heightU-1}`:'Unassigned to a rack'} · {device.heightU?`${device.heightU}U`:'Height not recorded'}</p><p>{device.description||'No description'}<span className="tool-hint"> · #{device.id} · {device.portCount} ports · {device.assignedPortCount} assigned</span></p></div><div className="sv-heading-actions"><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>guard(()=>{setMode('edit');setSelectedPort(null);})}>Edit device</button><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>guard(()=>{setConfirmDelete(true);setSelectedPort(null);})}>Delete device</button></div></header>
            {confirmDelete&&<div className="sv-review" role="region" aria-label="Device deletion review"><h4>Delete {device.name}?</h4><p>This removes the {device.deviceType}, {device.portCount} sockets and {device.assignedPortCount} destinations. History will remain.</p><button className="tool-btn tool-btn-primary" disabled={busy} onClick={remove}>{busy?'Deleting…':'Confirm delete'}</button><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>setConfirmDelete(false)}>Cancel delete</button>{deleteError&&<p role="alert" className="tool-error">{deleteError}<button className="tool-btn tool-btn-ghost" onClick={()=>select(selectedId)}>Reload current device</button></p>}</div>}
            <ViewTabs items={[...(isAppliance(device)?[{id:'connections',label:'Connections'}]:[]),{id:'panel',label:'Panel'},{id:'table',label:'Port table'},{id:'history',label:'History'}]} value={portView} label="Device views" onChange={value=>guard(()=>{setPortView(value);setSelectedPort(null);})}/>
            {portView==='connections'&&isAppliance(device)&&<div className="sv-appliance-overview"><DeviceCanvas device={device} selectedPort={selectedPort} onSelectPort={choosePort} disabled={busy||confirmDelete}/><ConnectionMap key={device.id} device={device} selectedPort={selectedPort} onSelectPort={choosePort} disabled={busy||confirmDelete}/></div>}
            {portView==='panel'&&<DeviceCanvas device={device} selectedPort={selectedPort} onSelectPort={choosePort} disabled={busy||confirmDelete}/>}
            {portView==='table'&&<PortTable device={device} selectedPort={selectedPort} onSelectPort={choosePort} disabled={busy||confirmDelete}/>}
            {portView==='history'&&<DeviceHistory deviceId={device.id}/>}
            {device.deviceType!=='cable-management'&&!confirmDelete&&!port&&portView!=='history'&&<p className="sv-select-hint">Select an interface to edit its IP, VLAN, label or destination.</p>}
          </>}
        </>}
      </section>
      {port&&mode==='browse'&&!confirmDelete&&<aside className="tool-panel sv-port-inspector" aria-label="Selected port">
        <div className="sv-inspector-heading"><span>{dirty?'Unsaved changes':'Port assignment'}</span><button className="tool-btn tool-btn-ghost" aria-label="Close port editor" onClick={()=>guard(()=>setSelectedPort(null))}>Close</button></div>
        <PortEditor key={`${port.id}-${device.version}-${draftEpoch}`} device={device} port={port} onSaved={saved} onDirty={setDirty} onBusy={setBusy} onReload={()=>guard(()=>select(selectedId))}/>
      </aside>}
    </div>
  </div>;
}
