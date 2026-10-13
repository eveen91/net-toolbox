import React,{useEffect,useState} from 'react';
import { getDeviceAudit } from './api.js';
const ACTIONS={device_create:'Device created',device_update:'Configuration changed',port_update:'Port updated',device_delete:'Device deleted'};
export default function DeviceHistory({deviceId}) {
  const [id,setId]=useState(deviceId||''),[lookup,setLookup]=useState(deviceId||null),[offset,setOffset]=useState(0),[data,setData]=useState(null),[error,setError]=useState(null),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0),[expanded,setExpanded]=useState(null);
  useEffect(()=>{
    if(!lookup)return;
    let active=true;setLoading(true);setError(null);
    getDeviceAudit(lookup,{limit:20,offset}).then(result=>{if(active)setData(result);}).catch(e=>{if(active){setError(e.message);setData(null);}}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[lookup,offset,retry]);
  return <section className="sv-history" aria-label="Device history">
    <h3>History</h3>
    <form className="sv-history-lookup" onSubmit={e=>{e.preventDefault();setLookup(Number(id));setOffset(0);setRetry(r=>r+1);}}><label>Device ID (including deleted)<input className="tool-input" type="number" min={1} step={1} required value={id} onChange={e=>setId(e.target.value)}/></label><button className="tool-btn tool-btn-ghost">Load history</button></form>
    {loading&&<p role="status">Loading history…</p>}
    {error&&<p className="tool-error" role="alert">{error}<button className="tool-btn tool-btn-ghost" onClick={()=>setRetry(r=>r+1)}>Retry</button></p>}
    {data&&!loading&&<><p className="tool-hint">{data.total} audit entries · device #{lookup}</p><ol className="sv-history-list">{data.items.map(entry=><li key={entry.id}><div><strong>{ACTIONS[entry.action]||entry.action}</strong><time>{new Date(entry.createdAt).toLocaleString()}</time><span>Actor: {entry.actorId==null?'Open mode':`account #${entry.actorId}`}</span></div><button className="tool-btn tool-btn-ghost" onClick={()=>setExpanded(expanded===entry.id?null:entry.id)} aria-expanded={expanded===entry.id}>Details</button>{expanded===entry.id&&<div className="sv-audit-diff"><details open><summary>Before</summary><pre>{JSON.stringify(entry.oldValue,null,2)||'No previous record'}</pre></details><details open><summary>After</summary><pre>{JSON.stringify(entry.newValue,null,2)||'Deleted'}</pre></details></div>}</li>)}</ol><div className="sv-pagination"><button className="tool-btn tool-btn-ghost" disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-20))}>Previous history</button><button className="tool-btn tool-btn-ghost" disabled={offset+20>=data.total} onClick={()=>setOffset(n=>n+20)}>Next history</button></div></>}
    {!lookup&&<p className="tool-hint">Select a device or enter its historical ID.</p>}
  </section>;
}
