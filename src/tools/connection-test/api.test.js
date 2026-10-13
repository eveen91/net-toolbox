import { afterEach, expect, it, vi } from "vitest";
import { runConnectionTest } from "./api.js";
import { setTenantId } from "../../tenantContext.js";
afterEach(() => { vi.unstubAllGlobals(); setTenantId(null); });
it("preserves tenant, credentials and CSRF when running", async () => {
  const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({rows:[]})});
  vi.stubGlobal("fetch",fetch); setTenantId("selected");
  await runConnectionTest({ports:[443]});
  expect(fetch.mock.calls[0][1].headers.get("X-Tenant-ID")).toBe("selected");
  expect(fetch.mock.calls[0][1].headers.get("X-CSRF-TOKEN")).toBe("fixed-csrf-token");
  expect(fetch.mock.calls[0][1].credentials).toBe("include");
});
it("shows readable validation errors without dumping the submitted input", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false,status:422,json:async()=>({detail:[{loc:["body","ports",0],msg:"Input should be a valid integer",input:"22abc"}]})}));
  await expect(runConnectionTest({})).rejects.toThrow("ports.0: Input should be a valid integer");
});
