import React,{useMemo,useEffect,useRef,useState} from 'react';
import {connectionLayout,endpointText,locationText,UNIT,RACK_WIDTH,connectionBundles} from './connectionLayout.js';
export default function ConnectionDiagram({data,selectedId,onSelect,scope=null,onScope=()=>{}}) {
  const layout=useMemo(()=>connectionLayout(data),[data]);
  const viewport=useRef(null);
  const [fit,setFit]=useState(1),[zoom,setZoom]=useState(null);
  useEffect(()=>{const measure=()=>{if(viewport.current)setFit(Math.min(1,(viewport.current.clientWidth-16)/layout.width,(viewport.current.clientHeight-16)/layout.height));};measure();const observer=new ResizeObserver(measure);if(viewport.current)observer.observe(viewport.current);return()=>observer.disconnect();},[layout.width,layout.height]);
  const scale=zoom??fit;
  const selected=data.items.find(link=>link.id===selectedId);
  const highlighted=new Set(selected?[selected.source.id,selected.target.id]:scope?.type==='device'?[scope.id]:[]);
  const selectedPorts=new Set(selected?[selected.source.portId,selected.target.portId]:[]);
  const connected=new Map();
  for(const link of data.items)for(const endpoint of [link.source,link.target])connected.set(endpoint.portId,link.id);
  const bundles=connectionBundles(data.items);
  const edges=layout.edges.filter(edge=>edge.id===selectedId);
  const activeBundle=bundle=>!scope||(scope.type==='bundle'?scope.id===bundle.key:bundle.items.some(link=>[link.source.id,link.target.id].includes(scope.id)));
  const organizer=end=>{
    const node=layout.nodes.find(node=>node.id===end.id);
    return node?{x:node.x+node.width+30,y:node.y+node.height/2}:null;
  };
  const selectKey=(event,id)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(id);}};
  return <><div className="di-bundle-picker" aria-label="Cable bundles on this page">{bundles.map(bundle=><button key={bundle.key} className="tool-btn tool-btn-ghost" aria-pressed={scope?.type==='bundle'&&scope.id===bundle.key} onClick={()=>onScope({type:'bundle',id:bundle.key})}>{bundle.label} <strong>{bundle.items.length}</strong></button>)}</div><div className="di-actions">{(scope||selectedId)&&<button className="tool-btn tool-btn-ghost" onClick={()=>{onScope(null);onSelect(null);}}>Show overview</button>}<span className="tool-hint">{selected?'Tracing one cable':scope?.type==='device'?'Device connections':scope?'Bundle connections':'Bundle overview'} · counts on this page</span><button className="tool-btn tool-btn-ghost" onClick={()=>setZoom(null)}>Fit racks</button><button className="tool-btn tool-btn-ghost" onClick={()=>setZoom(1)}>100%</button><button className="tool-btn tool-btn-ghost" aria-label="Zoom out connection diagram" onClick={()=>setZoom(Math.max(.1,scale/1.25))}>−</button><span className="tool-hint">{Math.round(scale*100)}%</span><button className="tool-btn tool-btn-ghost" aria-label="Zoom in connection diagram" onClick={()=>setZoom(Math.min(2,scale*1.25))}>+</button></div><div ref={viewport} className="di-cabling-scroll" role="region" aria-label="Rack connection diagram, scroll to see connected racks" tabIndex={0}>
    <svg className="di-cabling-svg" width={layout.width*scale} height={layout.height*scale} viewBox={`0 0 ${layout.width} ${layout.height}`} role="group" aria-label="Saved physical connections. Equivalent details are in the connection list below.">
      {layout.racks.map(r=><g key={r.id}><text x={r.x} y={22} className="di-svg-dc">{r.dataCenterName.slice(0,36)}<title>{r.dataCenterName}</title></text><text x={r.x} y={44} className="di-svg-title">{r.name.slice(0,30)}{r.id===data.rackId?' · selected':''}<title>{r.name}</title></text><rect x={r.x} y={r.y} width={RACK_WIDTH} height={r.heightU*UNIT} className="di-svg-rack"/>{Array.from({length:r.heightU},(_,i)=><g key={i}><text x={r.x+6} y={r.y+i*UNIT+20} className="di-svg-unit">{r.heightU-i}</text><line x1={r.x+32} x2={r.x+RACK_WIDTH-6} y1={r.y+(i+1)*UNIT} y2={r.y+(i+1)*UNIT} className="di-svg-rule"/></g>)}</g>)}
      {layout.unassigned.length>0&&<text x={layout.unassigned[0].x} y={44} className="di-svg-title">Unassigned equipment</text>}
      {layout.racks.map(r=><rect key={`organizer-${r.id}`} x={r.x+RACK_WIDTH+12} y={r.y} width={12} height={r.heightU*UNIT} rx={4} className="di-svg-organizer"/>)}
      {!selected&&layout.nodes.filter(node=>data.items.some(link=>[link.source.id,link.target.id].includes(node.id))).map(node=><line key={`stub-${node.id}`} x1={node.x+node.width} x2={node.x+node.width+30} y1={node.y+node.height/2} y2={node.y+node.height/2} className="di-bundle-line"/>)}
      {!selected&&bundles.filter(activeBundle).map((bundle,index)=>{
        const points=bundle.ends.map(organizer);if(points.some(point=>!point))return null;
        const [a,b]=points.map(point=>({...point,x:point.x+index*8})),local=bundle.ends[0].rackId===bundle.ends[1].rackId;
        const bus=62+index*12;
        const d=local?`M ${a.x} ${a.y} H ${a.x+24} V ${b.y} H ${b.x}`:`M ${a.x} ${a.y} V ${bus} H ${b.x} V ${b.y}`;
        return <g key={bundle.key} className="di-bundle"><path d={d} className="di-bundle-line"/><path d={d} className="di-cable-hit" role="button" tabIndex={0} aria-label={`${bundle.label}: ${bundle.items.length} connections on this page`} onClick={()=>onScope({type:'bundle',id:bundle.key})} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onScope({type:'bundle',id:bundle.key});}}}/></g>;
      })}
      {layout.nodes.map(node=><g key={node.id} className={highlighted.has(node.id)?'di-svg-device di-svg-device-selected':'di-svg-device'}><title>{node.name} · {node.heightU||'?'}U · {locationText(node)}</title><rect x={node.x} y={node.y+1} width={node.width} height={node.height-2} role="button" tabIndex={0} aria-label={`Show connections for ${node.name}`} onClick={()=>onScope({type:'device',id:node.id})} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onScope({type:'device',id:node.id});}}}/><text pointerEvents="none" x={node.x+7} y={node.y+11} className="di-svg-panel-name">{node.name.length>28?node.name.slice(0,27)+'…':node.name}</text>{node.height>48&&<text x={node.x+7} y={node.y+25} className="di-svg-unit">{node.heightU||'?'}U · {node.deviceType==='cable-management'?'Cable management':node.deviceType}</text>}</g>)}
      {edges.map(edge=><g key={edge.id} className={`di-cable ${selectedId===edge.id?'di-cable-selected':selectedId?'di-cable-dim':''}`}><path d={edge.path} className="di-cable-line"/><path d={edge.path} className="di-cable-hit" tabIndex={0} role="button" aria-pressed={selectedId===edge.id} aria-label={`Select connection: ${endpointText(edge.source)} to ${endpointText(edge.target)}`} onClick={()=>onSelect(edge.id)} onKeyDown={event=>selectKey(event,edge.id)}><title>{endpointText(edge.source)} ↔ {endpointText(edge.target)}</title></path></g>)}
      {layout.nodes.map(node=><g key={node.id}>{node.sockets.map(socket=>{
        const id=connected.get(socket.id),isSelected=selectedPorts.has(socket.id);
        return <rect key={socket.id} x={socket.x} y={socket.y} width={socket.width} height={socket.height} rx={.6} className={`di-svg-socket ${id?'di-svg-socket-connected':''} ${isSelected?'di-svg-socket-selected':''}`} role={id?'button':undefined} tabIndex={id?0:undefined} aria-pressed={id?isSelected:undefined} aria-label={`${node.name} / ${socket.name}${id?' · select cable':''}`} onClick={id?()=>onSelect(id):undefined} onKeyDown={id?event=>selectKey(event,id):undefined}><title>{node.name} / {socket.name}</title></rect>;
      })}{node.sockets.filter(socket=>selectedPorts.has(socket.id)).map(socket=><g key={`label-${socket.id}`}><circle cx={socket.cx} cy={socket.cy} r={3} className="di-svg-port-pin" pointerEvents="none"/><text x={node.x+node.width-7} y={node.y+11} textAnchor="end" className="di-svg-selected-port" pointerEvents="none">{socket.name.length>22?'…'+socket.name.slice(-21):socket.name}</text></g>)}</g>)}
    </svg>
  </div><p className="tool-hint">Bundles summarize connections on this page. Select a bundle or device to narrow the list, then select a port or cable to trace one connection. Port positions follow the saved panel layout; equipment and cable paths are schematic. Use 100% to inspect sockets.</p></>;
}
