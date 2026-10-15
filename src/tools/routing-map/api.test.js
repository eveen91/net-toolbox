import { afterEach, expect, it, vi } from "vitest";
import { setTenantId } from "../../tenantContext.js";
import { listRoutingHosts, exportRoutingHosts, getRoutingHost, saveRoutingHost, deleteRoutingHost } from "./api.js";

afterEach(() => { setTenantId(null); vi.unstubAllGlobals(); });

it("uses the active tenant for list, visualization/trace export, details, save and delete", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
  vi.stubGlobal("fetch", fetch);
  setTenantId("tenant-a");
  await listRoutingHosts();
  await exportRoutingHosts();
  await getRoutingHost("router/site");
  await saveRoutingHost("router/site", [{ network: "10.0.0.0/24", nextHop: "directly connected" }]);
  await deleteRoutingHost("router/site");
  for (const [, options] of fetch.mock.calls) {
    expect(options.headers.get("X-Tenant-ID")).toBe("tenant-a");
    expect(options.credentials).toBe("include");
  }
  expect(fetch.mock.calls[2][0]).toContain("router%2Fsite");
  expect(fetch.mock.calls[3][1].method).toBe("PUT");
  expect(fetch.mock.calls[4][1].method).toBe("DELETE");
  setTenantId("tenant-b");
  await exportRoutingHosts();
  expect(fetch.mock.calls[5][1].headers.get("X-Tenant-ID")).toBe("tenant-b");
});

it("sends source tenant, destination and reviewed version for a move", async () => {
  const { listRoutingMoveTargets, previewRoutingHostMove, moveRoutingHost } = await import("./api.js");
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  setTenantId("source");
  await listRoutingMoveTargets();
  await previewRoutingHostMove("router site", "target");
  await moveRoutingHost("router site", "target", "reviewed-version");
  for (const [, options] of fetch.mock.calls) expect(options.headers.get("X-Tenant-ID")).toBe("source");
  expect(fetch.mock.calls[1][0]).toContain("router%20site/move-preview?targetTenantId=target");
  expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ targetTenantId: "target", expectedVersion: "reviewed-version" });
});

it('imports saved interface networks with tenant, CSRF and the reviewed host timestamp', async () => {
  const { importRoutingNetworks } = await import('./api.js');
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ summary: { created: 1 } }) });
  vi.stubGlobal('fetch', fetch);
  setTenantId('tenant-a');
  await importRoutingNetworks('router branch', '2026-10-14T12:00:00+00:00', ['eth0']);
  await importRoutingNetworks('router branch', 'saved-time');
  expect(fetch.mock.calls[0][0]).toContain('router%20branch/ipam-import');
  expect(fetch.mock.calls[0][1].headers.get('X-Tenant-ID')).toBe('tenant-a');
  expect(fetch.mock.calls[0][1].headers.get('X-CSRF-TOKEN')).toBe('fixed-csrf-token');
  expect(fetch.mock.calls[0][1].method).toBe('POST');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ expectedUpdatedAt: '2026-10-14T12:00:00+00:00', interfaces: ['eth0'] });
  expect(JSON.parse(fetch.mock.calls[1][1].body).interfaces).toBeNull();
});

it('reports stale-source rejection rather than treating an import as successful', async () => {
  const { importRoutingNetworks } = await import('./api.js');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: 'Routing interfaces changed; reload the host before importing' }) }));
  await expect(importRoutingNetworks('router', 'old-time')).rejects.toThrow('Routing interfaces changed');
});
