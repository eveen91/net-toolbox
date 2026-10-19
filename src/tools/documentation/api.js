import {apiFetch} from '../../apiFetch.js';
const ROOT = '/api/documentation/dc';
async function request(path='',method='GET',body) {
  const response = await apiFetch(ROOT+path,{method,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  if(!response.ok) {
    let detail;try {detail=(await response.json()).detail;}catch {}
    throw new Error(typeof detail==='string' ? detail : Array.isArray(detail) ? detail.map(item=>`${item.loc?.slice(1).join('.')}: ${item.msg}`).join('; ') : detail?.message||`Could not save or load documentation (${response.status}).`);
  }
  return response.json();
}
export const listForms = (offset,filters={}) => request(`?${new URLSearchParams(Object.entries({limit:20,offset,...filters}).filter(([,value])=>value!==''&&value!=null))}`);
export const getForm = id => request(`/${id}`);
export const saveForm = (form,record) => record ? request(`/${record.id}`,'PUT',{...form,expectedVersion:record.version}) : request('','POST',form);
export const listVersions = (id,offset=0) => request(`/${id}/versions?${new URLSearchParams({limit:20,offset})}`);
export const getVersion = (id,number) => request(`/${id}/versions/${number}`);
export const createVersion = (id,expectedVersion,description) => request(`/${id}/versions`,'POST',{expectedVersion,description});
export async function downloadVersion(id,number,format) {
  const response=await apiFetch(`${ROOT}/${id}/versions/${number}/export?${new URLSearchParams({format})}`);
  if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{}throw new Error(typeof detail==='string'?detail:`Export failed (${response.status}).`);}
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
  link.href=url;link.download=`dc-${id}-v${number}.${format}`;document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export const getOptions=filters=>request('/options?'+new URLSearchParams(Object.entries(filters).filter(([,value])=>value!==''&&value!=null)));
export const getCoverage=(scopeSpec,templateId)=>request('/coverage','POST',{scopeSpec,templateId});
export const transition=(id,expectedVersion,action,description='')=>request(`/${id}/transition`,'POST',{expectedVersion,action,description});
export const previewRefresh=(id,expectedVersion)=>request(`/${id}/refresh/preview`,'POST',{expectedVersion});
export const applyRefresh=(id,expectedVersion,snapshotDigest)=>request(`/${id}/refresh`,'POST',{expectedVersion,snapshotDigest});
export const compareVersions=(id,before,after)=>request(`/${id}/compare?`+new URLSearchParams({before,after}));
export const restoreVersion=(id,number,expectedVersion)=>request(`/${id}/versions/${number}/restore`,'POST',{expectedVersion});
export const getHistory=(id,offset=0)=>request(`/${id}/history?`+new URLSearchParams({limit:20,offset}));

export async function diagramBlob(id,number,filename,signal) {
  const response=await apiFetch(`${ROOT}/${id}/versions/${number}/assets/${encodeURIComponent(filename)}`,{signal});
  if(!response.ok)throw new Error(`Could not load diagram (${response.status}).`);
  return response.blob();
}

const CONFLUENCE='/confluence';
export const listConfluenceProfiles=()=>request(CONFLUENCE+'/profiles');
export const getConfluenceProfile=id=>request(`${CONFLUENCE}/profiles/${id}`);
export const saveConfluenceProfile=(form,record)=>request(CONFLUENCE+'/profiles'+(record?`/${record.id}`:''),record?'PUT':'POST',{...form,...(record?{expectedVersion:record.version}:{})});
export const checkConfluenceProfile=(id,expectedVersion)=>request(`${CONFLUENCE}/profiles/${id}/check`,'POST',{expectedVersion});
const previewPath=(id,number)=>`${CONFLUENCE}/documents/${id}/versions/${number}/previews`;
export const prepareConfluencePreview=(id,number,profileId,expectedVersion)=>request(previewPath(id,number),'POST',{profileId,expectedVersion});
export const listConfluencePreviews=(id,number,offset=0)=>request(previewPath(id,number)+`?limit=20&offset=${offset}`);
export const getConfluencePreview=(id,number,previewId)=>request(previewPath(id,number)+'/'+encodeURIComponent(previewId));

const jobsPath=(id,number)=>`${CONFLUENCE}/documents/${id}/versions/${number}/jobs`;
export const startConfluencePublication=(id,number,plan,decisions)=>request(jobsPath(id,number),'POST',{previewId:plan.id,expectedVersion:plan.profileVersion,audienceConfirmed:true,...decisions});
export const listConfluencePublications=(id,number,offset=0)=>request(jobsPath(id,number)+`?limit=20&offset=${offset}`);
export const getConfluencePublication=(id,number,jobId,offset=0)=>request(jobsPath(id,number)+'/'+jobId+`?limit=50&offset=${offset}`);
export const advanceConfluencePublication=(id,number,job)=>request(jobsPath(id,number)+'/'+job.id+'/advance','POST',{expectedRevision:job.revision});
export const controlConfluencePublication=(id,number,job,action)=>request(jobsPath(id,number)+'/'+job.id+'/control','POST',{expectedRevision:job.revision,action});
export const revalidateConfluencePublication=(id,number,job,expectedProfileVersion)=>request(jobsPath(id,number)+'/'+job.id+'/revalidate','POST',{expectedRevision:job.revision,expectedProfileVersion,audienceConfirmed:true});
export const resolveConfluencePublication=(id,number,job,values)=>request(jobsPath(id,number)+'/'+job.id+'/resolve','POST',{expectedRevision:job.revision,...values});
