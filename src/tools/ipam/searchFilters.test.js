import { describe, expect, it } from "vitest";
import { filterSubnetsByTags, searchSubnets } from "./SubnetSearch.jsx";

describe("IPAM subnet search and tag filters", () => {
  const subnets = [
    { id: 1, cidr: "10.0.0.0/24", description: "Production API", vlan: 120, tagIds: [1, 2] },
    { id: 2, cidr: "10.0.1.0/24", description: "Development", vlan: 130, tagIds: [2] },
    { id: 3, cidr: "10.0.2.0/24", description: "Operations", vlan: null, tagIds: [3] },
  ];

  it("requires every active tag filter", () => {
    expect(filterSubnetsByTags(subnets, [2]).map((subnet) => subnet.id)).toEqual([1, 2]);
    expect(filterSubnetsByTags(subnets, [1, 2]).map((subnet) => subnet.id)).toEqual([1]);
    expect(filterSubnetsByTags(subnets, []).map((subnet) => subnet.id)).toEqual([1, 2, 3]);
  });

  it("searches CIDR, description, and VLAN case-insensitively", () => {
    expect(searchSubnets(subnets, "api").map((subnet) => subnet.id)).toEqual([1]);
    expect(searchSubnets(subnets, "10.0.1").map((subnet) => subnet.id)).toEqual([2]);
    expect(searchSubnets(subnets, "130").map((subnet) => subnet.id)).toEqual([2]);
  });

  it("composes tag filtering with text search", () => {
    const tagged = filterSubnetsByTags(subnets, [2]);
    expect(searchSubnets(tagged, "development").map((subnet) => subnet.id)).toEqual([2]);
  });
});
