import {afterEach,expect,it,vi} from 'vitest';
import {setTenantId} from '../../tenantContext.js';
import {createHardwareFromAddress} from './api.js';
afterEach(()=>{setTenantId(null);vi.unstubAllGlobals();});
it('creates hardware against the selected address version and active tenant',async()=>{
  setTenantId('tenant-create');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({id:19})}));
  const device={name:'Router',deviceType:'router',rackId:4,rackPosition:7};
  expect(await createHardwareFromAddress(5,device,'version-time','data')).toEqual({id:19});
  const [url,options]=fetch.mock.calls[0];
  expect(url).toBe('/api/ipam/addresses/5/hardware');
  expect(options.method).toBe('POST');
  expect(options.headers.get('X-Tenant-ID')).toBe('tenant-create');
  expect(options.headers.get('X-CSRF-TOKEN')).toBe('fixed-csrf-token');
  expect(options.credentials).toBe('include');
  expect(JSON.parse(options.body)).toEqual({device,expectedUpdatedAt:'version-time',ipPort:'data'});
});
it('shows the source-address conflict message so a failed draft can be reviewed',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({detail:{code:'stale_address',message:'Reload IPAM address details'}})}));
  await expect(createHardwareFromAddress(5,{},'old')).rejects.toThrow('Reload IPAM address details');
});
