import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
vi.mock('../apiFetch.js',()=>({apiFetch:vi.fn()}));
import {apiFetch} from '../apiFetch.js';
import {groupRequest,listGroups,groupMembers,listAccounts} from './groupsApi.js';
beforeEach(()=>apiFetch.mockReset());
afterEach(()=>vi.restoreAllMocks());
describe('group access API',()=>{
 it('uses authenticated API requests and preserves group names and DNs in JSON',async()=>{
  apiFetch.mockResolvedValue({ok:true,json:async()=>({id:3})});
  const body={name:'R&D',source:'ad',groupDn:'CN=R&D,DC=example,DC=com'};
  expect(await groupRequest('','POST',body)).toEqual({id:3});
  expect(apiFetch).toHaveBeenCalledWith('/api/admin/access-groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 });
 it('pages and encodes search without exposing unrelated records',async()=>{
  apiFetch.mockResolvedValue({ok:true,json:async()=>({items:[],total:0})});
  await listGroups('A&B',25);await groupMembers(7,50);await listAccounts('a b',75);
  expect(apiFetch.mock.calls.map(call=>call[0])).toEqual(['/api/admin/access-groups?query=A%26B&offset=25&limit=25','/api/admin/access-groups/7/members?offset=50&limit=25','/api/admin/access-groups/accounts?query=a+b&offset=75&limit=25']);
 });
 it('shows server denial and validation errors instead of success',async()=>{
  apiFetch.mockResolvedValueOnce({ok:false,json:async()=>({detail:'Platform administrator required'})});
  await expect(groupRequest('/1','DELETE')).rejects.toThrow('Platform administrator required');
  apiFetch.mockResolvedValueOnce({ok:false,json:async()=>({detail:[{msg:'Group name required'}]})});
  await expect(groupRequest('','POST',{})).rejects.toThrow('Group name required');
 });
});
