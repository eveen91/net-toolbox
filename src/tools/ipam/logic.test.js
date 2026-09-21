import { describe, expect, it, vi } from "vitest";
import {
  addressesToCsv,
  fetchAllAddressPages,
  heatmapPageForAddress,
  isOutsidePointerStart,
  normalizeAddressPageLimit,
  shouldCloseAddressPopover,
} from "./logic.js";

describe("IPAM address helpers", () => {
  it("caps address page requests at 500 records", () => {
    expect(normalizeAddressPageLimit(900)).toBe(500);
    expect(normalizeAddressPageLimit(0)).toBe(100);
    expect(normalizeAddressPageLimit(-1)).toBe(1);
  });

  it("fetches every address page without requesting more than 500", async () => {
    const records = Array.from({ length: 1201 }, (_, id) => ({ id, address: `10.0.${Math.floor(id / 256)}.${id % 256}` }));
    const fetchPage = vi.fn(({ limit, offset }) => Promise.resolve({
      addresses: records.slice(offset, offset + limit),
      total: records.length,
    }));

    const result = await fetchAllAddressPages(fetchPage, 900);

    expect(result).toEqual(records);
    expect(fetchPage).toHaveBeenCalledTimes(3);
    expect(fetchPage.mock.calls.every(([request]) => request.limit <= 500)).toBe(true);
  });

  it("calculates the heatmap page containing a table address", () => {
    expect(heatmapPageForAddress("10.0.0.0/16", "10.0.4.20", 500)).toBe(2);
  });

  it("serializes all supplied addresses and escapes CSV fields", () => {
    const csv = addressesToCsv([
      { address: "10.0.0.1", status: "used", hostname: "one,primary" },
      { address: "10.0.0.2", status: "free", hostname: "two" },
    ]);

    expect(csv.split("\r\n")).toHaveLength(3);
    expect(csv).toContain('"one,primary"');
    expect(csv).toContain("10.0.0.2");
  });

  it("closes the address dialog for controls and matching async requests", () => {
    expect(shouldCloseAddressPopover(undefined, "10.0.0.1")).toBe(true);
    expect(shouldCloseAddressPopover({ type: "click" }, "10.0.0.1")).toBe(true);
    expect(shouldCloseAddressPopover("10.0.0.1", "10.0.0.1")).toBe(true);
    expect(shouldCloseAddressPopover("10.0.0.2", "10.0.0.1")).toBe(false);
  });

  it("only treats a pointer gesture that starts outside as an outside click", () => {
    const inside = {};
    const outside = {};
    const container = { contains: (target) => target === inside };

    expect(isOutsidePointerStart(container, inside)).toBe(false);
    expect(isOutsidePointerStart(container, outside)).toBe(true);
    expect(isOutsidePointerStart(null, outside)).toBe(false);
  });
});
