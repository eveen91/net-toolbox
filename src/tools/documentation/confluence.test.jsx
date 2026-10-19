import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import {profilePayload,ConnectionCheck} from './ConfluenceProfiles.jsx';
import ConfluencePreview,{previewFrame} from './ConfluencePreview.jsx';
import {canDocument} from './permissions.js';

it('preserves saved credentials when blank and normalizes optional connection inputs',()=>{
 const form={name:'Local',parentPageId:'',token:'',timeoutSeconds:'10'};
 expect(profilePayload(form)).toEqual({...form,parentPageId:null,token:null,timeoutSeconds:10});
 expect(profilePayload({...form,token:'new-token',parentPageId:'42'})).toMatchObject({token:'new-token',parentPageId:'42'});
});

it('keeps rendered content in a scriptless frame with network access blocked',()=>{
 const html=previewFrame('<p>Saved canonical content</p>');
 expect(html).toContain("default-src 'none'");expect(html).toContain("img-src 'none'");
 expect(html).toContain("form-action 'none'");expect(html).not.toContain('<script');
 expect(html).toContain('Saved canonical content');
});

it('distinguishes read capability checks from publication permissions and escapes remote labels',()=>{
 const html=renderToStaticMarkup(<ConnectionCheck result={{ok:true,profileVersion:1,checkedAt:'2026-10-19T12:00:00Z',serverVersion:'9.2.1',identity:'<script>remote</script>',spaceName:'Test',spaceKey:'TEST'}}/>);
 expect(html).toContain('&lt;script&gt;remote&lt;/script&gt;');expect(html).not.toContain('<script>');
 expect(html).toContain('Publication and upload permissions have not been tested.');
 const failure=renderToStaticMarkup(<ConnectionCheck result={{ok:false,message:'Authentication failed',checkedAt:'2026-10-19T12:00:00Z',profileVersion:1}}/>);
 expect(failure).toContain('role="alert"');expect(failure).toContain('Authentication failed');
});

it('requires local publication before preparing Confluence and separates connection management grants',()=>{
 const html=renderToStaticMarkup(<ConfluencePreview id={1} version={1} kind="saved" onBusy={()=>{}}/>);
 expect(html).toContain('Publish the reviewed document locally');expect(html).not.toContain('Prepare Confluence preview</button>');
 expect(canDocument({permissions:['documentation.read','documentation.publish']},'admin')).toBe(false);
 expect(canDocument({permissions:['documentation.read','documentation.admin']},'publish')).toBe(false);
 expect(canDocument({permissions:['documentation']},'admin')).toBe(true);
});

it('turns explicit publication choices into disjoint scoped decisions and blocks unresolved collisions',async()=>{
 const {publicationDecisions,unresolvedPages}=await import('./ConfluencePublication.jsx');
 const plan={pages:[{key:'root',action:'conflict',issues:['Remote content changed'],remoteId:'42'},
   {key:'child',action:'conflict',issues:['A parent page has a conflict; review it']},
   {key:'collision',action:'conflict',issues:['Unowned destination title'],remoteId:null}]};
 expect(unresolvedPages(plan,{}).map(p=>p.key)).toEqual(['root','collision']);
 expect(publicationDecisions(plan,{root:'keep',collision:'replace'})).toEqual({keepRemoteKeys:['root'],replaceReviewedKeys:['collision']});
 expect(unresolvedPages(plan,{root:'keep'}).map(p=>p.key)).toEqual(['collision']);
});
