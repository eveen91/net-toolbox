import {useCallback,useEffect,useRef,useState} from 'react';
import {listDataCenters,listRacks} from './api.js';

export default function useCatalog(dataCenterId,deviceAccess=false,revision=0) {
  const [dc,setDC]=useState({items:[],total:0});
  const [racks,setRacks]=useState({items:[],total:0});
  const [loading,setLoading]=useState({dc:false,racks:false});
  const [errors,setErrors]=useState({dc:null,racks:null});
  const [retry,setRetry]=useState(0);
  const tickets=useRef({dc:0,racks:0});
  const load=useCallback(async(kind,offset=0)=>{
    const ticket=++tickets.current[kind];
    const setter=kind==='dc'?setDC:setRacks;
    setLoading(old=>({...old,[kind]:true}));setErrors(old=>({...old,[kind]:null}));
    try {
      const result=kind==='dc'?await listDataCenters({limit:50,offset},deviceAccess):await listRacks({dataCenterId,limit:50,offset},deviceAccess);
      if(ticket===tickets.current[kind])setter(old=>({...result,items:offset?[...old.items,...result.items]:result.items}));
    }catch(error){if(ticket===tickets.current[kind])setErrors(old=>({...old,[kind]:error.message}));}
    finally{if(ticket===tickets.current[kind])setLoading(old=>({...old,[kind]:false}));}
  },[dataCenterId,deviceAccess]);
  useEffect(()=>{setDC({items:[],total:0});load('dc');return()=>{tickets.current.dc++;};},[deviceAccess,revision,retry]); // DCs do not depend on the selected rack/DC.
  useEffect(()=>{
    setRacks({items:[],total:0});setErrors(old=>({...old,racks:null}));setLoading(old=>({...old,racks:false}));
    if(dataCenterId)load('racks');
    return()=>{tickets.current.racks++;};
  },[dataCenterId,deviceAccess,revision,retry,load]);
  return {dc,racks,loading,error:errors.dc||errors.racks,moreDC:()=>load('dc',dc.items.length),moreRacks:()=>load('racks',racks.items.length),retry:()=>setRetry(value=>value+1)};
}
