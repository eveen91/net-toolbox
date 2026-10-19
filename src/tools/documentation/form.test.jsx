import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import DCForm from './DCForm.jsx';
import {emptyForm,SECTIONS,PAGES} from './fields.js';

it('opens a blank DC form without inventory dependencies and preserves saved values',()=>{
 const form=emptyForm('admin');
 expect(form.author).toBe('admin');
 expect(form.dcName).toBe('');
 expect(Object.keys(form)).toHaveLength(SECTIONS.flatMap(section=>section.fields).length+3);
 const html=renderToStaticMarkup(<DCForm record={{form:{...form,title:'DC <Warsaw>',dcName:'DC1',power:'A/B UPS'}}} onDirty={()=>{}} onBusy={()=>{}} onSave={()=>{}}/>);
 expect(html).toContain('DC &lt;Warsaw&gt;');
 const power=renderToStaticMarkup(<DCForm record={{form:{title:'DC',dcName:'DC1',power:'A/B UPS'}}} activeTab="power" onDirty={()=>{}} onBusy={()=>{}} onSave={()=>{}}/>);
 expect(power).toContain('A/B UPS');expect(power).not.toContain('undefined');
 expect(html).not.toContain('Find source');expect(html).not.toContain('Use inventory');
});

it('keeps every chapter in the same document with unique field IDs and only two mandatory fields',()=>{
 const fields=SECTIONS.flatMap(section=>section.fields);
 expect(PAGES).toHaveLength(11);
 expect(new Set(fields.map(field=>field.id)).size).toBe(fields.length);
 expect(fields.filter(field=>field.required).map(field=>field.id)).toEqual(['title','dcName']);
 expect(emptyForm('').powerDistribution).toBe('');
 expect(emptyForm('').address).toBe('');
});

it('previews all chapters safely without inventing missing content',async()=>{
 const {default:DocumentPreview}=await import('./DocumentPreview.jsx');
 const html=renderToStaticMarkup(<DocumentPreview form={{title:'DC <script>',dcName:'DC1',power:'A/B',notes:'<img src=x onerror=bad>',environment:'production'}}/>);
 expect(html).toContain('Production');expect(html).toContain('A/B');
 expect(html).toContain('Not recorded.');expect(html).toContain('Logical network');
 expect(html).not.toContain('<script>');expect(html).not.toContain('<img');
});

it('supports all four templates and keeps review-only readers from editing',async()=>{
 const {TEMPLATES,pagesFor,fieldValue}=await import('./fields.js');
 const {canDocument}=await import('./permissions.js');
 const {hasToolAccess}=await import('../registry.js');
 expect(Object.keys(TEMPLATES)).toEqual(['network','switch','firewall','runbook']);
 const form={...emptyForm(''),templateId:'firewall',templateNotes:{policy:'Managed by central policy server'}};
 const policy=pagesFor(form).find(page=>page.id==='policy').sections[0].fields[0];
 expect(fieldValue(form,policy)).toBe('Managed by central policy server');
 expect(canDocument({permissions:['documentation.read']},'write')).toBe(false);
 expect(hasToolAccess(['documentation.read'],'documentation')).toBe(true);
 const html=renderToStaticMarkup(<DCForm record={{form,status:'review',version:1}} user={{permissions:['documentation.read']}} onDirty={()=>{}} onBusy={()=>{}} onSave={()=>{}}/>);
 expect(html).not.toContain('Save all chapters');expect(html).not.toContain('Submit for review');expect(html).not.toContain('Publish reviewed version');
});
