import { afterEach, expect, it, vi } from "vitest";
import { apiFetch } from "./apiFetch.js";
import { getTenantId, setTenantId, tenantStreamUrl } from "./tenantContext.js";
import { hasToolAccess, visibleTools } from "./tools/registry.js";

afterEach(() => { setTenantId(null); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it("captures the selected tenant without modifying caller headers", async () => {
  const fetch = vi.fn().mockResolvedValue({ status: 200 });
  vi.stubGlobal("fetch", fetch);
  const original = { "Content-Type": "application/json" };
  setTenantId("tenant-a");
  const first = apiFetch("/api/devices", { method: "POST", headers: original });
  setTenantId("tenant-b");
  await first;
  await apiFetch("/api/validation/plans");
  expect(fetch.mock.calls[0][1].headers.get("X-Tenant-ID")).toBe("tenant-a");
  expect(fetch.mock.calls[1][1].headers.get("X-Tenant-ID")).toBe("tenant-b");
  expect(fetch.mock.calls[0][1].headers.get("X-CSRF-TOKEN")).toBe("fixed-csrf-token");
  expect(original).toEqual({ "Content-Type": "application/json" });
});

it("scopes EventSource URLs and clears the selection", () => {
  setTenantId("tenant-a");
  expect(tenantStreamUrl("/stream/job")).toBe("/stream/job?tenant_id=tenant-a");
  expect(tenantStreamUrl("/stream/job?x=1")).toBe("/stream/job?x=1&tenant_id=tenant-a");
  setTenantId(null);
  expect(getTenantId()).toBeNull();
  expect(tenantStreamUrl("/stream/job")).toBe("/stream/job");
});

it("does not infer platform administration from tenant tool access", () => {
  expect(hasToolAccess(["ipam.read"], "ipam")).toBe(true);
  expect(hasToolAccess(["ipam.read"], "troubleshoot")).toBe(false);
});

it("keeps browser calculators global while persisted tools use tenant permissions", () => {
  const user = { permissions: ["ipam.read"], globalPermissions: ["ip-calculator", "subnet-splitter"] };
  expect(visibleTools(user, true).map((tool) => tool.id)).toEqual(["subnet-splitter", "ip-calculator", "ipam"]);
  expect(visibleTools({ ...user, permissions: [] }, true).map((tool) => tool.id)).toEqual(["subnet-splitter", "ip-calculator"]);
});

it("routes relative module APIs to the configured backend without double prefixes", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://toolbox.example");
  const fetch = vi.fn().mockResolvedValue({ status: 200 });
  vi.stubGlobal("fetch", fetch);
  setTenantId("tenant-a");
  await apiFetch("/api/devices");
  await apiFetch("https://toolbox.example/api/validation/plans");
  expect(fetch.mock.calls[0][0]).toBe("https://toolbox.example/api/devices");
  expect(fetch.mock.calls[1][0]).toBe("https://toolbox.example/api/validation/plans");
  expect(fetch.mock.calls[0][1].headers.get("X-Tenant-ID")).toBe("tenant-a");
});
