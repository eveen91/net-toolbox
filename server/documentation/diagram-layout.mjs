// Standalone, network-free export adapter over the application's existing geometry.
import {rackRows,unitRange} from '../../src/tools/dc-inventory/rackLogic.js';
import {connectionLayout,panelSockets,connectionBundles,endpointText,locationText} from '../../src/tools/dc-inventory/connectionLayout.js';

export function diagrams(data) {
  const pages=[],devices=data.devices||[],links=data.connections||[];
  const rect=(x,y,w,h,fill='#eef2f6',stroke='#64748b')=>({type:'rect',x,y,w,h,fill,stroke});
  const text=(x,y,value,width=1000,size=16,color='#172538')=>({type:'text',x,y,text:String(value??'Not recorded'),width,size,color});
  const line=(points,color='#2563a6',width=2)=>({type:'line',points,color,width});
  const page=(id,title,chapter,height=500)=>{
    if(pages.length>=512)throw new Error('Diagram page limit exceeded');
    const p={id,title,chapter,width:1120,height,items:[text(24,20,title,1070,23),text(24,56,'Saved records · schematic · no live link status',1070,14,'#516175')],references:[]};
    pages.push(p);return p;
  };
  const reference=(p,type,id)=>p.references.push({type,id});
  for(const rack of data.racks||[]){
    const installed=devices.filter(d=>d.rackId===rack.id);
    const rows=rackRows(rack.heightU,installed);
    for(let offset=0;offset<rows.length;offset+=24){
      const units=rows.slice(offset,offset+24),top=units[0].unit,bottom=units.at(-1).unit;
      const p=page(`rack-${rack.id}-${offset/24+1}`,`${rack.dataCenterName} / ${rack.name} · U${bottom}–U${top}`,'physical',130+units.length*36);
      reference(p,'rack',rack.id);
      p.items.push(text(24,87,'Front view · U1 at bottom · only scoped equipment shown',1060,14));
      for(const [i,row] of units.entries()){
        const d=installed.find(d=>d.id===row.deviceId),y=116+i*36;
        p.items.push(text(24,y+8,`U${row.unit}`,60,14),rect(90,y,1000,36,d?'#e2edf8':'#fafbfc','#a0adbc'));
        if(!d)p.items.push(text(106,y+9,'No scoped equipment recorded',960,13,'#778293'));
      }
      for(const d of installed){
        const low=Math.max(bottom,d.rackPosition),high=Math.min(top,d.rackPosition+d.heightU-1);
        if(low>high)continue;
        const y=116+(top-high)*36,h=(high-low+1)*36;
        p.items.push(rect(90,y,1000,h,'#e2edf8'),text(106,y+9,d.name,620,15),text(742,y+10,`${unitRange(d)} · ${d.heightU}U · ${d.deviceType}`,332,13));
        reference(p,'device',d.id);
      }
    }
  }
  // Every overview row is a rack bundle. Cable detail lives in a separate asset,
  // keeping large parallel connections from obscuring each other.
  const bundles=connectionBundles(links);
  for(let offset=0;offset<bundles.length;offset+=10){
    const selected=bundles.slice(offset,offset+10),p=page(`connections-overview-${offset/10+1}`,'Physical connections · rack bundles','connections',140+selected.length*98);
    selected.forEach((bundle,i)=>{
      const y=100+i*98,[a,b]=bundle.ends;
      p.items.push(rect(24,y,410,64),rect(686,y,410,64),text(38,y+12,a.rackName||'Unassigned equipment',380),text(700,y+12,b.rackName||'Unassigned equipment',380),
        text(38,y+38,a.dataCenterName||'No DC recorded',380,13),text(700,y+38,b.dataCenterName||'No DC recorded',380,13),
        line([{x:434,y:y+32},{x:686,y:y+32}]),text(457,y+8,`${bundle.items.length} cable(s)`,210,14));
      for(const link of bundle.items)reference(p,'connection',link.id);
    });
  }
  for(const cable of links){
    const ends=[cable.source,cable.target];
    const portLayouts=Object.fromEntries(ends.map(end=>[end.id,{deviceType:end.deviceType,ports:devices.find(d=>d.id===end.id)?.ports||[
      {id:end.portId,name:end.portName,family:end.family,groupId:0,number:1,isManagement:false}]}]));
    const nodes=[...new Map(ends.map(end=>[end.id,end])).values()];
    const layout=connectionLayout({racks:[],unassigned:nodes,portLayouts,items:[cable]});
    const p=page(`connection-${cable.id}`,`Cable #${cable.id} · ${cable.label||'No label recorded'}`,'connections',560);
    reference(p,'connection',cable.id);
    const dy=20;
    for(const node of layout.nodes){
      p.items.push(rect(node.x,node.y+dy,node.width,node.height),text(node.x+8,node.y+dy+8,node.name,node.width-16,15));
      for(const socket of node.sockets)p.items.push(rect(socket.x,socket.y+dy,socket.width,socket.height,'#64748b','#64748b'));
    }
    for(const edge of layout.edges){
      p.items.push(line(edge.points.map(pt=>({x:pt.x,y:pt.y+dy})), '#2563a6',3));
      for(const anchor of [edge.sourceAnchor,edge.targetAnchor])p.items.push(rect(anchor.x-4,anchor.y+dy-4,8,8,'#1261b0','#1261b0'));
    }
    ends.forEach((end,i)=>{
      const outside=!devices.some(d=>d.id===end.id),y=350+i*70;
      p.items.push(text(24,y,`${i?'To':'From'}: ${endpointText(end)}${outside?' [outside document scope]':''}`,1070,16),
        text(24,y+26,`${locationText(end)} · ${end.effectiveFamily} · ${end.effectiveSpeedGbps} Gbps`,1070,14));
      if(!outside)reference(p,'device',end.id);
    });
    p.items.push(text(24,505,'Only explicit port pairs are drawn. Free-text destination notes are not verified connections.',1070,13));
    if(ends.some(end=>!devices.some(d=>d.id===end.id)))p.items.push(text(24,533,'An external panel shows its connected port only; its physical port position is not recorded in this scope.',1070,13));
  }
  for(const device of devices){
    const ports=device.ports||[];
    for(let offset=0;offset<ports.length;offset+=16){
      const selected=ports.slice(offset,offset+16),p=page(`device-${device.id}-ports-${offset/16+1}`,`${device.name} · ports ${offset+1}–${offset+selected.length} of ${ports.length}`,'equipment',270+selected.length*64);
      reference(p,'device',device.id);
      const node={x:24,y:93,width:1070,height:100};
      p.items.push(rect(node.x,node.y,node.width,node.height),text(38,106,`${device.deviceType} · ${device.rackName||'Unassigned'} · ${unitRange(device)}`,1030,14));
      for(const socket of panelSockets(node,{deviceType:device.deviceType,ports:selected}))p.items.push(rect(socket.x,socket.y,socket.width,socket.height,socket.connectionId?'#2563a6':'#a5b1bd'));
      p.items.push(text(24,211,'Blue socket = saved physical connection · Grey = no saved physical connection',1070,13));
      selected.forEach((port,i)=>{
        const y=247+i*64,peer=links.find(l=>[l.source.portId,l.target.portId].includes(port.id)),end=peer&&(peer.source.portId===port.id?peer.target:peer.source);
        p.items.push(rect(24,y-4,1070,64,i%2?'#f4f7fa':'#ffffff','#dde3eb'),text(36,y+3,port.name,360,15),
          text(415,y+3,`${port.effectiveFamily} / ${port.effectiveSpeedGbps}G${port.transceiver?' / '+port.transceiver:''}`,660,14),
          text(36,y+31,port.ipAddress||`VLAN: ${port.accessVlan??port.trunkVlans??'Not recorded'}`,360,13),
          text(415,y+31,end?`Cable #${peer.id}: ${endpointText(end)}`:port.leadsTo?`Unverified note: ${port.leadsTo}`:'No saved connection',660,13));
      });
    }
  }
  for(const network of data.networks||[]){
    // Membership is calculated from recorded interface IP/CIDR by the existing
    // source adapter. VLAN/zone adjacency is deliberately never inferred.
    const members=network.members||[];
    for(let offset=0;offset<Math.max(1,members.length);offset+=12){
      const selected=members.slice(offset,offset+12),p=page(`subnet-${network.id}-${offset/12+1}`,`${network.cidr} · recorded interface membership`,'logical',190+Math.max(1,selected.length)*74);
      reference(p,'subnet',network.id);
      p.items.push(text(24,93,`VLAN: ${network.vlan??'Not recorded'} · Membership is not a routing, zone or live reachability claim.`,1070,14));
      if(!selected.length)p.items.push(text(24,145,'No scoped interface IP is recorded inside this network. Relationships are not guessed.',1070));
      selected.forEach((member,i)=>{
        const y=135+i*74;
        p.items.push(rect(24,y,480,58),text(36,y+8,member.name,450,15),text(36,y+33,`${member.portName} · ${member.address}`,450,13),
          line([{x:504,y:y+29},{x:666,y:y+29}]),rect(666,y,430,58),text(684,y+20,network.cidr,390,17));
        reference(p,'device',member.deviceId);
      });
    }
  }
  return pages;
}

// Read bounded JSON through stdin; no file paths, shell expressions or network URLs.
if(process.argv[1]&&import.meta.url===new URL(process.argv[1],'file:').href){
  let input='';for await(const chunk of process.stdin)input+=chunk;
  process.stdout.write(JSON.stringify({nodeVersion:process.version,pages:diagrams(JSON.parse(input))}));
}
