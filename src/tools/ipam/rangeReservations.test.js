import { describe, expect, it } from "vitest";
import { activeReservationForIp, compareIpv4, isValidIpv4 } from "./rangeReservations.js";

describe("range reservations", () => {
  it("validates and compares IPv4 values", () => {
    expect(isValidIpv4("10.0.0.1")).toBe(true);
    expect(isValidIpv4("10.0.0.999")).toBe(false);
    expect(compareIpv4("10.0.0.2", "10.0.0.10")).toBeLessThan(0);
  });

  it("matches only active reservations", () => {
    const reservations = [
      { start_ip: "10.0.0.10", end_ip: "10.0.0.20", status: "active" },
      { start_ip: "10.0.0.30", end_ip: "10.0.0.40", status: "released" },
    ];
    expect(activeReservationForIp(reservations, "10.0.0.15")).toBe(reservations[0]);
    expect(activeReservationForIp(reservations, "10.0.0.35")).toBeNull();
  });
});
