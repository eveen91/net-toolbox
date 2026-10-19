import React from 'react';

export default function DriveBays({count=0,occupied=[],onChange,disabled=false}) {
  count=Number.isFinite(count)?Math.max(0,Math.min(120,Math.trunc(count))):0;
  const used=new Set(occupied);
  return <section className="sv-drive-bays" aria-label="Drive bays">
    <div className="sv-drive-heading"><h4>Drive bays</h4><span>{used.size} occupied · {count-used.size} empty · {count} total</span></div>
    {count>0?<div className="sv-drive-grid">{Array.from({length:count},(_,index)=>{
      const number=index+1,isOccupied=used.has(number),label=`Bay ${number} · ${isOccupied?'Occupied':'Empty'}`;
      return onChange?<button key={number} type="button" className={`sv-drive-bay ${isOccupied?'sv-drive-occupied':''}`} disabled={disabled} aria-label={label} aria-pressed={isOccupied} onClick={()=>onChange(isOccupied?occupied.filter(n=>n!==number):[...occupied,number].sort((a,b)=>a-b))}><strong>{number}</strong><span>{isOccupied?'Occupied':'Empty'}</span></button>:<div key={number} className={`sv-drive-bay ${isOccupied?'sv-drive-occupied':''}`} aria-label={label}><strong>{number}</strong><span>{isOccupied?'Occupied':'Empty'}</span></div>;
    })}</div>:<p className="tool-hint">No drive bays recorded.</p>}
    <p className="tool-hint">{onChange?'Select a bay to toggle its occupancy. Changes are saved with the device.':'Recorded occupancy · Edit device to change the bay count or occupancy.'}</p>
  </section>;
}
