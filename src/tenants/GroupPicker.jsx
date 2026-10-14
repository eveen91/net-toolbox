import React, {useEffect,useState} from 'react';
import {listGroups,listAccounts} from './groupsApi.js';
export default function GroupPicker({kind='groups',value,onChange,disabled=false,label='Group'}){
 const [query,setQuery]=useState(''),[offset,setOffset]=useState(0),[page,setPage]=useState({items:[],total:0}),[error,setError]=useState(''),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{let current=true;setLoading(true);const timer=setTimeout(()=>{(kind==='groups'?listGroups:listAccounts)(query,offset).then(data=>{if(current){setPage(data);setError('')}}).catch(e=>{if(current)setError(e.message)}).finally(()=>{if(current)setLoading(false)});},query?250:0);return()=>{current=false;clearTimeout(timer)};},[kind,query,offset,retry]);
 return <div className="nt-access-picker"><label>Find {kind==='groups'?'group':'account'}<input className="tool-input" type="search" value={query} disabled={disabled} maxLength={120} onChange={e=>{setQuery(e.target.value);setOffset(0);onChange('')}} /></label>
 <label>{label}<select aria-label={label} className="tool-input" required value={value} disabled={disabled||loading} onChange={e=>onChange(e.target.value)}><option value="">{loading?'Loading…':`Select ${label.toLowerCase()}`}</option>{page.items.map(item=><option key={item.id} value={item.id}>{item.name||item.username} ({item.source||item.authSource})</option>)}</select></label>
 {error&&<p role="alert" className="tool-error">{error}<button type="button" className="tool-btn tool-btn-ghost" disabled={disabled} onClick={()=>setRetry(v=>v+1)}>Retry choices</button></p>}
 {page.total>25&&<div className="nt-access-pager"><span>{offset+1}–{Math.min(offset+25,page.total)} of {page.total}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled||loading||!offset} onClick={()=>{setOffset(offset-25);onChange('')}}>Previous choices</button><button type="button" className="tool-btn tool-btn-ghost" disabled={disabled||loading||offset+25>=page.total} onClick={()=>{setOffset(offset+25);onChange('')}}>Next choices</button></div>}
 </div>;
}
