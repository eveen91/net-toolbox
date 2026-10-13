import { afterEach, describe, expect, it, vi } from "vitest";
import { getSubnetAddresses, listSubnets } from "./api.js";

afterEach(() => vi.unstubAllGlobals());

describe("IPAM API error handling", () => {
  it("surfaces backend validation details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 400, statusText: "Bad Request",
      json: async () => ({ detail: "CIDR must be a valid IPv4 network" }),
    }));

    await expect(listSubnets()).rejects.toThrow("Backend error (400): CIDR must be a valid IPv4 network");
  });

  it("falls back to status text when an error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 503, statusText: "Service Unavailable",
      json: async () => { throw new Error("invalid JSON"); },
    }));

    await expect(listSubnets()).rejects.toThrow("Backend error (503): Service Unavailable");
  });

  it("keeps request filters while surfacing an API error", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: false, status: 409, statusText: "Conflict",
      json: async () => ({ detail: "Record was modified by another user" }),
    });
    vi.stubGlobal("fetch", fetch);

    await expect(getSubnetAddresses(7, { status: "used", tagId: 3, query: "api" })).rejects.toThrow("Backend error (409): Record was modified by another user");
    expect(fetch.mock.calls[0][0]).toContain("status=used");
    expect(fetch.mock.calls[0][0]).toContain("tag_id=3");
    expect(fetch.mock.calls[0][0]).toContain("query=api");
  });
});

it("lists filtered archives and restores with credentials and the mutation header", async () => {
  const { fetchArchives, restoreArchive } = await import("./api.js");
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal("fetch", fetch);
  await fetchArchives("dhcp_pool");
  expect(fetch.mock.calls[0][0]).toContain("/archives?resource_type=dhcp_pool");
  await restoreArchive(3);
  expect(fetch.mock.calls[1][0]).toContain("/archives/3/restore");
  expect(fetch.mock.calls[1][1]).toMatchObject({ method: "POST", credentials: "include" });
  expect(fetch.mock.calls[1][1].headers.get("X-CSRF-TOKEN")).toBe("fixed-csrf-token");
});

it("sends source tenant, destination and reviewed version for subnet transfers", async () => {
  const { listSubnetMoveTargets, previewSubnetMove, moveSubnetToTenant } = await import("./api.js");
  const { setTenantId } = await import("../../tenantContext.js");
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  setTenantId("ipam-source");
  try {
    await listSubnetMoveTargets();
    await previewSubnetMove(7, "target");
    await moveSubnetToTenant(7, "target", "review-version");
    for (const [, options] of fetch.mock.calls) expect(options.headers.get("X-Tenant-ID")).toBe("ipam-source");
    expect(fetch.mock.calls[1][0]).toContain("/subnets/7/move-preview?targetTenantId=target");
    expect(fetch.mock.calls[2][1].method).toBe("POST");
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ targetTenantId: "target", expectedVersion: "review-version" });
  } finally { setTenantId(null); }
});
