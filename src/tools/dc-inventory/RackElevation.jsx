import React from 'react';
import {rackRows,unitRange} from './rackLogic.js';
export default function RackElevation({rack,onSelect,selectedId,disabled}) {
  const rows=rackRows(rack.heightU,rack.devices);
  return <section className="di-rack-elevation" aria-label={`${rack.name} rack elevation`}><div className="di-rack-caption"><strong>{rack.name}</strong><span>{rack.usedU} / {rack.heightU}U occupied</span></div>
    <div className="di-rack-scroll" tabIndex={0} role="region" aria-label="Rack units, highest at top">
      <div className="di-rack-grid" style={{gridTemplateRows:`repeat(${rack.heightU},44px)`}}>
        {rows.map((row,index)=><React.Fragment key={row.unit}><span className="di-unit-number" style={{gridColumn:1,gridRow:index+1}}>U{row.unit}</span>{!row.deviceId&&<span className="di-unit-free" style={{gridColumn:2,gridRow:index+1}}><span className="di-sr-only">U{row.unit}: </span>Free</span>}</React.Fragment>)}
        {rack.devices.map(device=><button type="button" key={device.id} className={`di-rack-device ${device.id===selectedId?'di-rack-device-selected':''}`} style={{gridColumn:2,gridRow:`${rack.heightU-device.rackPosition-device.heightU+2} / span ${device.heightU}`}} disabled={disabled} onClick={()=>onSelect(device)} title={`${device.name} · ${unitRange(device)} · ${device.heightU}U`}><strong>{device.name}</strong><span>{device.heightU}U · {device.deviceType==='cable-management'?'Cable management':device.deviceType}</span></button>)}
      </div>
    </div><p className="tool-hint">Front view · U1 at bottom. Select a device to move or unassign it.</p>
  </section>;
}
