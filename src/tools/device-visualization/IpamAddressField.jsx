import React,{useEffect,useRef,useState} from 'react';
import {useAuth} from '../../auth/AuthContext.jsx';
import {canIpam} from '../ipam/permissions.js';
import {listSubnets,getSubnetAddresses} from '../ipam/api.js';
import {bestSubnetForAddress} from '../ipam/logic.js';

function AddressPicker({initialValue,onSelect,onClose,disabled}) {
  const initial=useRef(initialValue);
  const [subnets,setSubnets]=useState(null),[subnetId,setSubnetId]=useState(''),[query,setQuery]=useState(''),[status,setStatus]=useState('');
  const [page,setPage]=useState(null),[offset,setOffset]=useState(0),[error,setError]=useState(null),[subnetError,setSubnetError]=useState(null),[reload,setReload]=useState(0);
  useEffect(()=>{
    let active=true;setSubnetError(null);
    listSubnets().then(items=>{if(active){setSubnets(items);setSubnetId(current=>items.some(item=>String(item.id)===current)?current:String(bestSubnetForAddress(items,initial.current)?.id||items[0]?.id||''));}}).catch(failure=>{if(active)setSubnetError(failure.message);});
    return()=>{active=false;};
  },[reload]);
  useEffect(()=>{
    let active=true;setPage(null);setError(null);
    if(!subnetId)return()=>{active=false;};
    const timer=setTimeout(()=>getSubnetAddresses(subnetId,{query:query.trim(),status,limit:25,offset}).then(result=>{
      if(!active)return;
      if(offset&&offset>=result.total){setOffset(0);return;}
      setPage({...result,filter:JSON.stringify([subnetId,query,status,offset])});
    }).catch(failure=>{if(active)setError(failure.message);}),200);
    return()=>{active=false;clearTimeout(timer);};
  },[subnetId,query,status,offset,reload]);
  const visiblePage=page?.filter===JSON.stringify([subnetId,query,status,offset])?page:null;
  const subnet=subnets?.find(item=>String(item.id)===subnetId);
  return <section className="sv-destination-picker" aria-label="Choose IP address from IPAM" onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onClose();}}}>
    <label>IPAM subnet<select autoFocus aria-label="IPAM subnet" className="tool-input" value={subnetId} disabled={disabled||!subnets} onChange={event=>{setSubnetId(event.target.value);setOffset(0);}}><option value="">Choose a subnet</option>{subnets?.map(item=><option key={item.id} value={item.id}>{item.cidr}{item.description?` · ${item.description}`:''}</option>)}</select></label>
    <label>Find IPAM address<input type="search" className="tool-input" maxLength={100} value={query} disabled={disabled} onChange={event=>{setQuery(event.target.value);setOffset(0);}} onKeyDown={event=>{if(event.key==='Enter')event.preventDefault();}} placeholder="IP, hostname or description in this subnet"/></label>
    <label>Address status<select aria-label="Address status" className="tool-input" value={status} disabled={disabled} onChange={event=>{setStatus(event.target.value);setOffset(0);}}><option value="">All statuses</option><option value="free">Free</option><option value="used">Used</option><option value="reserved">Reserved</option></select></label>
    <p className="tool-hint">Recorded addresses in the current tenant. Choosing an address fills the field; Save assignment applies it. Used, reserved and locked entries keep their IPAM protections.</p>
    {subnetError||error?<p className="tool-error" role="alert">{subnetError||error} <button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>setReload(value=>value+1)}>Retry IPAM addresses</button></p>:!subnets?<p role="status">Loading IPAM subnets…</p>:!subnets.length?<p className="tool-hint">No subnets in IPAM. You can enter an IP manually.</p>:!subnetId?<p className="tool-hint">Choose a subnet to list its recorded addresses.</p>:!visiblePage?<p role="status">Loading IPAM addresses…</p>:<>
      {visiblePage.addresses.length?<ul className="sv-destination-options">{visiblePage.addresses.map(item=><li key={item.id}><button type="button" disabled={disabled} onClick={()=>onSelect({...item,subnetCidr:subnet.cidr})}><strong>{item.address}</strong><span>{subnet.cidr} · {item.status}{item.locked?' · Locked':''}</span><small>{item.hostname||'No hostname'}{item.description?` · ${item.description}`:''}</small></button></li>)}</ul>:<p className="tool-hint">No recorded addresses match these filters. Change the subnet or enter an IP manually.</p>}
      <p className="tool-hint" role="status">{visiblePage.total?`${offset+1}–${offset+visiblePage.addresses.length} of ${visiblePage.total}`:'0 recorded addresses'}</p>
      <div className="sv-destination-actions"><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled||!offset} onClick={()=>setOffset(value=>value-25)}>Previous addresses</button><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled||offset+25>=visiblePage.total} onClick={()=>setOffset(value=>value+25)}>Next addresses</button></div>
    </>}
    <button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={onClose}>Close IPAM picker</button>
  </section>;
}

export default function IpamAddressField({value,onChange,disabled=false}) {
  const {user,loginRequired}=useAuth();
  const canRead=user?canIpam(user,'ipam.read'):!loginRequired;
  const [open,setOpen]=useState(false),[selected,setSelected]=useState(null);
  const input=useRef(null),trigger=useRef(null);
  const close=()=>{setOpen(false);trigger.current?.focus();};
  return <>
    <label>IP address (optional)<input ref={input} className="tool-input" maxLength={64} value={value} disabled={disabled} onChange={event=>{setSelected(null);onChange(event.target.value);}} placeholder="192.0.2.1/24 or 2001:db8::1/64" aria-describedby="sv-port-ip-hint" spellCheck={false}/></label>
    {canRead&&<button ref={trigger} type="button" className="tool-btn tool-btn-ghost" disabled={disabled} aria-expanded={open} onClick={()=>setOpen(current=>!current)}>Choose from IPAM</button>}
    {open&&canRead&&<AddressPicker initialValue={value} disabled={disabled} onClose={close} onSelect={item=>{setSelected(item);onChange(item.address);setOpen(false);input.current?.focus();}}/>}
    {selected&&<p className="tool-hint" role="status">Selected {selected.address} · {selected.subnetCidr} · {selected.status}{selected.locked?' · Locked':''}. Save assignment to apply this address.</p>}
  </>;
}
