export function rackRows(heightU,devices) {
  const occupied=new Map();
  for(const device of devices)for(let unit=device.rackPosition;unit<device.rackPosition+device.heightU;unit++)occupied.set(unit,device.id);
  return Array.from({length:heightU},(_,index)=>({unit:heightU-index,deviceId:occupied.get(heightU-index)??null}));
}
export const unitRange=device=>device.rackPosition==null?'Unassigned':`U${device.rackPosition}–U${device.rackPosition+device.heightU-1}`;
