import React from 'react';
import useCatalog from './useCatalog.js';
import './dc-inventory.css';

export default function LocationFields({draft,onChange,disabled=false,deviceAccess=true,fixedHeight=false}) {
  const {dc,racks,loading,error,moreDC,moreRacks,retry}=useCatalog(draft.dataCenterId,deviceAccess);
  return <fieldset disabled={disabled} className="di-location-fields"><legend>DC / rack location</legend>
    <div className="di-fields">
      <label>Device height (U)<input className="tool-input" type="number" min={1} max={100} step={1} required readOnly={fixedHeight} value={draft.heightU??''} onChange={event=>onChange({heightU:event.target.value===''?null:Number(event.target.value)})}/></label>
      <label>Data center<select aria-label="Data center" className="tool-input" value={draft.dataCenterId||''} disabled={loading.dc} onChange={event=>{const id=Number(event.target.value)||null;onChange({dataCenterId:id,dataCenterName:dc.items.find(item=>item.id===id)?.name||null,rackId:null,rackName:null,rackPosition:null});}}><option value="">Not assigned</option>{draft.dataCenterId&&!dc.items.some(item=>item.id===draft.dataCenterId)&&<option value={draft.dataCenterId}>{draft.dataCenterName||`DC #${draft.dataCenterId}`}</option>}{dc.items.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Rack<select aria-label="Rack" className="tool-input" disabled={!draft.dataCenterId||loading.racks} value={draft.rackId||''} onChange={event=>{const id=Number(event.target.value)||null;onChange({rackId:id,rackName:racks.items.find(item=>item.id===id)?.name||null,rackPosition:null});}}><option value="">Not assigned</option>{draft.rackId&&!racks.items.some(item=>item.id===draft.rackId)&&<option value={draft.rackId}>{draft.rackName||`Rack #${draft.rackId}`}</option>}{racks.items.map(item=><option key={item.id} value={item.id}>{item.name} · {item.heightU}U</option>)}</select></label>
      <label>Starting U (bottom)<input className="tool-input" type="number" min={1} max={100} step={1} required={!!draft.rackId} disabled={!draft.rackId} value={draft.rackPosition??''} onChange={event=>onChange({rackPosition:event.target.value===''?null:Number(event.target.value)})}/></label>
    </div>
    <p className="tool-hint">U1 is at the bottom. {draft.rackId&&draft.rackPosition&&draft.heightU?`This device occupies U${draft.rackPosition}–U${draft.rackPosition+draft.heightU-1}.`:'Devices without a rack stay in the Unassigned list.'} Manage data centers and rack capacity in DC Inventory.</p>
    {dc.items.length<dc.total&&<button type="button" className="tool-btn tool-btn-ghost" disabled={loading.dc} onClick={moreDC}>Load more data centers</button>}
    {racks.items.length<racks.total&&<button type="button" className="tool-btn tool-btn-ghost" disabled={loading.racks} onClick={moreRacks}>Load more racks</button>}
    {loading.dc||loading.racks?<p role="status" className="tool-hint">Loading locations…</p>:null}
    {error&&<p className="tool-error" role="alert">{error}<button type="button" className="tool-btn tool-btn-ghost" onClick={retry}>Retry locations</button></p>}
  </fieldset>;
}
