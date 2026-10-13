import React,{useMemo} from 'react';
import { FAMILY_NAMES,VENDORS } from './logic.js';
export default function DeviceFaceplate({device,selectedPort,onSelectPort,disabled}) {
  const groups=useMemo(()=>device.deviceType==='server'?device.networkCards:device.portGroups,[device]);
  return <div className={`sv-chassis sv-chassis-${device.deviceType} sv-vendor-${device.vendor||'generic'} ${device.deviceType==='switch'&&device.portNaming!=='family'?'sv-naming-numeric':''}`}>
    <div className="sv-chassis-caption"><span>{device.deviceType==='server'?'SERVER · REAR PANEL':device.deviceType==='firewall'?VENDORS[device.vendor]:'SWITCH · FRONT PANEL'}</span><span>{device.model||'Configurable chassis'}</span></div>
    <p className="sv-sr-only">Markers show saved assignments, not live link status. Scroll to see all sockets.</p>
    <div className="sv-face-scroll" tabIndex={0} role="region" aria-label={`${device.name} physical ports`}>
      <div className={`sv-face sv-face-${device.deviceType}`}>
        {groups.filter(g=>g.count>0).map(group=>{
          const ports=device.ports.filter(p=>p.groupId===group.id);
          const heading=device.deviceType==='server'?`NIC ${group.slotNumber}${group.name?` · ${group.name}`:''}`:FAMILY_NAMES[group.family];
          return <section className={`sv-port-group sv-port-group-${group.family}`} key={group.id} aria-label={heading}>
            <h4>{heading}<span>{group.speedGbps}G · {group.count} sockets</span></h4>
            <div className="sv-sockets" style={{'--columns':device.deviceType==='switch'?Math.ceil(group.count/2):Math.min(group.count,device.deviceType==='server'?8:group.family==='ethernet'?24:group.family==='sfp'?8:4)}}>
              {ports.map(port=><button type="button" id={`sv-port-${port.id}`} key={port.id} disabled={disabled} tabIndex={port.id===selectedPort||(!selectedPort&&device.ports[0]?.id===port.id)?0:-1}
                onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return;event.preventDefault();const buttons=[...event.currentTarget.closest('.sv-face').querySelectorAll('.sv-socket:not(:disabled)')];const index=buttons.indexOf(event.currentTarget);const target=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(['ArrowLeft','ArrowUp'].includes(event.key)?-1:1)));buttons[target]?.focus();}}
                aria-pressed={port.id===selectedPort} className={`sv-socket sv-socket-${port.family} ${port.leadsTo?'sv-assigned':''} ${port.id===selectedPort?'sv-selected':''}`} onClick={()=>onSelectPort(port.id)}
                aria-label={`${port.name}, ${FAMILY_NAMES[port.family]}, ${port.speedGbps} gigabits${port.label?`, label ${port.label}`:''}, ${port.leadsTo?`leads to ${port.leadsTo}`:'unassigned'}${port.portMode?`, ${port.portMode} VLAN ${port.accessVlan||port.trunkVlans}`:''}`} title={`${port.portMode?`${port.portMode} VLAN ${port.accessVlan||port.trunkVlans}\n`:""}${port.name}${port.label?` · ${port.label}`:''}\n${port.leadsTo||'Unassigned'}`}>
                <span className="sv-socket-shape" aria-hidden="true"><span className="sv-contacts"/></span>
                <span className="sv-socket-number">{device.deviceType==='switch'&&device.portNaming!=='family'?port.name:port.number}<span className="sv-assignment-mark" aria-hidden="true">{port.leadsTo?'●':'○'}</span></span>
                <span className="sv-socket-label">{port.label||`${port.speedGbps}G`}</span>
              </button>)}
            </div>
          </section>;
        })}
      </div>
    </div>
    <p className="sv-scroll-hint">Select a socket. Scroll horizontally when ports extend beyond the panel.</p>
    <div className="sv-face-legend"><span>● Assigned</span><span>○ Unassigned</span><span>Outlined socket: selected</span></div>
  </div>;
}
