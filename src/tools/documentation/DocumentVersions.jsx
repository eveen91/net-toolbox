import React,{useEffect,useRef,useState} from 'react';
import DocumentPreview from './DocumentPreview.jsx';
import VersionComparison from './VersionComparison.jsx';
import DocumentHistory from './DocumentHistory.jsx';
import DocumentDiagrams from './DocumentDiagrams.jsx';
import ConfluencePreview from './ConfluencePreview.jsx';
import {canDocument} from './permissions.js';
import * as api from './api.js';

export default function DocumentVersions({record,dirty,locked,onBusy,onUpdated,user}) {
  const [page,setPage]=useState(null),[offset,setOffset]=useState(0),[reload,setReload]=useState(0);
  const [description,setDescription]=useState(''),[error,setError]=useState(''),[listError,setListError]=useState('');
  const [selected,setSelected]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const alive=useRef(true),selection=useRef(0);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;selection.current++;};},[]);
  useEffect(()=>{
    let active=true;setPage(null);setListError('');
    if(!record)return;
    api.listVersions(record.id,offset).then(result=>{if(active)setPage(result);}).catch(failure=>{if(active)setListError(failure.message);});
    return()=>{active=false;};
  },[record?.id,offset,reload]);
  const perform=async action=>{
    if(busy||locked)return;
    setBusy(true);onBusy(true);setError('');
    try{await action();}catch(failure){if(alive.current){setError(failure.message);setReload(value=>value+1);}}finally{if(alive.current){setBusy(false);onBusy(false);}}
  };
  const preview=number=>perform(async()=>{
    const ticket=++selection.current,result=await api.getVersion(record.id,number);
    if(alive.current&&ticket===selection.current)setSelected(result);
  });
  if(!record)return <div className="tool-panel"><h3>Document versions</h3><p>Save the document before creating a version or exporting it.</p></div>;
  const exists=!!page?.versionForCurrentDraft;
  return <section className="dc-doc-versions" aria-label="Document versions">
    {canDocument(user,'write')&&(record.status||'draft')==='draft'&&<div className="tool-panel"><h3>Save a draft version</h3><p className="tool-hint">A version freezes all saved chapters. Later edits to the draft do not change its preview or downloaded files.</p>
      <label className="dc-doc-version-note">Version note (optional)<input className="tool-input" maxLength={1000} value={description} disabled={busy||locked} onChange={event=>setDescription(event.target.value)}/></label>
      {dirty&&<p className="tool-hint">Save your changes before creating a version.</p>}
      {exists&&<p className="tool-hint">A version already exists for this saved draft. Save further changes to create another version.</p>}
      <button type="button" className="tool-btn tool-btn-primary" disabled={dirty||busy||locked||exists||!page} onClick={()=>perform(async()=>{
        const result=await api.createVersion(record.id,record.version,description);
        if(alive.current){setSelected(result);setDescription('');setOffset(0);setReload(value=>value+1);setNotice(`Version ${result.number} created.`);}
      })}>{busy?'Processing…':'Create version'}</button>
    </div>
    }
    {error&&<p role="alert" className="tool-error">{error}</p>}
    {notice&&<p role="status" className="dc-doc-notice">{notice}</p>}
    <div className="tool-panel"><h3>Saved versions</h3><p className="tool-hint">Markdown contains the full text and tables. ZIP adds offline PNG/SVG diagrams, linked references and paginated large tables. Preview a version to inspect its saved diagrams.</p>
      {listError?<p role="alert" className="tool-error">{listError} <button type="button" className="tool-btn tool-btn-ghost" onClick={()=>setReload(value=>value+1)}>Retry versions</button></p>:!page?<p role="status">Loading versions…</p>:<>
        {!page.items.length&&<p className="tool-hint">No versions yet. Create a version to download Markdown or a ZIP package.</p>}
        <ul className="dc-doc-version-list">{page.items.map(item=><li key={item.number}><div><strong>Version {item.number} · {item.kind||'saved'}</strong><span>{new Date(item.createdAt).toLocaleString()} · Draft revision {item.draftVersion}{item.createdBy?` · ${item.createdBy}`:''}</span>{item.description&&<p>{item.description}</p>}</div>
          <div className="dc-doc-version-actions"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>preview(item.number)}>Preview version {item.number}</button>
            <button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>perform(()=>api.downloadVersion(record.id,item.number,'md'))}>Download Markdown v{item.number}</button>
            <button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>perform(()=>api.downloadVersion(record.id,item.number,'zip'))}>Download ZIP v{item.number}</button></div></li>)}</ul>
        {page.total>20&&<div className="dc-doc-pager"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||!offset} onClick={()=>setOffset(value=>value-20)}>Previous versions</button><span>{offset+1}–{Math.min(offset+20,page.total)} of {page.total}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||offset+20>=page.total} onClick={()=>setOffset(value=>value+20)}>Next versions</button></div>}
      </>}
    </div>
    <VersionComparison record={record} locked={locked||busy} onBusy={onBusy}/>
    <DocumentHistory key={`${record.id}-${reload}`} id={record.id}/>
    {selected&&<div className="tool-panel">{canDocument(user,'write')&&(record.status||'draft')==='draft'&&<button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||dirty} onClick={()=>{if(window.confirm(`Restore version ${selected.number} as a new draft revision? The current saved draft will be replaced; saved versions remain unchanged.`))perform(async()=>onUpdated(await api.restoreVersion(record.id,selected.number,record.version)));}}>Restore version {selected.number} as draft</button>}<DocumentPreview form={selected.document.form} version={selected.number} createdAt={selected.createdAt} chapters={selected.document.chapters} snapshot={selected.document.snapshot} sourceMap={selected.document.sourceChapterMap}/>{canDocument(user,'publish')&&<ConfluencePreview key={`confluence-${record.id}-${selected.number}`} id={record.id} version={selected.number} kind={selected.kind} locked={locked||busy} onBusy={onBusy}/>}{!selected.document.snapshot?.diagramData&&!selected.document.assets?.length&&<p className="tool-hint">This version has no frozen diagram inputs. For infrastructure diagrams, refresh infrastructure in a draft and create a new version. Existing version downloads stay unchanged.</p>}<DocumentDiagrams key={`${record.id}-${selected.number}`} id={record.id} version={selected.number} assets={selected.document.assets}/></div>}
  </section>;
}
