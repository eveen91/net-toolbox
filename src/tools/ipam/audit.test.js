import { describe, expect, it } from "vitest";
import {
  auditDiffRows,
  auditEventLabel,
  auditEventTone,
  auditPageCount,
  buildAuditQueryParams,
  formatAuditValue,
} from "./audit.js";

describe("IPAM audit helpers", () => {
  it("builds a paginated contextual audit query with repeated event filters", () => {
    const params = buildAuditQueryParams({
      subnetId: 42,
      addressId: 128,
      startDate: "2026-09-01",
      endDate: "2026-09-21",
      changeTypes: ["create", "update"],
      limit: 25,
      offset: 50,
    });

    expect(params.get("subnet_id")).toBe("42");
    expect(params.get("address_id")).toBe("128");
    expect(params.get("start_date")).toBe("2026-09-01");
    expect(params.get("end_date")).toBe("2026-09-21");
    expect(params.getAll("change_type")).toEqual(["create", "update"]);
    expect(params.get("limit")).toBe("25");
    expect(params.get("offset")).toBe("50");
  });

  it("omits empty filters from query parameters", () => {
    expect(buildAuditQueryParams({ subnetId: "", startDate: "", changeTypes: [] }).toString()).toBe("");
  });

  it("creates sorted diff rows from the union of old and new fields", () => {
    expect(auditDiffRows({ status: "free", hostname: "old" }, { status: "used", team: "netops" })).toEqual([
      { field: "hostname", oldValue: "old", newValue: undefined },
      { field: "status", oldValue: "free", newValue: "used" },
      { field: "team", oldValue: undefined, newValue: "netops" },
    ]);
  });

  it("formats labels, tones, values, and page counts", () => {
    expect(auditEventLabel("dhcp_pool_move")).toBe("DHCP pool moved");
    expect(auditEventLabel("release")).toBe("Address released");
    expect(auditEventLabel("custom_event")).toBe("Custom Event");
    expect(auditEventTone("subnet_delete")).toBe("danger");
    expect(auditEventTone("release")).toBe("danger");
    expect(formatAuditValue({ enabled: true })).toBe('{"enabled":true}');
    expect(formatAuditValue(null)).toBe("—");
    expect(auditPageCount(51, 25)).toBe(3);
  });
});
