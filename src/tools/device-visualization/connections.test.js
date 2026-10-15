import {expect,it} from 'vitest';
import {connectionPorts,hasDocumentation,isAppliance,vlanDescription,networkCardTitle} from './connections.js';
const ports=[
  {id:1,name:'Eth 1',family:'ethernet',ipAddress:'192.0.2.129/25',leadsTo:'Edge uplink'},
  {id:2,name:'Eth 2',family:'ethernet'},
  {id:3,name:'SFP 1',family:'sfp',portMode:'trunk',trunkVlans:'10,20-25',nativeVlan:10},
  {id:4,name:'MGMT',family:'ethernet',isManagement:true,ipAddress:'2001:db8::1/64'},
];
it('uses saved details without treating an unconfigured socket as a connection',()=>{
  expect(connectionPorts(ports).map(p=>p.id)).toEqual([4,1,3]);
  expect(connectionPorts(ports,'','all').map(p=>p.id)).toEqual([4,1,2,3]);
  expect(hasDocumentation(ports[1])).toBe(false);
  expect(ports.map(p=>p.id)).toEqual([1,2,3,4]);
});
it('finds IPs, destinations, trunk/native VLANs and management without inventing networks',()=>{
  expect(connectionPorts(ports,'192.0.2.129')).toEqual([ports[0]]);
  expect(connectionPorts(ports,'192.0.2.128')).toEqual([]);
  expect(connectionPorts(ports,'EDGE')).toEqual([ports[0]]);
  expect(connectionPorts(ports,'native 10')).toEqual([ports[2]]);
  expect(connectionPorts(ports,'2001:db8','management')).toEqual([ports[3]]);
  expect(connectionPorts(ports,'','management')).toEqual([ports[3]]);
  expect(vlanDescription(ports[2])).toBe('Trunk 10,20-25 · Native 10');
});
it('opens the appliance workspace only for routers and firewalls',()=>{
  expect(isAppliance({deviceType:'router'})).toBe(true);
  expect(isAppliance({deviceType:'firewall'})).toBe(true);
  expect(isAppliance({deviceType:'switch'})).toBe(false);
  expect(isAppliance(null)).toBe(false);
});
it('filters storage controllers independently and orders management within each controller',()=>{
  const arrayPorts=[{...ports[0],id:11,controller:'B'},{...ports[3],id:12,controller:'B'},{...ports[0],id:21,controller:'A'},{...ports[3],id:22,controller:'A'}];
  expect(connectionPorts(arrayPorts).map(p=>p.id)).toEqual([22,21,12,11]);
  expect(connectionPorts(arrayPorts,'','management','B').map(p=>p.id)).toEqual([12]);
  expect(connectionPorts(arrayPorts,'192.0.2.129','all','A').map(p=>p.id)).toEqual([21]);
  expect(isAppliance({deviceType:'storage'})).toBe(true);
});

it('groups server ports by saved NIC identity and searches card names',()=>{
  const cards=[{id:11,slotNumber:1,name:'Production'},{id:33,slotNumber:3,name:'Backup'}];
  const serverPorts=[{...ports[0],groupId:11,slotNumber:1,cardName:'Production'},{...ports[0],id:2,groupId:33,slotNumber:3,cardName:'Backup'},{...ports[3],groupId:50}];
  expect(connectionPorts(serverPorts,'','all','all','33').map(p=>p.id)).toEqual([2]);
  expect(connectionPorts(serverPorts,'backup').map(p=>p.id)).toEqual([2]);
  expect(connectionPorts(serverPorts,'','management','all','33')).toEqual([]);
  expect(networkCardTitle(serverPorts[1],cards)).toBe('NIC 3 · Backup');
  expect(networkCardTitle(serverPorts[2],cards)).toBe('Management');
  expect(isAppliance({deviceType:'server'})).toBe(true);
  expect(isAppliance({deviceType:'switch'})).toBe(false);
});
