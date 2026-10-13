import { describe, expect, it } from "vitest";
import { navigationGroups, pageFromHash } from "./navigation.js";
import { visibleTools } from "../tools/registry.js";

describe("workspace navigation", () => {
  it("groups only tools available to a granular IPAM reader", () => {
    const groups = navigationGroups(visibleTools({ permissions: ["ipam.read"] }, true));
    expect(groups.map((group) => group.id)).toEqual(["infrastructure"]);
    expect(groups[0].items.map((tool) => tool.id)).toEqual(["ipam"]);
  });
  it("retains global calculator access independently from tenant permissions", () => {
    const groups = navigationGroups(visibleTools({ permissions: ["device-visualization"], globalPermissions: ["ip-calculator"] }, true));
    expect(groups.flatMap((group) => group.items.map((tool) => tool.id))).toEqual(["device-visualization", "ip-calculator"]);
  });
  it("restores the module from bookmarked hashes and defaults an empty URL", () => {
    expect(pageFromHash("#/device-visualization")).toBe("device-visualization");
    expect(pageFromHash("#/ipam?subnet=3")).toBe("ipam");
    expect(pageFromHash("")).toBe("home");
  });
});
