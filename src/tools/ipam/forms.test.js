import { describe, expect, it } from "vitest";
import { addressDraftToRequest } from "./AddressPopover.jsx";
import { subnetDraftToRequest } from "./AddSubnetForm.jsx";

const baseAddress = {
  status: "used", allocationType: "static", hostname: "", description: "", team: "",
  machineType: "", vmCluster: "", environment: "", locked: false,
};

describe("IPAM form payloads", () => {
  it("normalizes a subnet form before submission", () => {
    expect(subnetDraftToRequest({ cidr: " 10.0.1.1/24 ", vlan: " 120 ", description: " edge " })).toEqual({
      cidr: "10.0.1.1/24", vlan: 120, description: "edge",
    });
    expect(subnetDraftToRequest({ cidr: "10.0.2.0/24", vlan: "", description: " " })).toEqual({
      cidr: "10.0.2.0/24", vlan: null, description: null,
    });
  });

  it("normalizes address form metadata and clears non-VM clusters", () => {
    expect(addressDraftToRequest({ ...baseAddress, hostname: " host-01 ", description: " web ", team: " ops ", machineType: "physical", vmCluster: "ignored", environment: "prod", locked: true })).toEqual({
      status: "used", allocationType: "static", hostname: "host-01", description: "web", team: "ops",
      machineType: "physical", vmCluster: null, environment: "prod", locked: true,
    });
  });

  it("keeps VM cluster for VM address forms", () => {
    expect(addressDraftToRequest({ ...baseAddress, machineType: "vm", vmCluster: " cluster-a " }).vmCluster).toBe("cluster-a");
  });
});
