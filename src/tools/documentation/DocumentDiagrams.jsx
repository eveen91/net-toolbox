import React,{useEffect,useState} from 'react';
import {diagramBlob} from './api.js';

function Diagram({id,version,asset}) {
  const [url,setUrl]=useState(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();let active=true,objectUrl;
    setError('');setUrl(null);
    diagramBlob(id,version,asset.files.png.split('/').at(-1),controller.signal).then(blob=>{
      if(active){objectUrl=URL.createObjectURL(blob);setUrl(objectUrl);}
    }).catch(failure=>{if(active)setError(failure.message);});
    return()=>{active=false;controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[id,version,asset.files.png,retry]);
  return <figure className="dc-doc-diagram"><figcaption>{asset.title}</figcaption>
    {error?<p role="alert">{error} <button type="button" className="tool-btn tool-btn-ghost" onClick={()=>setRetry(value=>value+1)}>Retry diagram</button></p>:!url?<p role="status">Loading diagram…</p>:<a href={url} target="_blank" rel="noreferrer" aria-label={`Open full size: ${asset.title}`}><img src={url} alt={asset.title}/></a>}
  </figure>;
}

export default function DocumentDiagrams({id,version,assets=[]}) {
  const [open,setOpen]=useState(false),[offset,setOffset]=useState(0);
  if(!assets.length)return null;
  return <section className="dc-doc-diagrams" aria-label="Saved diagrams"><h3>Saved diagrams · {assets.length}</h3>
    <p className="tool-hint">Frozen with version {version}. Saved records, schematic layout, no live status. Open an image at full size to inspect ports. Complete labels and equivalent facts are in the document tables.</p>
    <button type="button" className="tool-btn tool-btn-ghost" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{open?'Hide diagrams':'Show diagrams'}</button>
    {open&&<><div className="dc-doc-pager"><button type="button" className="tool-btn tool-btn-ghost" disabled={!offset} onClick={()=>setOffset(value=>value-6)}>Previous diagrams</button><span>{offset+1}–{Math.min(offset+6,assets.length)} of {assets.length}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={offset+6>=assets.length} onClick={()=>setOffset(value=>value+6)}>Next diagrams</button></div>
      {assets.slice(offset,offset+6).map(asset=><Diagram key={asset.id} id={id} version={version} asset={asset}/>)}</>}
  </section>;
}
