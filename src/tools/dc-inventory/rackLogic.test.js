import {expect,it} from 'vitest';
import {rackRows,unitRange} from './rackLogic.js';
it('draws the top U first and reserves the complete device range',()=>{
  const devices=[{id:1,rackPosition:1,heightU:2},{id:2,rackPosition:5,heightU:1}];
  expect(rackRows(6,devices)).toEqual([{unit:6,deviceId:null},{unit:5,deviceId:2},{unit:4,deviceId:null},{unit:3,deviceId:null},{unit:2,deviceId:1},{unit:1,deviceId:1}]);
  expect(unitRange(devices[0])).toBe('U1–U2');
  expect(unitRange({rackPosition:null,heightU:null})).toBe('Unassigned');
});
