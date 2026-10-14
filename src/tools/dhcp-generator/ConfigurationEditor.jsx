import React, { useId, useState } from 'react';
import { globalFields, subnetFields, emptySubnet } from './fields.js';

function Field({ spec, value, onChange }) {
  const id = useId();
  return <label className="dhcp-field" htmlFor={id}><span>{spec.label}</span><input id={id} className="tool-input" type={spec.type || 'text'}
    maxLength={spec.max} min={spec.type === 'number' ? 1 : undefined} max={spec.type === 'number' ? 2147483647 : undefined}
    required={spec.required} value={Array.isArray(value) ? value.join(', ') : value ?? ''} onChange={event => onChange(event.target.value)}
    aria-describedby={spec.help ? `${id}-help` : undefined} spellCheck={false} />
    {spec.help && <small id={`${id}-help`} className="tool-hint">{spec.help}</small>}</label>;
}
export default function ConfigurationEditor({ draft, onChange, busy, onSave, saved }) {
  const [index, setIndex] = useState(0);
  const [reservationPage, setReservationPage] = useState(0);
  const subnets = draft.subnets || [];
  const selectedIndex = Math.min(index, Math.max(0, subnets.length - 1));
  const selected = subnets[selectedIndex];
  const reservations = selected?.reservations || [];
  const page = Math.min(reservationPage, Math.max(0, Math.ceil(reservations.length / 25) - 1));
  const changeSubnet = patch => onChange({ ...draft, subnets: subnets.map((subnet, i) => i === selectedIndex ? { ...subnet, ...patch } : subnet) });
  const confirmRemoval = message => window.confirm(message);
  return <form onSubmit={event => { event.preventDefault(); onSave(); }} aria-label="DHCP configuration editor">
    <fieldset disabled={busy} className="dhcp-fields-reset">
      <div className="dhcp-general">
        <Field spec={{ label: 'Firewall name', required: true, max: 63 }} value={draft.firewall} onChange={firewall => onChange({ ...draft, firewall })} />
        <label className="dhcp-field"><span>Gaia profile</span><select className="tool-input" value={draft.profile} onChange={event => onChange({ ...draft, profile: event.target.value })}><option>R81.10</option><option>R82.10</option></select></label>
      </div>
      <details className="dhcp-options"><summary>Global DHCP options</summary><div className="dhcp-fields-grid">{globalFields.map(spec => <Field key={spec.key} spec={spec} value={draft[spec.key]} onChange={value => onChange({ ...draft, [spec.key]: value })} />)}</div></details>
      <div className="dhcp-subnet-toolbar"><h3>Subnets <span className="tool-hint">{subnets.length}</span></h3><button type="button" className="tool-btn tool-btn-ghost" onClick={() => { setIndex(subnets.length); onChange({ ...draft, subnets: [...subnets, emptySubnet()] }); }}>Add subnet</button></div>
      {subnets.length === 0 ? <div className="tool-empty">Add a subnet, its dynamic pool and any reservations. You can save an incomplete draft.</div> : <>
        <label className="dhcp-field"><span>Selected subnet</span><select className="tool-input" value={selectedIndex} onChange={event => setIndex(Number(event.target.value))}>{subnets.map((subnet, i) => <option key={i} value={i}>{subnet.cidr || `New subnet ${i + 1}`}{subnet.active === false ? ' · inactive' : ''}</option>)}</select></label>
        <div className="dhcp-fields-grid">{subnetFields.map(spec => <Field key={`${selectedIndex}-${spec.key}`} spec={spec} value={selected[spec.key]} onChange={value => changeSubnet({ [spec.key]: value })} />)}</div>
        <div className="dhcp-checks"><label><input type="checkbox" checked={selected.active !== false} onChange={event => changeSubnet({ active: event.target.checked })} /> Active subnet</label>
          <label><input type="checkbox" checked={Boolean(selected.gaia_host_name_fallback)} onChange={event => changeSubnet({ gaia_host_name_fallback: event.target.checked })} /> Gaia host-name fallback</label></div>
        <div className="dhcp-subnet-toolbar"><h3>Dynamic pool</h3>{!selected.pools?.length && <button type="button" className="tool-btn tool-btn-ghost" onClick={() => changeSubnet({ pools: [{ start: '', end: '', active: true }] })}>Add pool</button>}</div>
        {selected.pools?.length > 0 ? <div className="dhcp-pool"><div className="dhcp-fields-grid">{['start', 'end'].map(key => <Field key={`${selectedIndex}-pool-${key}`} spec={{ key, label: key === 'start' ? 'Pool start IPv4' : 'Pool end IPv4', required: true, max: 15 }} value={selected.pools[0][key]} onChange={value => changeSubnet({ pools: [{ ...selected.pools[0], [key]: value }] })} />)}</div>
          <div className="dhcp-checks"><label><input type="checkbox" checked={selected.pools[0].active !== false} onChange={event => changeSubnet({ pools: [{ ...selected.pools[0], active: event.target.checked }] })} /> Active pool</label>
            <button type="button" className="tool-btn tool-btn-ghost" onClick={() => { if (confirmRemoval(`Remove the pool from ${selected.cidr}? Published versions remain unchanged.`)) changeSubnet({ pools: [] }); }}>Remove pool</button></div></div> : <p className="tool-hint">One active pool is required per active subnet before publishing.</p>}
        <div className="dhcp-subnet-toolbar"><h3>Reservations</h3><button type="button" className="tool-btn tool-btn-ghost" onClick={() => changeSubnet({ reservations: [...(selected.reservations || []), { id: '', mac: '', ip: '', active: true }] })}>Add reservation</button></div>
        <p className="tool-hint">Reserved addresses must be outside the dynamic pool. Host IDs and MAC addresses are unique across this configuration.</p>
        {reservations.slice(page * 25, (page + 1) * 25).map((row, visibleIndex) => { const rowIndex = page * 25 + visibleIndex; return <div className="dhcp-reservation" key={`${selectedIndex}-${rowIndex}`}>
          <div className="dhcp-reservation-fields">{[{ key: 'id', label: 'Host ID', max: 63 }, { key: 'mac', label: 'MAC address', max: 17 }, { key: 'ip', label: 'Reserved IPv4', max: 15 }].map(spec => <Field key={spec.key} spec={{ ...spec, required: true }} value={row[spec.key]} onChange={value => changeSubnet({ reservations: selected.reservations.map((item, i) => i === rowIndex ? { ...item, [spec.key]: value } : item) })} />)}</div>
          <div className="dhcp-checks"><label><input type="checkbox" checked={row.active !== false} onChange={event => changeSubnet({ reservations: selected.reservations.map((item, i) => i === rowIndex ? { ...item, active: event.target.checked } : item) })} /> Active reservation</label>
            <button type="button" className="tool-btn tool-btn-ghost" onClick={() => { if (confirmRemoval(`Remove reservation ${row.id || rowIndex + 1}? Published versions remain unchanged.`)) changeSubnet({ reservations: selected.reservations.filter((_, i) => i !== rowIndex) }); }}>Remove reservation</button></div>
        </div>; })}
        {reservations.length > 25 && <div className="dhcp-pagination"><span>{page * 25 + 1}–{Math.min((page + 1) * 25, reservations.length)} of {reservations.length} reservations</span><button type="button" className="tool-btn tool-btn-ghost" disabled={page === 0} onClick={() => setReservationPage(page - 1)}>Previous reservations</button><button type="button" className="tool-btn tool-btn-ghost" disabled={(page + 1) * 25 >= reservations.length} onClick={() => setReservationPage(page + 1)}>Next reservations</button></div>}
        <button type="button" className="tool-btn tool-btn-ghost dhcp-remove-subnet" onClick={() => { if (confirmRemoval(`Remove ${selected.cidr || 'this subnet'}, its pool and ${selected.reservations?.length || 0} reservations from the draft?`)) { onChange({ ...draft, subnets: subnets.filter((_, i) => i !== selectedIndex) }); setIndex(0); } }}>Remove subnet</button>
      </>}
    </fieldset>
    <div className="dhcp-editor-footer"><button type="submit" className="tool-btn tool-btn-primary" disabled={busy}>{busy ? 'Working…' : saved ? 'Save draft' : 'Create configuration'}</button><span className="tool-hint">Publishing creates a separate, immutable version.</span></div>
  </form>;
}
