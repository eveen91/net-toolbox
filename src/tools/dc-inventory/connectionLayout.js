export const UNIT=20,HEADER=66,RACK_WIDTH=270,GAP=150;
export const endpointText=end=>`${end.name} / ${end.portName}`;
export const locationText=end=>end.rackId?`${end.dataCenterName} / ${end.rackName} · U${end.rackPosition}`:'Unassigned to a rack';
export function connectionLayout(data) {
  const maxUnits=Math.max(1,...data.racks.map(r=>r.heightU));
  const racks=data.racks.map((r,index)=>({...r,x:24+index*(RACK_WIDTH+GAP),y:HEADER+(maxUnits-r.heightU)*UNIT}));
  const nodes=new Map();
  for(const rack of racks)for(const d of rack.devices)nodes.set(d.id,{...d,x:rack.x+36,y:rack.y+(rack.heightU-d.rackPosition-d.heightU+1)*UNIT,width:RACK_WIDTH-48,height:d.heightU*UNIT});
  const unassignedX=24+racks.length*(RACK_WIDTH+GAP);
  const unassigned=data.unassigned.map((d,index)=>({...d,x:unassignedX,y:HEADER+index*72,width:RACK_WIDTH-48,height:56}));
  for(const d of unassigned)nodes.set(d.id,d);
  const edges=data.items.map((link,index)=>{
    const a=nodes.get(link.source.id),b=nodes.get(link.target.id);
    if(!a||!b)return null;
    const ay=a.y+a.height/2,by=b.y+b.height/2;
    if(a.x===b.x) {
      const x=a.x+a.width,lane=x+28+(index%12)*7;
      return {...link,path:`M ${x} ${ay} C ${lane} ${ay}, ${lane} ${by}, ${x} ${by}`};
    }
    const forward=a.x<b.x,ax=a.x+(forward?a.width:0),bx=b.x+(forward?0:b.width),mid=(ax+bx)/2+(index%7-3)*12;
    return {...link,path:`M ${ax} ${ay} C ${mid} ${ay}, ${mid} ${by}, ${bx} ${by}`};
  }).filter(Boolean);
  return {racks,nodes:[...nodes.values()],unassigned,edges,width:Math.max(360,(unassigned.length?unassignedX+RACK_WIDTH:24+racks.length*(RACK_WIDTH+GAP)-GAP)+100),height:Math.max(HEADER+maxUnits*UNIT+40,HEADER+unassigned.length*72+40)};
}
