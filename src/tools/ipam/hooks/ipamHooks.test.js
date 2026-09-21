import { afterEach, describe, expect, it, vi } from "vitest";
import { reconcileTagIds } from "./useIpamData.js";
import { openAutodiscoverStream, scanAddressLabel } from "./useIpamScan.js";
import { getAutodiscoverJob } from "../api.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

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

  it("opens the scan stream with session credentials", () => {
    const EventSource = vi.fn();
    vi.stubGlobal("EventSource", EventSource);

    openAutodiscoverStream(7, "job-1");

    expect(EventSource).toHaveBeenCalledWith(
      "/api/ipam/subnets/7/autodiscover/stream/job-1",
      { withCredentials: true }
    );
  });

  it("reads persisted scan status for stream recovery", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ jobId: "job-1", status: "done" }),
    });
    vi.stubGlobal("fetch", fetch);

    await expect(getAutodiscoverJob(7, "job-1")).resolves.toEqual({
      jobId: "job-1",
      status: "done",
    });
    expect(fetch).toHaveBeenCalledWith(
      "/api/ipam/subnets/7/autodiscover/jobs/job-1",
      expect.objectContaining({ credentials: "include" })
    );
  });
});
