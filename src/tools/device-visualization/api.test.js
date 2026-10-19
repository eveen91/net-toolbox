import { afterEach,expect,it,vi } from 'vitest';
import { setTenantId } from '../../tenantContext.js';
import { listDevices,createDevice,previewDeviceUpdate,updateDevice,deleteDevice,updatePortAssignment,getDeviceAudit } from './api.js';
afterEach(()=>{setTenantId(null);vi.unstubAllGlobals();});
it('scopes list, preview, mutation and historical data to the active tenant',async()=>{
  const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({})});vi.stubGlobal('fetch',fetch);setTenantId('device-tenant');
  await listDevices({query:'A%',deviceType:'server',limit:20,offset:20});
  await createDevice({deviceType:'server'});await previewDeviceUpdate(1,{expectedVersion:4});await updateDevice(1,{expectedVersion:4,confirmPortDataRemoval:true});
  await updatePortAssignment(1,7,{label:null,leadsTo:'endpoint',expectedVersion:5});await deleteDevice(1,{expectedVersion:6,confirmDelete:true});await getDeviceAudit(1,{offset:20});
  for(const [,options] of fetch.mock.calls) {
    expect(options.headers.get('X-Tenant-ID')).toBe('device-tenant');expect(options.headers.get('X-CSRF-TOKEN')).toBe('fixed-csrf-token');expect(options.credentials).toBe('include');
  }
  expect(fetch.mock.calls[0][0]).toContain('query=A%25');expect(fetch.mock.calls[5][1].method).toBe('DELETE');
  expect(JSON.parse(fetch.mock.calls[4][1].body).expectedVersion).toBe(5);
});
it('preserves structured conflicts for review and reload flows',async()=>{
  const detail={code:'confirmation_required',message:'Review removed ports',removedAssignedPortCount:2};
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({detail})}));
  await expect(updateDevice(1,{})).rejects.toMatchObject({status:409,detail,message:'Review removed ports'});
});
it('registers a saved interface in IPAM with its current version and tenant',async()=>{
  const {placePortInIpam}=await import('./api.js');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({status:'created'})}));
  setTenantId('device-tenant');
  await placePortInIpam(3,9,7);
  const [url,options]=fetch.mock.calls[0];
  expect(url).toContain('/devices/3/ports/9/ipam-placement');
  expect(options.method).toBe('POST');expect(JSON.parse(options.body)).toEqual({expectedVersion:7});
  expect(options.headers.get('X-Tenant-ID')).toBe('device-tenant');
});
