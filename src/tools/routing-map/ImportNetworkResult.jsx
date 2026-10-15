import React from 'react';

export default function ImportNetworkResult({ result }) {
  if (!result) return null;
  return <div className="rm-ipam-result">
    <p role="status">Added {result.summary.created} subnet{result.summary.created === 1 ? '' : 's'} to IPAM; skipped {result.summary.skipped} interface{result.summary.skipped === 1 ? '' : 's'}.</p>
    <a className="tool-btn tool-btn-ghost" href="#/ipam">Open IPAM</a>
    <details><summary>Import details</summary>
      <ul>{result.created.map(item => <li key={item.subnetId}><strong>{item.cidr}</strong> — created from {item.interfaces.join(', ')}</li>)}
        {result.skipped.map((item, index) => <li key={`${item.interface}-${index}`}><strong>{item.interface}</strong> · {item.ipAddress}{item.cidr ? ` → ${item.cidr}` : ''} — {item.message}</li>)}
      </ul>
    </details>
  </div>;
}
