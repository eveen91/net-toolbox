import CreateHardwareDialog from './CreateHardwareDialog.jsx';
import React,{useEffect,useState} from 'react';
import {useAuth} from '../../auth/AuthContext.jsx';
import {canLeaveWorkspace} from '../../components/navigation.js';
import {getInventoryLinks} from './api.js';

export default function InventoryLinks({ip,address,onCreated}) {
  const {user,loginRequired}=useAuth();
  const allowed=user?(user.permissions||[]).some(permission=>permission==='*'||permission==='dc-inventory'):!loginRequired;
  const canCreate=!!address&&(user?['device-visualization','ipam.write'].every(feature=>(user.permissions||[]).includes('*')||(user.permissions||[]).includes(feature)||(feature==='ipam.write'&&(user.permissions||[]).includes('ipam'))):!loginRequired);
  const [creating,setCreating]=useState(false),[createdNotice,setCreatedNotice]=useState(''),[refreshError,setRefreshError]=useState(null);
  const [page,setPage]=useState(null),[error,setError]=useState(null),[reload,setReload]=useState(0),[offset,setOffset]=useState(0);
  useEffect(()=>{setOffset(0);},[ip]);
  useEffect(()=>{
    let active=true;setPage(null);setError(null);
    if(allowed)getInventoryLinks(ip,offset).then(result=>{if(active)setPage(result);}).catch(failure=>{if(active)setError(failure.message);});
    return()=>{active=false;};
  },[allowed,ip,offset,reload]);
  const created=device=>{
    setCreating(false);setCreatedNotice(`Created ${device.name}. Its IP is assigned and its inventory location is saved.`);setReload(value=>value+1);
    Promise.resolve().then(()=>onCreated?.()).catch(failure=>setRefreshError(failure.message));
  };
  if(!allowed&&!canCreate)return null;
  return <section className="ip-inventory-links" aria-label="Hardware in DC Inventory"><h4>Hardware inventory</h4>
    {canCreate&&<><button type="button" className="tool-btn tool-btn-ghost" disabled={!!address.locked||!!page?.total||creating||!!createdNotice} onClick={()=>setCreating(true)}>Add device</button>{address.locked&&<p className="tool-hint">Unlock this address before assigning new hardware.</p>}{!!page?.total&&<p className="tool-hint">This IP is already documented on hardware. Use its existing inventory link.</p>}</>}
    {creating&&<CreateHardwareDialog address={address} onCreated={created} onClose={()=>setCreating(false)}/>}
    {createdNotice&&<p role="status">{createdNotice}</p>}
    {refreshError&&<p role="alert">Hardware was created, but the IPAM details could not refresh: {refreshError} <button type="button" className="tool-btn tool-btn-ghost" onClick={()=>Promise.resolve().then(()=>onCreated?.()).then(()=>setRefreshError(null)).catch(failure=>setRefreshError(failure.message))}>Retry address refresh</button></p>}
    {allowed&&<>
    {error?<p role="alert">{error} <button type="button" className="tool-btn tool-btn-ghost" onClick={()=>setReload(value=>value+1)}>Retry hardware lookup</button></p>:!page?<p role="status" className="tool-hint">Looking up hardware…</p>:page.items.length?<><ul>{page.items.map(device=><li key={device.portId}><a href={`#/dc-inventory?device=${device.id}`} onClick={event=>{if(!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&!canLeaveWorkspace())event.preventDefault();}}><strong>{device.name}</strong> · {device.portName}<span>{device.rackId?`${device.dataCenterName} / ${device.rackName} · U${device.rackPosition}–U${device.rackPosition+device.heightU-1}`:'Unassigned to a rack'} →</span></a></li>)}</ul>{page.total>25&&<div className="sv-heading-actions"><button className="tool-btn tool-btn-ghost" disabled={!offset} onClick={()=>setOffset(value=>value-25)}>Previous hardware</button><span>{offset+1}–{offset+page.items.length} of {page.total}</span><button className="tool-btn tool-btn-ghost" disabled={offset+25>=page.total} onClick={()=>setOffset(value=>value+25)}>Next hardware</button></div>}</>:<p className="tool-hint">No device interface currently documents this IP.</p>}
    </>}
  </section>;
}
