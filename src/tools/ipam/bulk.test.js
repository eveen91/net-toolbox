import { describe, expect, it } from "vitest";
import { bulkFieldPayload, togglePageSelection, toggleSelection } from "./bulk.js";

describe("IPAM bulk selection helpers", () => {
  it("selects and clears only the visible page", () => {
    expect(togglePageSelection([1], [1, 2, 3]).sort()).toEqual([1, 2, 3]);
    expect(togglePageSelection([1, 2, 3, 4], [1, 2, 3]).sort()).toEqual([4]);
  });

  it("toggles one selected address", () => {
    expect(toggleSelection([1, 2], 2)).toEqual([1]);
    expect(toggleSelection([1], 2).sort()).toEqual([1, 2]);
  });

  it("omits unchanged bulk fields", () => {
    expect(bulkFieldPayload({ status: "reserved", team: "", locked: false })).toEqual({ status: "reserved", locked: false });
  });
});
