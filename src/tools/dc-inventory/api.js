import {apiFetch} from '../../apiFetch.js';
async function request(path,method='GET',body,deviceAccess=false) {
  const root=deviceAccess?'/api/device-visualization/inventory':'/api/dc-inventory';
  const response=await apiFetch(root+path,{method,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{}const error=new Error(typeof detail==='string'?detail:Array.isArray(detail)?detail.map(item=>item.msg).join('; '):detail?.message||`Request failed (${response.status})`);error.detail=detail;error.status=response.status;throw error;}
  return response.json();
}
const query=filters=>'?'+new URLSearchParams(Object.entries(filters).filter(([,value])=>value!==null&&value!==undefined&&value!==''));
export const listDataCenters=(filters={},deviceAccess=false)=>request('/datacenters'+query(filters),'GET',undefined,deviceAccess);
export const listRacks=(filters={},deviceAccess=false)=>request('/racks'+query(filters),'GET',undefined,deviceAccess);
export const getRack=id=>request(`/racks/${id}`);
export const listDevices=filters=>request('/devices'+query(filters));
export const saveResource=(kind,data,id=null)=>request(`/${kind}${id?'/'+id:''}`,id?'PUT':'POST',data);
export const deleteResource=(kind,id,data)=>request(`/${kind}/${id}`,'DELETE',data);
export const placeDevice=(id,data)=>request(`/devices/${id}/placement`,'PUT',data);
export const listAudit=filters=>request('/audit'+query(filters));

export const createCablePanel=data=>request('/cable-panels','POST',data);
