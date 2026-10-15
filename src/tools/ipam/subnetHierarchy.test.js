import { describe, expect, it } from 'vitest';
import { subnetBrowserRows } from './subnetHierarchy.js';
const subnets = [
  { id: 3, cidr: '10.1.2.0/24', parentId: 2 },
  { id: 4, cidr: '10.2.0.0/16', parentId: 1 },
  { id: 2, cidr: '10.1.0.0/16', parentId: 1 },
  { id: 1, cidr: '10.0.0.0/8', parentId: null },
  { id: 5, cidr: '192.0.2.0/24', parentId: null },
];
describe('subnet browser hierarchy', () => {
  it('places each child immediately within its parent, even when the API list is flat', () => {
    const rows = subnetBrowserRows(subnets, subnets.map(item => item.id));
    expect(rows.map(row => [row.subnet.id, row.depth])).toEqual([[1,0],[4,1],[2,1],[3,2],[5,0]]);
  });
  it('collapses an entire nested branch while preserving siblings and roots', () => {
    expect(subnetBrowserRows(subnets, subnets.map(item => item.id), new Set([2])).map(row => row.subnet.id)).toEqual([1,4,2,5]);
    expect(subnetBrowserRows(subnets, subnets.map(item => item.id), new Set([1])).map(row => row.subnet.id)).toEqual([1,5]);
  });
  it('opens a matching child path and retains filtered parents as context', () => {
    const rows = subnetBrowserRows(subnets, [3], new Set([1,2]), true);
    expect(rows.map(row => [row.subnet.id, row.isContext, row.depth])).toEqual([[1,true,0],[2,true,1],[3,false,2]]);
    expect(rows.every(row => row.expanded)).toBe(true);
  });
  it('keeps an orphan visible and returns no rows for no matches', () => {
    expect(subnetBrowserRows([{id:6,parentId:99}], [6])[0].depth).toBe(0);
    expect(subnetBrowserRows(subnets, [])).toEqual([]);
  });
});
