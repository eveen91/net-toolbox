export const FAMILIES=['ethernet','sfp','qsfp'];
export const FAMILY_NAMES={ethernet:'Ethernet',sfp:'SFP',qsfp:'QSFP'};
export const SPEEDS={ethernet:[1,10],sfp:[10,25],qsfp:[40,100]};
export const LIMITS={ethernet:96,sfp:48,qsfp:16};
export const limitsForType=type=>type==='firewall'?{...LIMITS,sfp:32}:LIMITS;
export const VENDORS={checkpoint:'Check Point',fortigate:'FortiGate',generic:'Generic firewall'};
let temporaryCardKey = 0;
export function newCard(cards=[]) {
  let slot=1;while(cards.some(c=>c.slotNumber===slot))slot++;
  return {id:null,_key:`new-card-${++temporaryCardKey}`,slotNumber:slot,name:'',family:'ethernet',count:2,speedGbps:1};
}
export const PORT_NAMING={family:'Eth 1 / SFP 1 / QSFP 1','unit-slot-port':'1/1/1 · unit / slot / port','unit-zero-port':'1/0/1 · unit / 0 / port','unit-port':'1/1 · unit / port',port:'1, 2, 3 · continuous numbering'};
export function initialDraft(device) {
  if(device) {
    const result={deviceType:device.deviceType,vendor:device.vendor,name:device.name,model:device.model||'',description:device.description||''};
    if(device.deviceType==='switch')Object.assign(result,{portNaming:device.portNaming||'family',portUnit:device.portUnit??1,portSlot:device.portSlot??1});
    if(device.deviceType==='server') result.networkCards=device.networkCards.map(c=>({...c,name:c.name||'',_key:`card-${c.id}`}));
    else result.portGroups=device.portGroups.map(({family,count,speedGbps})=>({family,count,speedGbps}));
    return result;
  }
  return {deviceType:'switch',portNaming:'family',portUnit:1,portSlot:1,vendor:null,name:'',model:'',description:'',portGroups:FAMILIES.map(f=>({family:f,count:f==='ethernet'?24:0,speedGbps:SPEEDS[f][0]}))};
}
export function payload(draft,version) {
  const data={deviceType:draft.deviceType,vendor:draft.vendor,name:draft.name.trim(),model:draft.model.trim()||null,description:draft.description.trim()||null};
  if(draft.deviceType==='switch')Object.assign(data,{portNaming:draft.portNaming||'family',portUnit:draft.portUnit??1,portSlot:draft.portSlot??1});
  if(draft.deviceType==='server') data.networkCards=draft.networkCards.map(({_key,...card})=>({...card,name:card.name.trim()||null}));
  else data.portGroups=draft.portGroups;
  if(version!=null) data.expectedVersion=version;
  return data;
}
export function validateDraft(draft) {
  if(!draft.name.trim()||draft.name.trim().length>100)throw new Error('Device name must have 1–100 characters.');
  const groups=draft.deviceType==='server'?draft.networkCards:draft.portGroups;
  if(draft.deviceType==='server'&&(groups.length<1||groups.length>16))throw new Error('Use 1–16 network cards.');
  for(const g of groups) {
    const max=draft.deviceType==='server'?8:limitsForType(draft.deviceType)[g.family];
    if(!Number.isInteger(g.count)||g.count<(draft.deviceType==='server'?1:0)||g.count>max||!SPEEDS[g.family].includes(g.speedGbps))throw new Error('Check connector counts and speeds.');
  }
  const total=groups.reduce((n,g)=>n+g.count,0);
  if(total<1||total>128)throw new Error('Use 1–128 sockets in total.');
  return total;
}
export function removedPorts(device,draft) {
  if(!device)return [];
  return device.ports.filter(p=>{
    const group=draft.deviceType==='server'?draft.networkCards.find(c=>c.id===p.groupId):draft.portGroups.find(g=>g.family===p.family);
    return !group||group.family!==p.family||p.number>group.count;
  });
}
