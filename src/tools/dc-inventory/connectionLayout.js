export const UNIT=32,HEADER=76,RACK_WIDTH=380,GAP=220;
export const endpointText=end=>`${end.name} / ${end.portName}`;
export const locationText=end=>end.rackId?`${end.dataCenterName} / ${end.rackName} · U${end.rackPosition}`:'Unassigned to a rack';

// A compact front/rear panel, preserving port group order and switch odd/even pairs.
export function panelSockets(node,layout) {
  if(!layout?.ports?.length)return [];
  const groups=new Map();
  for(const port of layout.ports){if(!groups.has(port.groupId))groups.set(port.groupId,[]);groups.get(port.groupId).push(port);}
  const banks=[...groups.values()].sort((a,b)=>{
    const p=a[0],q=b[0];
    return String(p.controller||'').localeCompare(String(q.controller||''))||Number(p.isManagement)-Number(q.isManagement)||(p.slotNumber??0)-(q.slotNumber??0)||['ethernet','sfp','qsfp','sas'].indexOf(p.family)-['ethernet','sfp','qsfp','sas'].indexOf(q.family);
  }).map(ports=>{ports.sort((a,b)=>a.number-b.number);const paired=layout.deviceType==='switch'&&!ports[0].isManagement;const columns=paired?Math.ceil(ports.length/2):Math.min(8,ports.length);return {ports,paired,columns,rows:paired?2:Math.ceil(ports.length/columns)};});
  const available=node.width-14-(banks.length-1)*6;
  const totalColumns=banks.reduce((n,bank)=>n+bank.columns,0);
  let x=node.x+7;
  const sockets=[];
  for(const bank of banks){
    const width=available*bank.columns/totalColumns,cell=width/bank.columns;
    const band=Math.min(24,Math.max(10,node.height-16)),top=node.y+node.height-band-2,rowHeight=band/bank.rows;
    bank.ports.forEach((port,index)=>{
      const column=bank.paired?Math.floor(index/2):index%bank.columns,row=bank.paired?index%2:Math.floor(index/bank.columns);
      const w=Math.max(.8,Math.min(10,cell-1)),h=Math.max(.8,Math.min(8,rowHeight-1));
      sockets.push({...port,x:x+column*cell+(cell-w)/2,y:top+row*rowHeight+(rowHeight-h)/2,width:w,height:h,
        cx:x+(column+.5)*cell,cy:top+(row+.5)*rowHeight});
    });
    x+=width+6;
  }
  return sockets;
}

function segments(points){return points.slice(1).map((end,index)=>({a:points[index],b:end})).filter(s=>s.a.x!==s.b.x||s.a.y!==s.b.y);}
function path(points){return points.map((p,index)=>index===0?`M ${p.x} ${p.y}`:p.x===points[index-1].x?`V ${p.y}`:`H ${p.x}`).join(' ');}
function cost(points,existing){
  let score=0;
  for(const s of segments(points)){
    score+=(Math.abs(s.a.x-s.b.x)+Math.abs(s.a.y-s.b.y))*.0001;
    const horizontal=s.a.y===s.b.y;
    for(const t of existing){
      const otherHorizontal=t.a.y===t.b.y;
      if(horizontal===otherHorizontal){
        if((horizontal?s.a.y===t.a.y:s.a.x===t.a.x)){
          const overlap=Math.min(horizontal?Math.max(s.a.x,s.b.x):Math.max(s.a.y,s.b.y),horizontal?Math.max(t.a.x,t.b.x):Math.max(t.a.y,t.b.y))-Math.max(horizontal?Math.min(s.a.x,s.b.x):Math.min(s.a.y,s.b.y),horizontal?Math.min(t.a.x,t.b.x):Math.min(t.a.y,t.b.y));
          if(overlap>0)score+=overlap*4;
        }
      }else{
        const h=horizontal?s:t,v=horizontal?t:s;
        if(v.a.x>Math.min(h.a.x,h.b.x)&&v.a.x<Math.max(h.a.x,h.b.x)&&h.a.y>Math.min(v.a.y,v.b.y)&&h.a.y<Math.max(v.a.y,v.b.y))score+=200;
      }
    }
  }
  return score;
}

