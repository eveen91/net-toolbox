import {expect,it} from 'vitest';
import {connectionLayout,UNIT,endpointText,locationText} from './connectionLayout.js';
const device=(id,rackId,rackPosition,heightU=1)=>({id,rackId,rackPosition,heightU,name:`Device ${id}`,portName:'Eth 1',dataCenterName:'Warsaw',rackName:`Rack ${rackId}`});
it('aligns rack bottoms and reserves each complete U range',()=>{
 const a=device(1,1,1,2),b=device(2,2,10);
 const graph={rackId:1,racks:[{id:1,heightU:42,devices:[a]},{id:2,heightU:12,devices:[b]}],unassigned:[],items:[{id:7,source:a,target:b}]};
 const layout=connectionLayout(graph),[first,second]=layout.nodes;
 expect(first.height).toBe(2*UNIT);
 expect(layout.racks[0].y+42*UNIT).toBe(layout.racks[1].y+12*UNIT);
 expect(second.y).toBe(layout.racks[1].y+2*UNIT);
 expect(layout.edges).toHaveLength(1);
 expect(layout.edges[0].path).not.toMatch(/NaN|undefined/);
 expect(endpointText(a)).toBe('Device 1 / Eth 1');
 expect(locationText(a)).toContain('Warsaw / Rack 1');
});
it('draws local loops and unassigned equipment without inventing rack units',()=>{
 const a=device(1,1,1),b=device(2,1,4),loose=device(3,null,null,null);
 const layout=connectionLayout({rackId:1,racks:[{id:1,heightU:12,devices:[a,b]}],unassigned:[loose],items:[{id:1,source:a,target:b},{id:2,source:a,target:loose}]});
 expect(layout.edges).toHaveLength(2);expect(layout.unassigned[0].heightU).toBeNull();
 expect(locationText(loose)).toBe('Unassigned to a rack');
 expect(layout.nodes.every(d=>d.x+d.width<=layout.width&&d.y+d.height<=layout.height)).toBe(true);
});
it('separates parallel cables and handles empty racks',()=>{
 const a=device(1,1,1),b=device(2,2,1);
 const layout=connectionLayout({rackId:1,racks:[{id:1,heightU:2,devices:[a]},{id:2,heightU:2,devices:[b]}],unassigned:[],items:[{id:1,source:a,target:b},{id:2,source:a,target:b}]});
 expect(layout.edges[0].path).not.toBe(layout.edges[1].path);
 expect(connectionLayout({racks:[{heightU:42,devices:[]}],unassigned:[],items:[]}).nodes).toEqual([]);
});
