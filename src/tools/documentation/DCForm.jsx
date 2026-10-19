import React,{useEffect,useState} from 'react';
import {TEMPLATES,pagesFor,emptyForm,fieldValue} from './fields.js';
import {canDocument} from './permissions.js';
import ChapterTabs from './ChapterTabs.jsx';
import ViewTabs from '../../components/ViewTabs.jsx';
import DocumentPreview from './DocumentPreview.jsx';
import DocumentVersions from './DocumentVersions.jsx';
import ScopeForm from './ScopeForm.jsx';
import SourceTables,{Provenance} from './SourceTables.jsx';
import DocumentWorkflow from './DocumentWorkflow.jsx';
const scopeKey=scope=>JSON.stringify({kind:scope?.kind||'none',id:scope?.id||null,dhcpVersionIds:scope?.dhcpVersionIds||[]});

export default function DCForm({record,author,user,onSave,onUpdated,onDirty,onBusy,locked=false,activeTab='general',onTabChange=()=>{},view='edit',onViewChange=()=>{}}){
 const [initial]=useState(()=>({...emptyForm(author),...record?.form}));
 const [form,setForm]=useState(initial),[busy,setBusy]=useState(false),[error,setError]=useState(''),[invalid,setInvalid]=useState('');
 const pages=pagesFor(form),page=pages.find(item=>item.id===activeTab)||pages[0];
 const editable=canDocument(user,'write')&&(!record||(record.status||'draft')==='draft');
 const dirty=JSON.stringify(form)!==JSON.stringify(initial);
 const snapshot=scopeKey(form.scopeSpec)===scopeKey(record?.form.scopeSpec)?record?.snapshot:null;
 useEffect(()=>onDirty(dirty),[dirty,onDirty]);
 useEffect(()=>{if(invalid&&view==='edit')document.getElementById(`dc-doc-input-${invalid}`)?.focus();},[invalid,view,activeTab]);
 const change=(field,value)=>setForm(current=>field.note?{...current,templateNotes:{...current.templateNotes,[field.id]:value}}:{...current,[field.id]:value});
 const save=async event=>{
  event.preventDefault();if(busy||locked||!editable)return;
  const missing=['title',...(form.templateId==='runbook'?[]:['dcName'])].find(key=>!form[key].trim());
  if(missing){setInvalid(missing);setError('Enter the document title and documented subject name in General information.');onViewChange('edit');onTabChange('general');return;}
  if(form.scopeSpec.kind!=='none'&&!form.scopeSpec.id){setError('Choose the DC, rack, device or network included in this document.');onViewChange('edit');onTabChange('general');return;}
  setInvalid('');setBusy(true);onBusy(true);setError('');
  try{await onSave(form);}catch(failure){setError(failure.message);}finally{setBusy(false);onBusy(false);}
 };
 return <form onSubmit={save} className="dc-doc-form" noValidate>
  <label className="dc-doc-type">Document type<select className="tool-input" aria-label="Document type" value={form.templateId} disabled={!!record||!editable||busy||locked} onChange={event=>{if(dirty&&!window.confirm('Change the document type and discard the entered draft content?'))return;setForm({...emptyForm(author),templateId:event.target.value});onTabChange('general');setError('');}}>{Object.entries(TEMPLATES).map(([id,template])=><option key={id} value={id}>{template.name}</option>)}</select></label>
  {record&&<DocumentWorkflow key={record.version} record={record} dirty={dirty} locked={busy||locked} onBusy={onBusy} onUpdated={onUpdated} user={user}/>}
  <fieldset className="dc-doc-view-switch" disabled={busy||locked}><ViewTabs label="Documentation views" value={view} onChange={onViewChange} items={[{id:'edit',label:'Edit chapters'},{id:'preview',label:'Preview document'},{id:'versions',label:'Versions & export'}]}/></fieldset>
  {view==='edit'&&<ChapterTabs pages={pages} value={page.id} onChange={onTabChange} disabled={busy||locked}/>}
  {view==='edit'&&<p className="tool-hint">Fields marked * are required to save. Review requirements are checked when submitting the saved draft.</p>}
  <fieldset disabled={busy||locked} className="dc-doc-fieldset">
   {view==='preview'?<div className="tool-panel"><DocumentPreview form={form} chapters={pages} snapshot={snapshot}/></div>:view==='versions'?<DocumentVersions record={record} dirty={dirty} locked={busy||locked} onBusy={onBusy} onUpdated={onUpdated} user={user}/>:<div role="tabpanel" id={`dc-doc-page-${page.id}`} aria-labelledby={`dc-doc-tab-${page.id}`} className="dc-doc-page" tabIndex={0}>
    <div className="dc-doc-page-heading"><h3>{page.label}</h3><p className="tool-hint">{page.description}</p></div>
    {page.id==='general'&&<ScopeForm form={form} snapshot={record?.snapshot} disabled={!editable} user={user} onChange={(scopeSpec,name)=>setForm(current=>({...current,scopeSpec,...(!current.dcName&&name?{dcName:name}:{})}))}/>}
    {page.sections.map((section,index)=><section className="tool-panel dc-doc-section" key={section.id} aria-labelledby={`dc-doc-${section.id}`}>
     <div className="dc-doc-section-heading"><span aria-hidden="true">{String(index+1).padStart(2,'0')}</span><div><h3 id={`dc-doc-${section.id}`}>{section.title}</h3>{section.description&&<p className="tool-hint">{section.description}</p>}</div></div>
     <div className="dc-doc-grid">{section.fields.map(field=><label key={field.id} className={field.multiline?'dc-doc-wide':''}><span>{field.label}{field.required?' *':field.requiredForReview?' (required for review)':''}</span>
      {field.options?<select className="tool-input" aria-label={field.label} disabled={!editable} value={fieldValue(form,field)} onChange={event=>change(field,event.target.value)}><option value="">Not specified</option>{field.options.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>:field.multiline?<textarea aria-label={field.label} className="tool-textarea" rows={3} maxLength={field.max} disabled={!editable} value={fieldValue(form,field)} onChange={event=>change(field,event.target.value)} aria-describedby={field.hint?`dc-doc-hint-${field.id}`:undefined}/>:<input id={`dc-doc-input-${field.id}`} aria-invalid={invalid===field.id?true:undefined} aria-label={field.label+(field.required?' *':'')} className="tool-input" type={field.type||'text'} required={field.required} disabled={!editable} maxLength={field.max} value={fieldValue(form,field)} onChange={event=>change(field,event.target.value)} aria-describedby={field.hint?`dc-doc-hint-${field.id}`:undefined}/>}
      {field.hint&&<small className="tool-hint" id={`dc-doc-hint-${field.id}`}>{field.hint}</small>}
     </label>)}</div>
    </section>)}
    <SourceTables snapshot={snapshot} chapter={page.id} templateId={form.templateId}/>
    {page.id==='general'&&<Provenance snapshot={snapshot}/>}
   </div>}
   <div className="tool-panel dc-doc-save"><div>{error&&<p role="alert" className="tool-error">{error}</p>}<span className="tool-hint">{dirty?'Unsaved changes across this document':record?'All changes saved':'New documentation'}</span></div>{editable&&<button type="submit" className="tool-btn tool-btn-primary" disabled={busy||(!!record&&!dirty)}>{busy?'Saving…':'Save all chapters'}</button>}</div>
  </fieldset>
 </form>;
}
