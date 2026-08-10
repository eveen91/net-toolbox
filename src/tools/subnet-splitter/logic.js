// Core subnetting logic — ported from the original PowerShell script.
// Kept free of any React/UI concerns so it can be unit tested on its own.

export function ipToInt(ip) {
  const trimmed = ip.trim();
  const parts = trimmed.split(".");
  if (parts.length !== 4) throw new Error(`Invalid IP address: ${ip}`);
  const nums = parts.map((p) => {
    if (!/^\d+$/.test(p)) throw new Error(`Invalid IP address: ${ip}`);
    const n = parseInt(p, 10);
    if (n < 0 || n > 255) throw new Error(`Invalid IP address: ${ip}`);
    return n;
  });
  return nums[0] * 16777216 + nums[1] * 65536 + nums[2] * 256 + nums[3];
}

export function intToIp(int) {
  const b0 = Math.floor(int / 16777216) % 256;
  const b1 = Math.floor(int / 65536) % 256;
  const b2 = Math.floor(int / 256) % 256;
  const b3 = int % 256;
  return `${b0}.${b1}.${b2}.${b3}`;
}

export function prefixToMask(prefix) {
  if (prefix < 0 || prefix > 32) throw new Error(`Invalid prefix length: ${prefix}`);
  const maskInt = prefix === 0 ? 0 : Math.pow(2, 32) - Math.pow(2, 32 - prefix);
  return intToIp(maskInt);
}

export function rangeFromCidr(cidr) {
  const parts = cidr.split("/");
  if (parts.length !== 2) throw new Error(`Invalid CIDR: ${cidr}`);
  const prefix = parseInt(parts[1], 10);
  if (Number.isNaN(prefix) || prefix < 0 || prefix > 32) {
    throw new Error(`Invalid prefix length in: ${cidr}`);
  }
  const ipInt = ipToInt(parts[0]);
  const size = Math.pow(2, 32 - prefix);
  const networkInt = Math.floor(ipInt / size) * size;
  const broadcastInt = networkInt + size - 1;
  return { start: networkInt, end: broadcastInt };
}

export function rangeFromString(str) {
  if (str.includes("/")) return rangeFromCidr(str);
  if (str.includes("-")) {
    const parts = str.split("-");
    if (parts.length !== 2) throw new Error(`Invalid range: ${str}`);
    const start = ipToInt(parts[0].trim());
    const end = ipToInt(parts[1].trim());
    if (start > end) throw new Error(`Range start is after range end: ${str}`);
    return { start, end };
  }
  throw new Error(`Unrecognized range format: ${str} (use CIDR or start-end)`);
}

export function mergeRanges(ranges) {
  if (ranges.length === 0) return [];
  const sorted = [...ranges].sort((a, b) => a.start - b.start);
  const merged = [{ ...sorted[0] }];
  for (let i = 1; i < sorted.length; i++) {
    const next = sorted[i];
    const current = merged[merged.length - 1];
    if (next.start <= current.end + 1) {
      if (next.end > current.end) current.end = next.end;
    } else {
      merged.push({ ...next });
    }
  }
  return merged;
}

export function getFreeRanges(networkRange, excludedRanges) {
  const clipped = [];
  for (const r of excludedRanges) {
    const s = Math.max(r.start, networkRange.start);
    const e = Math.min(r.end, networkRange.end);
    if (s <= e) clipped.push({ start: s, end: e });
  }
  const merged = mergeRanges(clipped);
  const free = [];
  let cursor = networkRange.start;
  for (const ex of merged) {
    if (ex.start > cursor) free.push({ start: cursor, end: ex.start - 1 });
    if (ex.end + 1 > cursor) cursor = ex.end + 1;
  }
  if (cursor <= networkRange.end) free.push({ start: cursor, end: networkRange.end });
  return { free, merged };
}

export function getCidrsFromRange(start, end) {
  const result = [];
  let current = start;
  while (current <= end) {
    const remaining = end - current + 1;
    let prefix = 0;
    let blockSize = Math.pow(2, 32);
    for (prefix = 0; prefix <= 32; prefix++) {
      blockSize = Math.pow(2, 32 - prefix);
      if (current % blockSize === 0 && blockSize <= remaining) break;
    }
    result.push({
      cidr: `${intToIp(current)}/${prefix}`,
      subnetMask: prefixToMask(prefix),
      firstIp: intToIp(current),
      lastIp: intToIp(current + blockSize - 1),
      addresses: blockSize,
      startInt: current,
      endInt: current + blockSize - 1,
    });
    current += blockSize;
  }
  return result;
}

export function findMatchingCidr(ipInt, subnets) {
  for (const s of subnets) {
    if (ipInt >= s.startInt && ipInt <= s.endInt) return s.cidr;
  }
  return null;
}

export function parseLines(text) {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
}

export function formatAddresses(n) {
  return n.toLocaleString("en-US");
}

export const EXAMPLE = {
  network: "10.0.0.0/22",
  excludes: "10.0.0.0/26\n10.0.1.128-10.0.1.200\n10.0.3.0/25",
  checkIps: "10.0.0.10\n10.0.1.5\n10.0.1.150\n10.0.3.200",
};
