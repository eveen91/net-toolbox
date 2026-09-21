import { describe, expect, it } from "vitest";
import { reconcileTagIds } from "./useIpamData.js";
import { scanAddressLabel } from "./useIpamScan.js";

describe("IPAM hook helpers", () => {
  it("reconciles added and removed tag identifiers", () => {
    expect(reconcileTagIds([{ id: 1 }, { id: 2 }], [2, 3])).toEqual({
      toAdd: [3],
      toRemove: [1],
    });
  });

  it("formats scan address states", () => {
    expect(scanAddressLabel({ status: "pending" })).toBe("pending");
    expect(scanAddressLabel({ status: "in_progress" })).toBe("scanning…");
    expect(scanAddressLabel({ status: "complete", alive: true })).toBe("used");
    expect(scanAddressLabel({ status: "complete", alive: false })).toBe("free");
  });
});
