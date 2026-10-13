import { describe, expect, it } from "vitest";
import { fitScale } from "./DeviceCanvas.jsx";

describe("device canvas fit", () => {
  it("keeps a wide 48-port panel within the space left by an inspector", () => {
    const scale = fitScale(990, 320, 2600, 280);
    expect(scale * 2600).toBeLessThanOrEqual(990);
    expect(scale * 280).toBeLessThanOrEqual(320);
  });
  it("fits tall server NIC layouts by height and never enlarges small panels", () => {
    expect(fitScale(1200, 320, 600, 1000)).toBe(0.32);
    expect(fitScale(1200, 320, 600, 200)).toBe(1);
  });
});
