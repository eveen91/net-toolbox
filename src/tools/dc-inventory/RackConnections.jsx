import React,{useEffect,useState} from 'react';
import {getConnections,disconnectPorts} from './api.js';
import ConnectionDiagram from './ConnectionDiagram.jsx';
import ConnectionForm from './ConnectionForm.jsx';
import {endpointText,locationText,connectionBundles} from './connectionLayout.js';
export default function RackConnections({rack,revision,onChanged,onGuard,onDirty,onBusy,onNavigateRack,busy}) {
  const [data,setData]=useState(null),[error,setError]=useState(null),[reload,setReload]=useState(0),[offset,setOffset]=useState(0),[deviceId,setDeviceId]=useState('');
  const [selectedId,setSelectedId]=useState(null),[form,setForm]=useState(false),[confirm,setConfirm]=useState(false),[deleteError,setDeleteError]=useState(null);
  useEffect(()=>{
    let active=true;setData(null);setError(null);setConfirm(false);setDeleteError(null);
    getConnections(rack.id,{deviceId,offset,limit:20}).then(result=>{if(active){if(offset&&offset>=result.total){setOffset(0);return;}setData(result);setSelectedId(id=>result.items.some(link=>link.id===id)?id:null);}}).catch(failure=>{if(active)setError(failure.message);});
    return()=>{active=false;};
  },[rack.id,revision,reload,deviceId,offset]);
  const [scope,setScope]=useState(null);
  useEffect(()=>setScope(null),[data]);
  const bundles=connectionBundles(data?.items||[]);
  const visibleItems=(data?.items||[]).filter(link=>!scope||(scope.type==='device'?[link.source.id,link.target.id].includes(scope.id):bundles.find(bundle=>bundle.key===scope.id)?.items.includes(link)));
  const selected=data?.items.find(link=>link.id===selectedId);
  const changed=()=>{setForm(false);setConfirm(false);setDeleteError(null);onDirty(false);onChanged();};
  const disconnect=async()=>{
    onBusy(true);setDeleteError(null);
    try{await disconnectPorts(selected.id,{expectedVersion:selected.version,confirmDelete:true});changed();}
    catch(failure){setDeleteError(failure.message);}
    finally{onBusy(false);}
  };
  return <section className="di-connections" aria-label="Rack connections"><div className="di-heading"><div><h3>Rack connections</h3><p className="tool-hint">Saved port-to-port cabling · No live link status. Select a cable to highlight its devices.</p></div><button className="tool-btn tool-btn-primary" disabled={busy||form||!rack.devices.some(d=>d.deviceType!=='cable-management')} onClick={()=>onGuard(()=>setForm(true))}>Add connection</button></div>
    {form&&<ConnectionForm rack={rack} onSaved={changed} onCancel={()=>onGuard(()=>setForm(false))} onDirty={onDirty} onBusy={onBusy}/>}
    <label className="di-search">Show connections for<select className="tool-input" value={deviceId} disabled={busy} onChange={event=>{const id=event.target.value;onGuard(()=>{setForm(false);setDeviceId(id);setOffset(0);});}}><option value="">All devices in this rack</option>{rack.devices.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
    {error?<p role="alert" className="tool-error">{error}<button className="tool-btn tool-btn-ghost" onClick={()=>setReload(v=>v+1)}>Retry connections</button></p>:!data?<p role="status">Loading connections…</p>:<>
      <p className="tool-hint">{data.total} connections · Showing {data.total?offset+1:0}–{offset+data.items.length}. The diagram shows this page and directly connected racks. Scroll inside the diagram for other racks and units.</p>
      <ConnectionDiagram data={data} scope={scope} onScope={next=>{setScope(next);setSelectedId(null);setConfirm(false);setDeleteError(null);}} selectedId={selectedId} onSelect={id=>{setSelectedId(id);setConfirm(false);setDeleteError(null);}}/>
      {selected&&<div className="di-cable-detail" role="region" aria-label="Selected connection"><h4>{selected.label||`Connection #${selected.id}`}</h4><div className="di-fields"><p><strong>{endpointText(selected.source)}</strong><br/>{locationText(selected.source)}{selected.source.rackId&&selected.source.rackId!==rack.id&&<><br/><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>onNavigateRack(selected.source)}>Open source rack</button></>}</p><p><strong>{endpointText(selected.target)}</strong><br/>{locationText(selected.target)}{selected.target.rackId&&selected.target.rackId!==rack.id&&<><br/><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>onNavigateRack(selected.target)}>Open destination rack</button></>}</p></div>{!confirm?<button className="tool-btn tool-btn-ghost" disabled={busy||form} onClick={()=>setConfirm(true)}>Disconnect cable</button>:<div role="region" aria-label="Disconnection review"><p>Disconnect these two ports? Devices, port settings and “Leads to” notes will remain.</p><div className="di-actions"><button className="tool-btn tool-btn-primary" disabled={busy} onClick={disconnect}>Confirm disconnect</button><button className="tool-btn tool-btn-ghost" disabled={busy} onClick={()=>setConfirm(false)}>Keep connection</button></div></div>}{deleteError&&<p role="alert" className="tool-error">{deleteError}<button className="tool-btn tool-btn-ghost" onClick={()=>setReload(v=>v+1)}>Reload connections</button></p>}</div>}
      <h4>Connection list {scope&&`· ${visibleItems.length} on this page`}</h4>{data.items.length?<ul className="di-connection-list">{visibleItems.map(link=><li key={link.id}><button className={link.id===selectedId?'di-connection-active':''} type="button" aria-pressed={link.id===selectedId} onClick={()=>{setSelectedId(link.id);setConfirm(false);setDeleteError(null);}}><strong>{link.label||`Connection #${link.id}`}</strong><span>{endpointText(link.source)} ↔ {endpointText(link.target)}</span><small>{locationText(link.source)} ↔ {locationText(link.target)}</small></button></li>)}</ul>:<div className="tool-empty">No saved physical connections match this view. Use Add connection to choose both ports. Free-text “Leads to” notes are not converted automatically.</div>}
      <div className="di-actions"><button className="tool-btn tool-btn-ghost" disabled={busy||!offset} onClick={()=>onGuard(()=>{setForm(false);setOffset(v=>v-20);})}>Previous connections</button><button className="tool-btn tool-btn-ghost" disabled={busy||offset+20>=data.total} onClick={()=>onGuard(()=>{setForm(false);setOffset(v=>v+20);})}>Next connections</button></div>
    </>}
  </section>;
}
