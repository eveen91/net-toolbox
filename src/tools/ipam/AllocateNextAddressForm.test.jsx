import { describe, expect, it } from "vitest";
import { allocationDraftToRequest } from "./AllocateNextAddressForm.jsx";

describe("allocationDraftToRequest", () => {
  it("normalizes optional metadata and only retains VM clusters for VMs", () => {
    expect(allocationDraftToRequest({
      status: "reserved", hostname: " host-01 ", description: " ", team: " ops ",
      machineType: "physical", vmCluster: "ignored", environment: "prod", locked: true,
    })).toEqual({
      status: "reserved", hostname: "host-01", description: null, team: "ops",
      machineType: "physical", vmCluster: null, environment: "prod", locked: true,
    });
  });
});
