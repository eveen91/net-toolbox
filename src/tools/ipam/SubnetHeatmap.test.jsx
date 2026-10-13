import { describe, expect, it } from "vitest";
import { nextHeatmapCellIndex } from "./SubnetHeatmap.jsx";

describe("heatmap keyboard navigation", () => {
  const page = { columns: 4, pageStart: 0, pageEnd: 12 };

  it("moves horizontally and vertically by the grid column count", () => {
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 5, key: "ArrowRight" })).toBe(6);
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 5, key: "ArrowLeft" })).toBe(4);
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 5, key: "ArrowDown" })).toBe(9);
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 5, key: "ArrowUp" })).toBe(1);
  });

  it("skips child, DHCP, and reservation placeholder cells", () => {
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 3, key: "ArrowRight", placeholders: [4, 5] })).toBe(6);
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 10, key: "ArrowLeft", placeholders: [8, 9] })).toBe(7);
  });

  it("keeps focus on the current cell at page boundaries or for unrelated keys", () => {
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 0, key: "ArrowLeft" })).toBe(0);
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 11, key: "ArrowDown" })).toBe(11);
    expect(nextHeatmapCellIndex({ ...page, currentIndex: 5, key: "Enter" })).toBe(5);
  });
});
