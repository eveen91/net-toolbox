import React,{useState} from 'react';
import {sourcePage} from './fields.js';
const text=value=>value==null||value===''?'Not recorded':typeof value==='object'?JSON.stringify(value):String(value);
function Table({table}){
  const [offset,setOffset]=useState(0);
  return <section className="dc-doc-source-table"><h4>{table.title} <small>({table.rows.length})</small></h4><div className="tool-table-wrap"><table className="tool-table" style={{tableLayout:'fixed',minWidth:Math.max(420,table.columns.length*140)}}><thead><tr>{table.columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{table.rows.slice(offset,offset+50).map((row,index)=><tr key={index}>{row.map((value,col)=><td key={col}>{text(value)}</td>)}</tr>)}</tbody></table></div>{!table.rows.length&&<p className="tool-hint">No records.</p>}{table.rows.length>50&&<div className="dc-doc-pager"><button type="button" className="tool-btn tool-btn-ghost" disabled={!offset} onClick={()=>setOffset(value=>value-50)}>Previous rows</button><span>{offset+1}–{Math.min(offset+50,table.rows.length)} of {table.rows.length}</span><button type="button" className="tool-btn tool-btn-ghost" disabled={offset+50>=table.rows.length} onClick={()=>setOffset(value=>value+50)}>Next rows</button></div>}</section>;
}
export default function SourceTables({snapshot,chapter,templateId='network',sourceMap}){
 const tables=(snapshot?.tables||[]).filter(table=>!chapter||sourcePage(table,templateId,sourceMap)===chapter);
 if(!tables.length)return null;
 return <div className="dc-doc-source-tables" aria-label="Saved infrastructure data">{tables.map(table=><Table key={`${snapshot.collectedAt}-${table.id}`} table={table}/>)}</div>;
}
export function Provenance({snapshot}){
 if(!snapshot?.collectedAt)return null;
 return <details className="tool-panel dc-doc-provenance"><summary>Source provenance · {new Date(snapshot.collectedAt).toLocaleString()} · {snapshot.sources.length} records</summary><ul>{snapshot.sources.map((source,index)=><li key={index}>{source.module} · {source.name} · ID {source.id} · version {source.version??'Not recorded'} · updated {source.updatedAt||'Not recorded'}</li>)}</ul>{snapshot.warnings?.map((warning,index)=><p className="tool-hint" key={index}>{warning}</p>)}</details>;
}
