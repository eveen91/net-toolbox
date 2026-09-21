import { describe, expect, it } from "vitest";
import { allocationDraftToRequest, prefixBounds } from "./allocation.js";

describe("allocation helpers", () => {
  it("derives numeric prefix bounds from the selected parent", () => {
    expect(prefixBounds("10.0.0.0/23")).toEqual({ min: 23, max: 32 });
  });

  it("builds the atomic creation payload", () => {
    expect(allocationDraftToRequest({ parent: "10.0.0.0/24", cidr: "10.0.0.0/27", freshnessToken: "token", vlan: "120", description: " edge ", tagIds: [4, 8] })).toEqual({ parent: "10.0.0.0/24", cidr: "10.0.0.0/27", freshnessToken: "token", vlan: 120, description: "edge", tagIds: [4, 8] });
  });
});
