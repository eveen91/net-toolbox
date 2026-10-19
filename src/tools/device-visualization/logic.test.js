import { expect,it } from 'vitest';
import { initialDraft,newCard,payload,removedPorts,validateDraft,compatiblePorts } from './logic.js';
it('adds a card in the free middle slot without changing existing identities',()=>{
  const cards=[{id:11,slotNumber:1},{id:13,slotNumber:3}];
  const added=newCard(cards);
  expect(added.slotNumber).toBe(2);expect(added.id).toBeNull();expect(added.count).toBe(2);
  expect(cards.map(c=>c.id)).toEqual([11,13]);
});
it('detects deleted and replaced sockets by card ID rather than slot/index',()=>{
  const device={ports:[{id:1,groupId:11,family:'ethernet',number:1},{id:2,groupId:13,family:'sfp',number:2}]};
  expect(removedPorts(device,{deviceType:'server',networkCards:[{id:13,slotNumber:3,family:'sfp',count:2}]}).map(p=>p.id)).toEqual([1]);
  expect(removedPorts(device,{deviceType:'server',networkCards:[{id:null,slotNumber:1,family:'ethernet',count:2}]}).map(p=>p.id)).toEqual([1,2]);
  expect(removedPorts(device,{deviceType:'server',networkCards:[{id:11,family:'sfp',count:2},{id:13,family:'sfp',count:1}]}).map(p=>p.id)).toEqual([1,2]);
});
it('keeps card IDs in payload but strips transient React keys',()=>{
  const draft={deviceType:'server',vendor:null,name:' Server ',model:' ',description:' ',networkCards:[{id:11,_key:'local',slotNumber:1,name:' LAN ',family:'ethernet',count:4,speedGbps:1}]};
  expect(payload(draft,7)).toEqual({deviceType:'server',vendor:null,name:'Server',model:null,description:null,expectedVersion:7,networkCards:[{id:11,slotNumber:1,name:'LAN',family:'ethernet',count:4,speedGbps:1}]});
});
it('validates per-card counts and total sockets',()=>{
  const draft={...initialDraft(),name:'valid'};
  expect(validateDraft(draft)).toBe(24);
  expect(()=>validateDraft({...draft,portGroups:draft.portGroups.map(g=>({...g,count:0}))})).toThrow('1–128');
  const cards=Array.from({length:16},(_,i)=>({...newCard(),slotNumber:i+1,count:8}));
  expect(validateDraft({...draft,deviceType:'server',networkCards:cards})).toBe(128);
  expect(()=>validateDraft({...draft,deviceType:'server',networkCards:[{...cards[0],count:9}]})).toThrow('counts');
});
it('accepts 48 SFP plus 8 QSFP for a switch and retains the firewall limit',()=>{
  const draft={...initialDraft(),name:'SFP switch',portGroups:[{family:'ethernet',count:0,speedGbps:1},{family:'sfp',count:48,speedGbps:25},{family:'qsfp',count:8,speedGbps:100}]};
  expect(validateDraft(draft)).toBe(56);
  expect(()=>validateDraft({...draft,deviceType:'firewall'})).toThrow('counts');
  expect(()=>validateDraft({...draft,portGroups:draft.portGroups.map(g=>g.family==='sfp'?{...g,count:49}:g)})).toThrow('counts');
});
it('round-trips switch naming parameters in configuration payloads',()=>{
  const draft={...initialDraft(),name:'Switch',portNaming:'unit-slot-port',portUnit:2,portSlot:3};
  expect(payload(draft,4)).toMatchObject({portNaming:'unit-slot-port',portUnit:2,portSlot:3,expectedVersion:4});
});
it('round-trips management port and includes its removal in the review',()=>{
  const device={...initialDraft(),managementPort:true,ports:[{id:100,isManagement:true,label:'OOB'}]};
  const draft=initialDraft(device);
  expect(payload(draft).managementPort).toBe(true);
  expect(removedPorts(device,draft)).toEqual([]);
  expect(removedPorts(device,{...draft,managementPort:false}).map(p=>p.id)).toEqual([100]);
});
it('keeps independent storage slots and card ownership through draft and removal review',()=>{
  const cards=['A','B'].map(controller=>({...newCard(),controller,slotNumber:1,id:controller==='A'?11:21}));
  const device={deviceType:'storage',vendor:null,name:'Array',model:null,description:null,managementPort:true,networkCards:cards,ports:[{id:101,groupId:11,family:'ethernet',number:1,controller:'A'},{id:201,groupId:21,family:'ethernet',number:1,controller:'B'}]};
  const draft=initialDraft(device);
  expect(validateDraft(draft)).toBe(4);
  expect(payload(draft).networkCards.map(c=>[c.controller,c.slotNumber,c.id])).toEqual([['A',1,11],['B',1,21]]);
  expect(removedPorts(device,{...draft,networkCards:draft.networkCards.filter(c=>c.controller==='B')}).map(p=>p.id)).toEqual([101]);
  expect(()=>validateDraft({...draft,networkCards:[draft.networkCards[0]]})).toThrow('controllers A and B');
});
it('accepts passive 1U cable panels without sockets and prevents invalid heights',()=>{
  const draft={...initialDraft(),deviceType:'cable-management',name:'Cable panel',heightU:1,managementPort:false,portGroups:[]};
  expect(validateDraft(draft)).toBe(0);
  expect(payload(draft).portGroups).toEqual([]);
  expect(()=>validateDraft({...draft,heightU:2})).toThrow('1U');
  expect(()=>validateDraft({...draft,managementPort:true})).toThrow('no ports');
});

it('offers only the same connector family and configured speed, retaining occupied and management ports',()=>{
  const source={family:'ethernet',speedGbps:1};
  const ports=[{id:1,family:'ethernet',speedGbps:1},{id:2,family:'ethernet',speedGbps:10},
    {id:3,family:'sfp',speedGbps:1},{id:4,family:'ethernet',speedGbps:1,connectionId:7},
    {id:5,family:'ethernet',speedGbps:1,isManagement:true}];
  expect(compatiblePorts(source,ports).map(p=>p.id)).toEqual([1,4,5]);
  expect(compatiblePorts({family:'qsfp',speedGbps:100},ports)).toEqual([]);
  expect(compatiblePorts(undefined,ports)).toEqual([]);
  expect(compatiblePorts({family:'sfp',speedGbps:25},[{id:6,family:'sfp',speedGbps:10},{id:7,family:'sfp',speedGbps:25}]).map(p=>p.id)).toEqual([7]);
});
it('matches installed SFP modules by effective medium and speed, including RJ45 adapters',()=>{
  const cage={family:'sfp',speedGbps:10};
  const candidates=[{id:1,family:'ethernet',speedGbps:1},{id:2,family:'sfp',speedGbps:25},
    {id:3,...cage,transceiver:'sfp-1g'},{id:4,...cage,transceiver:'rj45-1g'},
    {id:5,...cage,transceiver:'sfp28-25g'},{id:6,...cage}];
  expect(compatiblePorts({...cage,transceiver:'rj45-1g'},candidates).map(p=>p.id)).toEqual([1,4]);
  expect(compatiblePorts({...cage,transceiver:'sfp-1g'},candidates).map(p=>p.id)).toEqual([3]);
  expect(compatiblePorts({...cage,transceiver:'sfp28-25g'},candidates).map(p=>p.id)).toEqual([2,5]);
  expect(compatiblePorts(cage,candidates).map(p=>p.id)).toEqual([6]);
});
