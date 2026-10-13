import { describe, expect, it } from "vitest";
import { canIpam } from "./permissions.js";

describe("IPAM frontend permissions", () => {
  it("allows anonymous access when authentication is disabled", () => {
    expect(canIpam(null, "ipam.write")).toBe(true);
  });

  it("recognizes granular, legacy, and wildcard permissions", () => {
    expect(canIpam({ permissions: ["ipam.read"] }, "ipam.read")).toBe(true);
    expect(canIpam({ permissions: ["ipam.read"] }, "ipam.write")).toBe(false);
    expect(canIpam({ permissions: ["ipam"] }, "ipam.scan")).toBe(true);
    expect(canIpam({ permissions: ["*"] }, "ipam.admin")).toBe(true);
  });
});