export function connectionLayout(data) {
  const links=data.items||[],maxUnits=Math.max(1,...data.racks.map(r=>r.heightU));
  // Most frequently connected peer racks stay nearest the selected rack.
  const weight=id=>links.reduce((n,l)=>n+Number(l.source.rackId===id||l.target.rackId===id),0);
  const ordered=[...data.racks].sort((a,b)=>Number(b.id===data.rackId)-Number(a.id===data.rackId)||weight(b.id)-weight(a.id)||a.id-b.id);
  const header=HEADER+links.length*8;
  const racks=ordered.map((r,index)=>({...r,index,x:24+index*(RACK_WIDTH+GAP),y:header+(maxUnits-r.heightU)*UNIT}));
  const nodes=new Map();
  for(const rack of racks)for(const d of rack.devices)nodes.set(d.id,{...d,column:rack.index,x:rack.x+36,y:rack.y+(rack.heightU-d.rackPosition-d.heightU+1)*UNIT,width:RACK_WIDTH-48,height:d.heightU*UNIT});
  const unassignedX=24+racks.length*(RACK_WIDTH+GAP);
  const unassigned=(data.unassigned||[]).map((d,index)=>({...d,column:racks.length,x:unassignedX+36,y:header+index*86,width:RACK_WIDTH-48,height:68}));
  for(const d of unassigned)nodes.set(d.id,d);
  for(const node of nodes.values())node.sockets=panelSockets(node,data.portLayouts?.[node.id]);
  const anchor=end=>{
    const n=nodes.get(end.id);if(!n)return null;
    const port=n.sockets.find(port=>port.id===end.portId);
    return {node:n,x:port?.cx??n.x+n.width,y:port?.cy??n.y+n.height/2,portId:end.portId};
  };
  const prepared=links.map(link=>({...link,a:anchor(link.source),b:anchor(link.target)})).filter(l=>l.a&&l.b)
    .sort((a,b)=>Math.abs(b.a.y-b.b.y)-Math.abs(a.a.y-a.b.y)||a.id-b.id);
  const existing=[],edges=[];
  // Candidate tracks are outside chassis, in cable corridors. Reuse a track only
  // when its vertical intervals do not overlap; crossing and overlap costs dominate length.
  const lanes=column=>Array.from({length:20},(_,i)=>24+column*(RACK_WIDTH+GAP)+RACK_WIDTH+18+i*9);
  for(const [index,link] of prepared.entries()){
    const left=link.a.node.column<=link.b.node.column?link.a:link.b,right=left===link.a?link.b:link.a;
    const same=left.node.column===right.node.column,adjacent=right.node.column-left.node.column===1;
    let best=null,bestCost=Infinity;
    if(same||adjacent){
      for(const lane of lanes(left.node.column).reverse()){
        const points=[{x:left.x,y:left.y},{x:lane,y:left.y},{x:lane,y:right.y},{x:right.x,y:right.y}];
        const score=cost(points,existing)+(lanes(left.node.column).at(-1)-lane)*.01;
        if(score<bestCost){bestCost=score;best=points;}
      }
      if(adjacent){
        // Detours separate parallel cables whose port rows share the same Y.
        for(let lane=0;lane<8;lane++)for(const sign of [-1,1]){
          const lx=24+left.node.column*(RACK_WIDTH+GAP)+RACK_WIDTH+18+lane*9;
          const rx=24+right.node.column*(RACK_WIDTH+GAP)-18-lane*6;
          const y=(left.y+right.y)/2+sign*(8+(index%5)*4);
          const points=[{x:left.x,y:left.y},{x:lx,y:left.y},{x:lx,y},{x:rx,y},{x:rx,y:right.y},{x:right.x,y:right.y}];
          const score=cost(points,existing);
          if(score<bestCost){bestCost=score;best=points;}
        }
      }
    }else{
      const bus=60+index*8;
      for(const lx of lanes(left.node.column).filter((_,i)=>i%2===0))for(const rx of lanes(right.node.column-1).filter((_,i)=>i%2===0)){
        const points=[{x:left.x,y:left.y},{x:lx,y:left.y},{x:lx,y:bus},{x:rx,y:bus},{x:rx,y:right.y},{x:right.x,y:right.y}];
        const score=cost(points,existing);
        if(score<bestCost){bestCost=score;best=points;}
      }
    }
    existing.push(...segments(best));
    edges.push({...link,path:path(best),points:best,sourceAnchor:{x:link.a.x,y:link.a.y},targetAnchor:{x:link.b.x,y:link.b.y}});
  }
  return {racks,nodes:[...nodes.values()],unassigned,edges,width:Math.max(480,24+(racks.length+(unassigned.length?1:0))*(RACK_WIDTH+GAP)),height:Math.max(header+maxUnits*UNIT+40,header+unassigned.length*86+40)};
}

// Counts always describe the loaded page, never the whole rack inventory.
export function connectionBundles(items) {
  const groups=new Map();
  for(const link of items){
    const ends=[link.source,link.target].sort((a,b)=>String(a.rackId??'unassigned').localeCompare(String(b.rackId??'unassigned')));
    const key=JSON.stringify(ends.map(end=>end.rackId??null));
    if(!groups.has(key))groups.set(key,{key,ends,items:[],label:ends[0].rackId===ends[1].rackId?`Within ${ends[0].rackName||'unassigned equipment'}`:`${ends[0].rackName||'Unassigned'} ↔ ${ends[1].rackName||'Unassigned'}`});
    groups.get(key).items.push(link);
  }
  return [...groups.values()];
}
