import {createPortal} from 'react-dom';
import useUnsavedChanges from '../../components/useUnsavedChanges.js';
import React,{useState} from 'react';
import DeviceForm from '../device-visualization/DeviceForm.jsx';
import {useAccessibleDialog} from './hooks/useAccessibleDialog.js';
import {createHardwareFromAddress} from './api.js';

export default function CreateHardwareDialog({address:initialAddress,onCreated,onClose}) {
  const [address]=useState(initialAddress);
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false);
  useUnsavedChanges(dirty,busy);
  const close=()=>{if(!busy&&(!dirty||window.confirm('Discard the unsaved hardware configuration?')))onClose();};
  const {dialogRef}=useAccessibleDialog(true,close);
  return createPortal(<div className="tool-modal-overlay" data-ipam-hardware-dialog="true"><section ref={dialogRef} className="tool-modal ip-create-hardware" role="dialog" aria-modal="true" aria-labelledby="ip-create-hardware-title" aria-busy={busy}>
    <h3 id="ip-create-hardware-title">Add hardware for {address.address}</h3>
    <DeviceForm initialValues={{name:(address.hostname||`Device ${address.address}`).slice(0,100),description:(address.description||'').slice(0,500)}} ipamSource={address}
      onCreate={(device,ipPort)=>createHardwareFromAddress(address.id,device,address.updatedAt,ipPort)}
      onSaved={onCreated} onCancel={close} onDirty={setDirty} onBusy={setBusy} onReload={()=>{}}/>
  </section></div>,document.body);
}
