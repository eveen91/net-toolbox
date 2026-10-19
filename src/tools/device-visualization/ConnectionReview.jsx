import React from 'react';
import {portDescription} from './logic.js';
export default function ConnectionReview({review,busy,onConfirm,onCancel}) {
  return <section className="sv-review" role="region" aria-label="Connection change review"><h4>Replace existing connection?</h4><p>The following ports are affected. Their labels, IP addresses and VLAN settings will be kept. Existing cables will be disconnected; matching reciprocal notes on displaced peers will be cleared. Custom notes on those peers will be retained.</p>
    <ul className="sv-connection-review">{review.ports.map(item=><li key={item.port.id}><strong>{item.deviceName} / {item.port.name}</strong><dl><dt>Current destination</dt><dd>{item.port.leadsTo||'Not set'}</dd><dt>Physical cable</dt><dd>{item.port.connectionId?`#${item.port.connectionId}`:'Not connected'}</dd><dt>Module / link</dt><dd>{portDescription(item.port)}</dd><dt>Label</dt><dd>{item.port.label||'Not set'}</dd><dt>IP address</dt><dd>{item.port.ipAddress||'Not set'}</dd><dt>VLAN</dt><dd>{item.port.portMode?`${item.port.portMode} · ${item.port.accessVlan||item.port.trunkVlans}${item.port.nativeVlan?` · Native ${item.port.nativeVlan}`:''}`:'Not configured'}</dd></dl></li>)}</ul>
    {review.connections.length>0&&<><h4>Current physical connections</h4><ul>{review.connections.map(link=><li key={link.id}>{link.source.name} / {link.source.portName} ↔ {link.target.name} / {link.target.portName}{link.label?` · ${link.label}`:''}</li>)}</ul></>}
    <p><strong>New destinations</strong><br/>{review.proposedSourceDestination}<br/>{review.proposedTargetDestination}</p>
    <button type="button" className="tool-btn tool-btn-primary" disabled={busy} onClick={onConfirm}>Confirm change and save</button><button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={onCancel}>Cancel replacement</button>
  </section>;
}
