import React,{useState} from 'react';
import {useAccessibleDialog} from '../ipam/hooks/useAccessibleDialog.js';
import {placePortInIpam} from './api.js';

export default function IpamPlacementNotice({notice,onClose}) {
  const [result,setResult]=useState(notice.result),[busy,setBusy]=useState(false);
  const {dialogRef}=useAccessibleDialog(true,()=>{if(!busy)onClose();});
  const retry=async()=>{
    setBusy(true);
    try{setResult(await placePortInIpam(notice.deviceId,notice.portId,notice.version));}
    catch(error){setResult({status:'error',message:`Hardware was saved, but IPAM placement could not complete. ${error.message}`});}
    finally{setBusy(false);}
  };
  const placed=['created','existing'].includes(result.status);
  return <div className="tool-modal-overlay"><section ref={dialogRef} className="tool-modal" role="dialog" aria-modal="true" aria-labelledby="sv-ipam-placement-title" aria-describedby="sv-ipam-placement-message" aria-busy={busy}>
    <h3 id="sv-ipam-placement-title">{placed?'Hardware located in IPAM':'Hardware was not placed in IPAM'}</h3>
    <p>The device and its interface settings have been saved.</p>
    {result.ip&&<p><strong>{result.deviceName} / {result.portName}</strong><br/>{result.ip}</p>}
    <p id="sv-ipam-placement-message" role="status">{result.message}</p>
    <div className="sv-heading-actions">{!placed&&<button type="button" className="tool-btn tool-btn-ghost" disabled={busy} onClick={retry}>{busy?'Checking IPAM…':'Retry IPAM placement'}</button>}<button type="button" className="tool-btn tool-btn-primary" disabled={busy} onClick={onClose}>Close</button></div>
  </section></div>;
}
