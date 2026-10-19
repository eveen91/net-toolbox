import {portDescription} from './logic.js';
import React, { useState } from 'react';
import { FAMILY_NAMES, VENDORS } from './logic.js';
import { connectionPorts, hasDocumentation, vlanDescription, networkCardTitle } from './connections.js';

const PAGE_SIZE = 12;
function DeviceSymbol({firewall,storage,server}) {
  return <svg width="36" height="36" viewBox="0 0 36 36" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {server ? <><rect x="4" y="4" width="28" height="28" rx="3"/><path d="M4 18h28M10 10h10m-10 15h10m5-15h1m-1 15h1"/></> : storage ? <><rect x="4" y="5" width="28" height="11" rx="2"/><rect x="4" y="20" width="28" height="11" rx="2"/><path d="M9 10h12m5 0h1M9 25h12m5 0h1"/></> : firewall ? <><path d="M18 3 30 8v9c0 7-5 12-12 16C11 29 6 24 6 17V8Z"/><path d="M11 14h14M11 20h14m-9-6v6m5 0v5"/></> : <><rect x="3" y="9" width="30" height="20" rx="3"/><path d="M9 15h8m-3-3 3 3-3 3m13 6h-8m3-3-3 3 3 3"/></>}
  </svg>;
}
function Arrow() {
  return <svg className="sv-connection-arrow" width="32" height="16" viewBox="0 0 32 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" focusable="false"><path d="M1 8h28m-5-5 5 5-5 5"/></svg>;
}
export default function ConnectionMap({device, selectedPort, onSelectPort, disabled}) {
  const [query,setQuery] = useState('');
  const [scope,setScope] = useState('documented');
  const [controller,setController] = useState('all');
  const [cardId,setCardId] = useState('all');
  const [page,setPage] = useState(0);
  const ports = device.deviceType==='server'?device.ports.map(port=>({...port,cardName:device.networkCards.find(card=>card.id===port.groupId)?.name||''})):device.ports;
  const matching = connectionPorts(ports, query, scope, controller, cardId);
  const currentPage = Math.min(page, Math.max(0,Math.ceil(matching.length / PAGE_SIZE) - 1));
  const visible = matching.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const documented = device.ports.filter(hasDocumentation).length;
  return <section className="sv-connection-map" aria-label="Interface connection map">
    <div className="sv-map-heading"><div><h4>Interface connections</h4><p>Follow an interface to its saved address and destination.</p></div><span>{documented} of {device.ports.length} interfaces documented</span></div>
    <div className={`sv-map-controls ${['storage','server'].includes(device.deviceType)?'sv-map-controls-grouped':''}`}>
      <label>Find interface<input className="tool-input" type="search" value={query} onChange={event=>{setQuery(event.target.value);setPage(0);}} placeholder="Interface, IP, VLAN or destination"/></label>
      <label>Show interfaces<select className="tool-input" value={scope} onChange={event=>{setScope(event.target.value);setPage(0);}}><option value="documented">With saved details</option><option value="all">All interfaces</option><option value="management">Management only</option></select></label>
      {device.deviceType==='storage'&&<label>Controller<select className="tool-input" value={controller} onChange={event=>{setController(event.target.value);setPage(0);}}><option value="all">Both controllers</option><option value="A">Controller A</option><option value="B">Controller B</option></select></label>}
      {device.deviceType==='server'&&<label>Network card<select className="tool-input" value={cardId} onChange={event=>{setCardId(event.target.value);setPage(0);}}><option value="all">All network cards</option>{device.networkCards.map(card=><option key={card.id} value={String(card.id)}>NIC {card.slotNumber}{card.name?` · ${card.name}`:''}</option>)}</select></label>}
    </div>
    <div className="sv-map-layout">
      <div className="sv-map-device"><DeviceSymbol firewall={device.deviceType==='firewall'} storage={['storage','storage-shelf'].includes(device.deviceType)} server={device.deviceType==='server'}/><strong>{device.name}</strong><span>{device.deviceType==='firewall' ? VENDORS[device.vendor] : device.deviceType==='storage'?'Storage array · Controllers A / B':device.deviceType==='server'?'Server · Network cards':device.deviceType==='storage-shelf'?'Storage expansion shelf':'Router'}</span>{device.model&&<span>{device.model}</span>}<span className="sv-map-device-count">{device.ports.filter(p=>p.ipAddress).length} IP · {device.ports.filter(p=>p.portMode).length} VLAN · {device.assignedPortCount} destinations</span></div>
      <div className="sv-map-branches">
        {visible.length>0 ? <ul className="sv-map-list">{visible.map((port,index)=><li key={port.id}>
          {device.deviceType==='storage'&&(index===0||visible[index-1].controller!==port.controller)&&<h5 className="sv-map-controller-heading">{port.family==='sas'?'Shelf expansion':`Controller ${port.controller}`}</h5>}
          {device.deviceType==='server'&&(index===0||visible[index-1].groupId!==port.groupId)&&<h5 className="sv-map-controller-heading">{networkCardTitle(port,device.networkCards)}</h5>}
          <button type="button" id={`sv-map-port-${port.id}`} className={`sv-connection ${selectedPort===port.id?'sv-connection-selected':''}`} aria-pressed={selectedPort===port.id} disabled={disabled} onClick={()=>onSelectPort(port.id)}>
            <span className="sv-connection-port"><strong>{port.label || port.name}</strong><span>{port.label && !port.isManagement ? `${port.name} · ` : port.controller ? `Controller ${port.controller} · ` : ''}{port.isManagement?'MGMT · ':''}{portDescription(port)}</span></span>
            <span className="sv-connection-config">{port.ipAddress ? <span className="sv-connection-ip">{port.ipAddress}</span> : <span className="sv-map-unspecified">{port.family==='sas'?'Storage expansion':'No IP recorded'}</span>}{port.portMode&&<span>{vlanDescription(port)}</span>}</span>
            <Arrow/><span className={`sv-connection-destination ${port.leadsTo?'':'sv-map-unspecified'}`}><span>Leads to</span><strong>{port.leadsTo || 'Destination not recorded'}</strong></span>
          </button>
        </li>)}</ul> : <div className="sv-map-empty"><p>{query || cardId!=='all' || controller!=='all' ? 'No interfaces match these filters.' : scope==='management' ? 'No dedicated management port on this device.' : 'No interfaces with saved details yet.'}</p><button type="button" className="tool-btn tool-btn-ghost" onClick={()=>{setQuery('');setScope('all');setController('all');setCardId('all');setPage(0);}}>Show all interfaces</button></div>}
      </div>
    </div>
    <div className="sv-map-footer"><span role="status">{matching.length ? `${currentPage * PAGE_SIZE + 1}–${Math.min((currentPage + 1) * PAGE_SIZE,matching.length)} of ${matching.length} interfaces` : '0 interfaces shown'}</span>{matching.length>PAGE_SIZE&&<div><button type="button" className="tool-btn tool-btn-ghost" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Previous interfaces</button><button type="button" className="tool-btn tool-btn-ghost" disabled={(currentPage+1)*PAGE_SIZE>=matching.length} onClick={()=>setPage(currentPage+1)}>Next interfaces</button></div>}</div>
    <p className="sv-map-note">Connections are saved “Leads to” entries. The diagram does not indicate live link state or traffic direction.</p>
  </section>;
}
