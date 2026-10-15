import React from 'react';
import { FAMILIES,FAMILY_NAMES,SPEEDS,newCard } from './logic.js';
export default function NetworkCardFields({cards,onChange,title='Network cards',limit=16,onAdd=null}) {
  const change=(key,patch)=>onChange(cards.map(c=>c._key===key?{...c,...patch}:c));
  return <div className="sv-card-fields">
    <h3>{title} <span className="tool-hint">{cards.length} / {limit}</span></h3>
    {cards.map(card=><fieldset className="sv-nic-form" key={card._key}>
      <legend>NIC {card.slotNumber}{card.id?'':' · new'}</legend>
      <label>Card name<input className="tool-input" maxLength={60} value={card.name} onChange={e=>change(card._key,{name:e.target.value})}/></label>
      <label>Connector<select aria-label="Connector" className="tool-input" value={card.family} onChange={e=>change(card._key,{family:e.target.value,speedGbps:SPEEDS[e.target.value][0]})}>{FAMILIES.map(f=><option key={f} value={f}>{FAMILY_NAMES[f]}</option>)}</select></label>
      <label>Sockets (1–8)<input className="tool-input" type="number" min={1} max={8} step={1} value={card.count} onChange={e=>change(card._key,{count:Number(e.target.value)})}/></label>
      <label>Speed<select aria-label="Speed" className="tool-input" value={card.speedGbps} onChange={e=>change(card._key,{speedGbps:Number(e.target.value)})}>{SPEEDS[card.family].map(s=><option value={s} key={s}>{s}G</option>)}</select></label>
      <button type="button" className="tool-btn tool-btn-ghost" onClick={()=>onChange(cards.filter(c=>c._key!==card._key))}>Remove NIC {card.slotNumber}</button>
    </fieldset>)}
    <button type="button" className="tool-btn tool-btn-ghost" disabled={cards.length>=limit} onClick={()=>onAdd?onAdd():onChange([...cards,newCard(cards)])}>Add network card</button>
  </div>;
}
