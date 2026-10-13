import { describe, expect, it } from "vitest";
import { ipToNumber, isValidIPv4 } from "./DhcpPoolManager.jsx";

describe("DHCP pool form validation", () => {
  it("accepts canonical IPv4 addresses and rejects malformed input", () => {
    expect(isValidIPv4("10.0.0.1")).toBe(true);
    expect(isValidIPv4("10.0.0.01")).toBe(false);
    expect(isValidIPv4("10.0.0.256")).toBe(false);
    expect(isValidIPv4("not-an-ip")).toBe(false);
  });

  it("orders numeric IPv4 values for start/end validation", () => {
    expect(ipToNumber("10.0.0.10")).toBeLessThan(ipToNumber("10.0.0.20"));
  });
});
