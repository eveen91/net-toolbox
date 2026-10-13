import { describe, expect, it } from "vitest";
import { parsePorts, validateWorkload, validateSettings } from "./logic.js";

describe("complete port validation", () => {
  it("accepts valid full decimal lines and comments", () => expect(parsePorts(" 22 \n#comment\n65535\n00443")).toEqual([22,65535,443]));
  it.each(["22abc", "22.5", "1e3", "0x16", "-22", "0", "65536", "22,443", "22 443", "Infinity"])("rejects %s", input => expect(() => parsePorts(input)).toThrow("Invalid port"));
});
it("caps each list and the complete matrix at the boundary", () => {
  expect(validateWorkload(Array(16), Array(64), [443])).toBe(1024);
  expect(() => validateWorkload(Array(16), Array(64), [22,443])).toThrow("2048 combinations");
  expect(() => validateWorkload(Array(17), ["host"], [22])).toThrow("16 sources");
  expect(() => validateWorkload(["host"], Array(65), [22])).toThrow("64 destinations");
  expect(() => validateWorkload(["host"], ["host"], Array(33))).toThrow("32 ports");
});
it("requires secure Basic and valid numeric settings", () => {
  const settings={connectTimeout:5,sshPort:22,winrmPort:5986,winrmScheme:"https",winrmTransport:"basic"};
  expect(() => validateSettings(settings)).not.toThrow();
  expect(() => validateSettings({...settings,winrmScheme:"http"})).toThrow("requires HTTPS");
  expect(() => validateSettings({...settings,sshPort:22.5})).toThrow("SSH port");
  expect(() => validateSettings({...settings,connectTimeout:0})).toThrow("Connect timeout");
});
