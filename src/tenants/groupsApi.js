import { apiFetch } from '../apiFetch.js';
const BASE = import.meta.env.VITE_API_BASE_URL || '';
export async function groupRequest(path='',method='GET',body) {
  const response=await apiFetch(`${BASE}/api/admin/access-groups${path}`,{method,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(e=>e.msg).join('; '):'Could not update group access');
  return data;
}
export const listGroups=(query='',offset=0)=>groupRequest(`?${new URLSearchParams({query,offset,limit:25})}`);
export const listAccounts=(query='',offset=0)=>groupRequest(`/accounts?${new URLSearchParams({query,offset,limit:25})}`);
export const groupMembers=(id,offset=0)=>groupRequest(`/${id}/members?${new URLSearchParams({offset,limit:25})}`);
