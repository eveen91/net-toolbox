import React,{useMemo} from 'react';
import { CONTROLLERS,FAMILY_NAMES,VENDORS,usesCards,portDescription,effectivePort } from './logic.js';

export default function DeviceFaceplate({device,selectedPort,onSelectPort,disabled}) {
  const groups=useMemo(()=>{
    const data=usesCards(device.deviceType)?device.networkCards:device.portGroups;
    const management=device.ports.filter(p=>p.isManagement).map(p=>({id:p.groupId,controller:p.controller,family:'ethernet',count:1,speedGbps:p.speedGbps,isManagement:true}));
    const expansion=device.expansionGroupId?[{id:device.expansionGroupId,family:'sas',count:device.expansionPortCount,speedGbps:12}]:[];
    return [...data,...management,...expansion];
  },[device]);
  const moveFocus=event=>{
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
    event.preventDefault();
    const buttons=[...event.currentTarget.closest('.sv-face').querySelectorAll('.sv-socket:not(:disabled)')];
    const index=buttons.indexOf(event.currentTarget);
    const target=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(['ArrowLeft','ArrowUp'].includes(event.key)?-1:1)));
    buttons[target]?.focus();
  };
  const renderGroup=group=>{
    const ports=device.ports.filter(p=>p.groupId===group.id);
    const heading=group.family==='sas'?'Shelf expansion':group.isManagement?'Management':usesCards(device.deviceType)?`NIC ${group.slotNumber}${group.name?` · ${group.name}`:''}`:FAMILY_NAMES[group.family];
    return <section className={`sv-port-group sv-port-group-${group.family} ${group.isManagement?'sv-port-group-management':''}`} key={group.id} aria-label={`${group.controller?`Controller ${group.controller} · `:''}${heading}`}>
      <h4>{heading}<span>{group.speedGbps}G{group.family==='sfp'?' default':''} · {group.count} sockets</span></h4>
      <div className="sv-sockets" style={{'--columns':device.deviceType==='switch'?Math.ceil(group.count/2):Math.min(group.count,usesCards(device.deviceType)?8:group.family==='qsfp'?4:8)}}>
        {ports.map(port=><button type="button" id={`sv-port-${port.id}`} key={port.id} disabled={disabled} tabIndex={port.id===selectedPort||(!selectedPort&&device.ports[0]?.id===port.id)?0:-1} onKeyDown={moveFocus}
          aria-pressed={port.id===selectedPort} className={`sv-socket sv-socket-${port.family} ${port.leadsTo?'sv-assigned':''} ${port.id===selectedPort?'sv-selected':''}`} onClick={()=>onSelectPort(port.id)}
          aria-label={`${port.name}, ${portDescription(port)}, ${effectivePort(port).effectiveSpeedGbps} gigabits${port.label?`, label ${port.label}`:''}, ${port.leadsTo?`leads to ${port.leadsTo}`:'unassigned'}${port.ipAddress?`, IP ${port.ipAddress}`:''}${port.portMode?`, ${port.portMode} VLAN ${port.accessVlan||port.trunkVlans}`:''}`} title={`${portDescription(port)}\n${port.ipAddress?`IP ${port.ipAddress}\n`:''}${port.portMode?`${port.portMode} VLAN ${port.accessVlan||port.trunkVlans}\n`:''}${port.name}${port.label?` · ${port.label}`:''}\n${port.leadsTo||'Unassigned'}`}>
          <span className="sv-socket-shape" aria-hidden="true"><span className="sv-contacts"/></span>
          <span className="sv-socket-number">{port.isManagement?'MGMT':device.deviceType==='switch'&&device.portNaming!=='family'?port.name:port.number}<span className="sv-assignment-mark" aria-hidden="true">{port.leadsTo?'●':'○'}</span></span>
          <span className="sv-socket-label">{port.label||`${effectivePort(port).effectiveSpeedGbps}G${port.transceiver==='rj45-1g'?' RJ45':''}`}</span>
        </button>)}
      </div>
    </section>;
  };
  if(device.deviceType==='cable-management')return <div className="sv-chassis"><div className="sv-chassis-caption"><span>RACKMOUNT CABLE MANAGEMENT PANEL</span><span>1U</span></div><p className="tool-hint">Passive cable management panel · No network ports</p></div>;
  const caption=device.deviceType==='server'?'SERVER · REAR PANEL':device.deviceType==='storage-shelf'?'STORAGE EXPANSION SHELF · REAR PANEL':device.deviceType==='storage'?'STORAGE HEAD · REAR PANEL':device.deviceType==='firewall'?VENDORS[device.vendor]:device.deviceType==='router'?'ROUTER · FRONT PANEL':'SWITCH · FRONT PANEL';
  return <div className={`sv-chassis sv-chassis-${device.deviceType} sv-vendor-${device.vendor||'generic'} ${device.deviceType==='switch'&&device.portNaming!=='family'?'sv-naming-numeric':''}`}>
    <div className="sv-chassis-caption"><span>{caption}</span><span>{device.model||'Configurable chassis'}</span></div>
    <p className="sv-sr-only">Markers show saved assignments, not live link status. Scroll to see all sockets.</p>
    <div className="sv-face-scroll" tabIndex={0} role="region" aria-label={`${device.name} physical ports`}>
      <div className={`sv-face sv-face-${device.deviceType}`}>
        {device.deviceType==='storage'?CONTROLLERS.map(controller=><section className="sv-storage-controller" key={controller} aria-label={`Controller ${controller} physical ports`}><h3>Controller {controller}</h3><div className="sv-storage-controller-groups">{groups.filter(g=>g.controller===controller&&g.count>0).map(renderGroup)}</div></section>):groups.filter(g=>g.count>0).map(renderGroup)}{device.deviceType==='storage'&&groups.filter(g=>g.family==='sas').map(renderGroup)}
      </div>
    </div>
    <p className="sv-scroll-hint">Select a socket. Scroll horizontally when ports extend beyond the panel.</p>
    <div className="sv-face-legend"><span>● Assigned</span><span>○ Unassigned</span><span>Outlined socket: selected</span></div>
  </div>;
}
