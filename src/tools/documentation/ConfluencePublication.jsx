import React,{useEffect,useRef,useState} from 'react';
import * as api from './api.js';

export function publicationDecisions(plan,choices){
  return {keepRemoteKeys:plan.pages.filter(p=>choices[p.key]==='keep').map(p=>p.key),replaceReviewedKeys:plan.pages.filter(p=>choices[p.key]==='replace').map(p=>p.key)};
}
export function unresolvedPages(plan,choices){return plan.pages.filter(p=>p.action==='conflict'&&p.issues.some(i=>!i.startsWith('A parent page has a conflict'))&&!choices[p.key]);}
const finished=new Set(['succeeded','abandoned']);

export default function ConfluencePublication({id,version,plan,locked,onBusy}){
  const [ack,setAck]=useState(false),[choices,setChoices]=useState({}),[job,setJob]=useState(null),[history,setHistory]=useState(null);
  const [remoteId,setRemoteId]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[offset,setOffset]=useState(0),[reload,setReload]=useState(0),[historyOffset,setHistoryOffset]=useState(0);
  const alive=useRef(true),running=useRef(false),pause=useRef(false);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;running.current=false;pause.current=true;};},[]);
  useEffect(()=>{setAck(false);setChoices({});},[plan?.id]);
  useEffect(()=>{let active=true;api.listConfluencePublications(id,version,historyOffset).then(value=>{if(active)setHistory(value);}).catch(failure=>{if(active)setError(failure.message);});return()=>{active=false;};},[id,version,reload,historyOffset]);
  const task=async action=>{
    if(busy||locked)return;setBusy(true);onBusy(true);setError('');
    try{await action();}catch(failure){if(alive.current)setError(failure.message);}finally{if(alive.current){setBusy(false);onBusy(false);setReload(v=>v+1);}}
  };
  const execute=async initial=>{
    running.current=true;pause.current=false;let current=initial;
    try{
      while(alive.current&&running.current&&!pause.current&&!finished.has(current.status)){
        if(current.inFlight)break;
        if(current.retryAt>Date.now()/1000)break;
        current=await api.advanceConfluencePublication(id,version,current);
        if(alive.current){setJob(current);setOffset(0);}
        if(!['pending'].includes(current.status))break;
      }
      if(alive.current&&pause.current&&current.status==='pending'&&!current.inFlight){current=await api.controlConfluencePublication(id,version,current,'pause');setJob(current);}
    }catch(failure){
      if(alive.current){try{setJob(await api.getConfluencePublication(id,version,current.id));}catch{}throw failure;}
    }finally{running.current=false;}
  };
  const open=(jobId,nextOffset=0)=>task(async()=>{setJob(await api.getConfluencePublication(id,version,jobId,nextOffset));setOffset(nextOffset);});
  const missing=plan?unresolvedPages(plan,choices):[];
  return <section className="dc-doc-publication" aria-label="Confluence publication"><h4>Publish to Confluence</h4>
    {error&&<p role="alert" className="tool-error">{error}</p>}
    {plan&&<><p>Destination: <strong>{plan.profileName} · {plan.spaceKey}</strong>{plan.parentPageId?` · Parent ${plan.parentPageId}`:' · Space root'}. This will create or update the reviewed pages and upload their frozen PNG files.</p>
      <details><summary>Destination audience and inherited read restrictions</summary>{plan.audience?<><p>{plan.audience.note}</p><p>{plan.audience.spacePermissionsReported?'Space permissions reported by Confluence.':'The API did not expose space permissions; inspect them in Confluence before confirming.'}</p><pre className="dc-doc-diff">{JSON.stringify(plan.audience,null,2)}</pre></>:<p>Prepare a new preview to capture the audience.</p>}</details>
      {plan.pages.filter(p=>p.action==='conflict'||p.action==='keep').map(page=><div className="dc-doc-publication-decision" key={page.key}><strong>{page.label}</strong>{page.remoteId&&page.remoteHash?<label>Decision for {page.label}<select className="tool-input" aria-label={`Decision for ${page.label}`} disabled={busy||locked} value={choices[page.key]||''} onChange={e=>{setChoices(v=>({...v,[page.key]:e.target.value}));setAck(false);}}><option value="">{page.action==='keep'?'Keep remote (saved decision)':'Choose after reviewing the diff'}</option><option value="keep">Keep remote content and attachments</option>{!page.attachments.some(a=>a.action==='conflict')&&<option value="replace">Replace the reviewed remote content</option>}</select></label>:page.issues.some(i=>!i.startsWith('A parent page has a conflict'))?<p className="tool-error">This destination cannot be adopted or overwritten. Resolve the collision and prepare a fresh preview.</p>:<p className="tool-hint">Depends on the reviewed decision for its parent.</p>}</div>)}
      <label className="dc-doc-publish-ack"><input type="checkbox" checked={ack} disabled={busy||locked} onChange={e=>setAck(e.target.checked)}/> I reviewed the page changes and destination permissions, and the intended audience may read this document.</label>
      <button type="button" className="tool-btn tool-btn-primary" disabled={busy||locked||!ack||!plan.audienceHash||plan.profileChanged||missing.length>0||(job?.previewId===plan.id&&job.status==='succeeded')} onClick={()=>task(async()=>{
        const current=await api.startConfluencePublication(id,version,plan,publicationDecisions(plan,choices));if(alive.current){setJob(current);setOffset(0);setAck(false);}await execute(current);
      })}>{busy?'Publication in progress…':'Publish reviewed plan to Confluence'}</button>
    </>}
    {busy&&running.current&&<button type="button" className="tool-btn tool-btn-ghost" onClick={()=>{pause.current=true;}}>Pause after current operation</button>}
    {history&&history.items.length>0&&<details><summary>Publication history ({history.total})</summary><ul className="dc-doc-version-list">{history.items.map(item=><li key={item.id}><span>{new Date(item.createdAt).toLocaleString()} · {item.status}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>open(item.id)}>Open publication {new Date(item.createdAt).toLocaleString()}</button></li>)}</ul>{history.total>20&&<div className="dc-doc-pager"><button className="tool-btn tool-btn-ghost" type="button" disabled={busy||locked||!historyOffset} onClick={()=>setHistoryOffset(v=>v-20)}>Previous publications</button><span>{historyOffset+1}–{Math.min(historyOffset+20,history.total)} of {history.total}</span><button className="tool-btn tool-btn-ghost" type="button" disabled={busy||locked||historyOffset+20>=history.total} onClick={()=>setHistoryOffset(v=>v+20)}>Next publications</button></div>}</details>}
    {job&&<div className="dc-doc-publication-status" data-publication-id={job.id}><p role="status"><strong>Publication: {job.status}</strong> · {job.completed} / {job.total} operations confirmed</p>{job.partial&&<p className="tool-hint">This is a partial publication. Confirmed operations have already taken effect in Confluence.</p>}<p className="tool-hint">Confirmed remote changes are retained. Leaving this view stops sending further operations; reopen the publication to resume.</p>{job.inFlight&&<p className="tool-hint">An operation is in flight. If the backend was interrupted, wait until {new Date(job.leaseUntil*1000).toLocaleTimeString()} before reconciling it.</p>}{job.status==='uncertain'&&<p className="tool-error">The result is uncertain. Reconciliation only reads the remote operation markers; it never repeats an ambiguous write.</p>}{job.status==='conflict'&&<p className="tool-error">Remote changes were preserved. Abandon this job and review a fresh preview to choose the next action.</p>}
      {job.status==='uncertain'&&<details><summary>Resolve a result that reconciliation cannot identify</summary><p className="tool-hint">For a renamed created page, enter its remote page ID. Its operation markers must match. Reset a missing create/upload only after checking Confluence server logs and verifying that the original request was not applied.</p><label>Created remote page ID<input className="tool-input" inputMode="numeric" value={remoteId} onChange={e=>setRemoteId(e.target.value)} disabled={busy||locked}/></label><div className="dc-doc-version-actions"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||job.inFlight||!remoteId} onClick={()=>task(async()=>setJob(await api.resolveConfluencePublication(id,version,job,{remotePageId:remoteId})))}>Identify marked page</button><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||job.inFlight} onClick={()=>{if(window.confirm('Confirm that you checked the Confluence server logs and verified the original create/upload was NOT applied. Reset this operation to allow a new attempt?'))task(async()=>setJob(await api.resolveConfluencePublication(id,version,job,{notAppliedConfirmed:true})));}}>Confirm write was not applied</button></div></details>}
      <div className="dc-doc-version-actions"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked} onClick={()=>open(job.id,offset)}>Refresh publication status</button>
        {!finished.has(job.status)&&<button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||job.inFlight} onClick={()=>{if(window.confirm('Revalidate this publication using the current connection credentials and unchanged destination audience?'))task(async()=>{const profiles=await api.listConfluenceProfiles(),profile=profiles.items.find(p=>p.id===job.profileId);if(!profile)throw new Error('Connection not found.');setJob(await api.revalidateConfluencePublication(id,version,job,profile.version));});}}>Revalidate connection</button>}
        {!finished.has(job.status)&&job.status!=='conflict'&&<button type="button" className="tool-btn tool-btn-primary" disabled={busy||locked||job.inFlight||job.retryAt>Date.now()/1000} onClick={()=>task(()=>execute(job))}>{job.status==='uncertain'?'Reconcile publication':'Continue publication'}</button>}
        {!finished.has(job.status)&&<button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||job.inFlight||job.status==='uncertain'} onClick={()=>{if(window.confirm('Abandon this publication? Confirmed pages and attachments will remain in Confluence. Further changes require a fresh preview.'))task(async()=>setJob(await api.controlConfluencePublication(id,version,job,'abandon')));}}>Abandon publication</button>}
      </div><ul className="dc-doc-publication-steps">{job.steps.items.map(step=><li key={step.ordinal}><strong>{step.ordinal+1}. {step.title}</strong><span>{step.kind}{step.filename?` · ${step.filename}`:''} · {step.status}</span>{step.error_message&&<p className="tool-error">{step.error_message}</p>}{step.destinationUrl&&<a href={step.destinationUrl} target="_blank" rel="noreferrer">Open remote page</a>}</li>)}</ul>
      {job.total>50&&<div className="dc-doc-pager"><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||!offset} onClick={()=>open(job.id,offset-50)}>Previous operations</button><span>{offset+1}–{Math.min(offset+50,job.total)} of {job.total}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={busy||locked||offset+50>=job.total} onClick={()=>open(job.id,offset+50)}>Next operations</button></div>}
    </div>}
  </section>;
}
