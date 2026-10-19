import {describe,it,expect} from 'vitest';
import {diagrams} from '../../../server/documentation/diagram-layout.mjs';

const port=(id,number)=>({id,name:`Eth ${number}`,family:'ethernet',groupId:1,number,effectiveFamily:'ethernet',effectiveSpeedGbps:1});
const device={id:1,name:'Core',deviceType:'switch',rackId:2,rackName:'Rack A',dataCenterName:'DC',rackPosition:1,heightU:1,ports:[port(1,1),port(2,2)]};
const endpoint={...device,portId:1,portName:'Eth 1',effectiveFamily:'ethernet',effectiveSpeedGbps:1};
const peer={id:3,name:'External peer',deviceType:'switch',rackId:4,rackName:'Rack B',rackPosition:2,dataCenterName:'DC',heightU:1,portId:9,portName:'Eth 9',family:'ethernet',effectiveFamily:'ethernet',effectiveSpeedGbps:1};

describe('portable diagram layout using existing inventory geometry',()=>{
  it('keeps 1U names and unit metadata on the same distinct row, and spans tall racks without omissions',()=>{
    const pages=diagrams({devices:[device],racks:[{id:2,name:'Rack A',dataCenterName:'DC',heightU:42}]});
    const rackPages=pages.filter(p=>p.id.startsWith('rack-'));
    expect(rackPages).toHaveLength(2);
    expect(rackPages.flatMap(p=>p.items).filter(i=>i.text?.match(/^U\d+$/))).toHaveLength(42);
    const row=rackPages[1].items.find(i=>i.text==='Core');
    const metadata=rackPages[1].items.find(i=>i.text==='U1–U1 · 1U · switch');
    expect(metadata.x).toBeGreaterThan(row.x+row.width);
  });
  it('draws one orthogonal cable per detail and preserves out-of-scope endpoint markers',()=>{
    const data={devices:[device],connections:[{id:5,label:'Uplink',source:endpoint,target:peer}],racks:[]};
    const pages=diagrams(data),detail=pages.find(p=>p.id==='connection-5');
    expect(pages.some(p=>p.id==='connections-overview-1')).toBe(true);
    const cable=detail.items.find(item=>item.type==='line');
    expect(cable.points.every((p,i,all)=>!i||p.x===all[i-1].x||p.y===all[i-1].y)).toBe(true);
    expect(detail.items.some(i=>i.text?.includes('[outside document scope]'))).toBe(true);
    expect(diagrams(data)).toEqual(pages);
  });
  it('paginates ports and marks manual notes without drawing invented links',()=>{
    const ports=Array.from({length:33},(_,i)=>({...port(i+1,i+1),leadsTo:'Unverified peer'}));
    const pages=diagrams({devices:[{...device,ports}],racks:[]});
    expect(pages).toHaveLength(3);
    expect(pages.flatMap(p=>p.items).filter(i=>i.text?.startsWith('Unverified note:'))).toHaveLength(33);
    expect(pages.flatMap(p=>p.items).some(i=>i.type==='line')).toBe(false);
  });
  it('does not require local rendering for a manual document or guess logical links',()=>{
    expect(diagrams({})).toEqual([]);
    const pages=diagrams({networks:[{id:1,cidr:'10.0.0.0/24',members:[]}]});
    expect(pages[0].items.some(i=>i.type==='line')).toBe(false);
    expect(pages[0].items.some(i=>i.text?.includes('Relationships are not guessed.'))).toBe(true);
  });
});
