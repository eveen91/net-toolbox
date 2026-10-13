import { expect,it } from 'vitest';
import { initialDraft,newCard,payload,removedPorts,validateDraft } from './logic.js';
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
