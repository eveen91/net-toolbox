import { apiFetch } from '../../apiFetch.js';
const ROOT='/api/device-visualization/devices';
async function request(path='',method='GET',body) {
  const res=await apiFetch(ROOT+path,{method,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  if(!res.ok) {
    let detail=res.statusText;
    try { detail=(await res.json()).detail || detail; } catch {}
    const message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(e=>e.msg).join('; '):detail.message;
    const error=new Error(message || `Request failed (${res.status})`);
    error.status=res.status;error.detail=detail;throw error;
  }
  return res.json();
}
const idPath=id=>`/${encodeURIComponent(id)}`;
export function listDevices(filters={}) { const q=new URLSearchParams(Object.entries(filters).filter(([,v])=>v!==''&&v!=null));return request(`?${q}`); }
export const getDevice=id=>request(idPath(id));
export const createDevice=data=>request('','POST',data);
export const previewDeviceUpdate=(id,data)=>request(`${idPath(id)}/update-preview`,'POST',data);
export const updateDevice=(id,data)=>request(idPath(id),'PUT',data);
export const deleteDevice=(id,data)=>request(idPath(id),'DELETE',data);
export const updatePortAssignment=(id,portId,data)=>request(`${idPath(id)}/ports/${encodeURIComponent(portId)}`,'PUT',data);
export const getDeviceAudit=(id,options={})=>request(`${idPath(id)}/audit?${new URLSearchParams(options)}`);
export const placePortInIpam=(deviceId,portId,expectedVersion)=>request(`${idPath(deviceId)}/ports/${encodeURIComponent(portId)}/ipam-placement`,'POST',{expectedVersion});
