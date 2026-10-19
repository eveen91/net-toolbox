import React,{useEffect,useRef} from 'react';
import {PAGES} from './fields.js';

export default function ChapterTabs({value,onChange,disabled,pages=PAGES}) {
  const buttons=useRef([]);
  useEffect(()=>{
    const reveal=()=>buttons.current[pages.findIndex(page=>page.id===value)]?.scrollIntoView({block:'nearest',inline:'nearest'});
    reveal();window.addEventListener('resize',reveal);
    return()=>window.removeEventListener('resize',reveal);
  },[value,pages]);
  const move=(event,index)=>{
    let next;
    if(event.key==='ArrowRight')next=(index+1)%pages.length;
    else if(event.key==='ArrowLeft')next=(index-1+pages.length)%pages.length;
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=pages.length-1;
    else return;
    event.preventDefault();onChange(pages[next].id);buttons.current[next]?.focus();
  };
  return <div className="dc-doc-tabs" role="tablist" aria-label="DC documentation chapters">
    {pages.map((page,index)=><button key={page.id} ref={node=>{buttons.current[index]=node;}} type="button" role="tab" id={`dc-doc-tab-${page.id}`} aria-controls={`dc-doc-page-${page.id}`} aria-selected={value===page.id} tabIndex={value===page.id?0:-1} disabled={disabled} onClick={()=>onChange(page.id)} onKeyDown={event=>move(event,index)}>{page.label}</button>)}
  </div>;
}
