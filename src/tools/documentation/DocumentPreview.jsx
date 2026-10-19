import React from 'react';
import {PAGES,fieldValue,sourcePage} from './fields.js';
import SourceTables,{Provenance} from './SourceTables.jsx';

export default function DocumentPreview({form,version,createdAt,chapters=PAGES,snapshot,sourceMap}) {
  return <article className="dc-doc-preview" aria-label="Document preview">
    <header><h3>{form.title||'Untitled documentation'}</h3><p>{form.dcName||'Subject not recorded'}{version?` · Version ${version}`:''}{createdAt?` · ${new Date(createdAt).toLocaleString()}`:''}</p></header>
    {chapters.map(page=>{
      const sections=page.sections.map(section=>({...section,fields:section.fields.filter(field=>String(fieldValue(form,field)).trim())})).filter(section=>section.fields.length);
      const hasData=(snapshot?.tables||[]).some(table=>sourcePage(table,form.templateId,sourceMap)===page.id&&table.rows.length);
      return <section key={page.id}><h3>{page.label}</h3>{!sections.length&&!hasData&&<p className="tool-hint">Not recorded.</p>}{sections.map(section=><div key={section.id}><h4>{section.title}</h4><dl>{section.fields.map(field=><div key={field.id}><dt>{field.label}</dt><dd>{field.options?new Map(field.options).get(fieldValue(form,field))||fieldValue(form,field):fieldValue(form,field)}</dd></div>)}</dl></div>)}<SourceTables snapshot={snapshot} chapter={page.id} templateId={form.templateId} sourceMap={sourceMap}/></section>;
    })}
    <Provenance snapshot={snapshot}/>
  </article>;
}
