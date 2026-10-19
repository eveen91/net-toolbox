import {expect,it} from 'vitest';
import {connectionBundles,connectionLayout,UNIT,endpointText,locationText} from './connectionLayout.js';
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

it('anchors cables to the actual paired switch sockets, including separate uplinks',()=>{
 const a=device(1,1,1),b=device(2,1,4);
 const ports=Array.from({length:48},(_,i)=>({id:i+1,name:`Eth ${i+1}`,family:'ethernet',number:i+1,groupId:1,isManagement:false}));
 ports.push({id:100,name:'SFP 1',family:'sfp',number:1,groupId:2,isManagement:false});
 const graph={rackId:1,racks:[{id:1,heightU:12,devices:[a,b]}],unassigned:[],portLayouts:{1:{deviceType:'switch',ports},2:{deviceType:'switch',ports:[{id:200,name:'Eth 1',family:'ethernet',number:1,groupId:3}]}},items:[{id:1,source:{...a,portId:48},target:{...b,portId:200}}]};
 const layout=connectionLayout(graph),node=layout.nodes.find(n=>n.id===1),one=node.sockets.find(p=>p.id===1),two=node.sockets.find(p=>p.id===2),last=node.sockets.find(p=>p.id===48),uplink=node.sockets.find(p=>p.id===100);
 expect(one.cx).toBe(two.cx);expect(one.cy).toBeLessThan(two.cy);expect(uplink.cx).toBeGreaterThan(last.cx);
 expect(layout.edges[0].sourceAnchor).toEqual({x:last.cx,y:last.cy});
 expect(layout.edges[0].path).not.toMatch(/[CQAS]/);
 for(const edge of layout.edges)for(let i=1;i<edge.points.length;i++)expect(edge.points[i].x===edge.points[i-1].x||edge.points[i].y===edge.points[i-1].y).toBe(true);
});

it('routes past intermediate racks above their equipment and keeps nested local cables on separate tracks',()=>{
 const a=device(1,1,1),b=device(2,1,10),c=device(3,1,3),d=device(4,1,8),remote=device(5,3,6);
 const graph={rackId:1,racks:[{id:1,heightU:12,devices:[a,b,c,d]},{id:2,heightU:12,devices:[]},{id:3,heightU:12,devices:[remote]}],unassigned:[],items:[{id:1,source:a,target:b},{id:2,source:c,target:d},{id:3,source:a,target:remote}]};
 // Force both remote racks to remain in the graph and the most connected peer nearest the source.
 graph.items.push({id:4,source:a,target:device(6,2,4)},{id:5,source:b,target:device(6,2,4)});
 graph.racks[1].devices=[device(6,2,4)];
 const layout=connectionLayout(graph),outer=layout.edges.find(e=>e.id===1),inner=layout.edges.find(e=>e.id===2);
 expect(outer.points[1].x).toBeGreaterThan(inner.points[1].x);
 const far=layout.edges.find(e=>e.id===3),middle=layout.racks[1];
 expect(far.points.some(p=>p.y<middle.y)).toBe(true);
 for(let i=1;i<far.points.length;i++){
  const start=far.points[i-1],end=far.points[i];
  if(start.y===end.y&&Math.min(start.x,end.x)<middle.x&&Math.max(start.x,end.x)>middle.x+380)expect(start.y).toBeLessThan(middle.y);
 }
});

it('groups reverse-direction cables together without merging local or unassigned connections',()=>{
 const a=device(1,1,1),b=device(2,2,1),c=device(3,1,2),u=device(4,null,null);
 const items=[{id:1,source:a,target:b},{id:2,source:b,target:a},{id:3,source:a,target:c},{id:4,source:a,target:u}];
 const groups=connectionBundles(items);
 expect(groups).toHaveLength(3);
 expect(groups[0].items.map(link=>link.id)).toEqual([1,2]);
 expect(groups[1].label).toBe('Within Rack 1');
 expect(groups.flatMap(group=>group.items)).toHaveLength(4);
 expect(connectionBundles([])).toEqual([]);
});
