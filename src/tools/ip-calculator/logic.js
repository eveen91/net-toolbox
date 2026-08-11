// Core IP-calculator logic — given an IPv4 address and a netmask (dotted,
// prefix-length, or wildcard), works out every standard network detail:
// network/broadcast address, usable host range, wildcard mask, binary
// layout, classful designation, and whether the address is in a
// special-use (private / loopback / link-local / multicast) range.
//
// Kept free of any React/UI concerns so it can be tested on its own.

export function ipToInt(ip) {
  if (typeof ip !== "string") throw new Error("IP address must be a string");
  const trimmed = ip.trim();
  const parts = trimmed.split(".");
  if (parts.length !== 4) throw new Error(`Invalid IP address: "${ip}" (expected 4 dot-separated octets)`);
  const nums = parts.map((p) => {
    if (!/^\d{1,3}$/.test(p)) throw new Error(`Invalid IP address: "${ip}"`);
    const n = parseInt(p, 10);
    if (n > 255) throw new Error(`Invalid IP address: "${ip}" (octet "${p}" is out of range)`);
    return n;
  });
  return ((nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3]) >>> 0;
}

export function intToIp(int) {
  return [(int >>> 24) & 0xff, (int >>> 16) & 0xff, (int >>> 8) & 0xff, int & 0xff].join(".");
}

export function prefixToMaskInt(prefix) {
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    throw new Error(`Invalid prefix length: /${prefix} (must be 0-32)`);
  }
  const hostBits = 32 - prefix;
  return hostBits === 32 ? 0 : (0xffffffff << hostBits) >>> 0;
}

export function prefixToMask(prefix) {
  return intToIp(prefixToMaskInt(prefix));
}

// Converts a dotted-decimal subnet mask (e.g. "255.255.255.0") to its
// prefix length. Rejects non-contiguous masks (e.g. "255.0.255.0") — a
// valid subnet mask is always a run of 1 bits followed by a run of 0 bits.
export function maskToPrefix(mask) {
  const maskInt = ipToInt(mask);
  // A contiguous 1-run mask, when inverted, is always (2^n - 1) for some n
  // (all the 0 bits become 1s, filling in from the bottom) — including 0
  // itself (n=0, i.e. a /32 mask). That's the cheapest way to check
  // "leading 1s then trailing 0s, no gaps" without walking bit-by-bit.
  const inverted = ~maskInt >>> 0;
  const isContiguous = (inverted & (inverted + 1)) === 0;
  if (!isContiguous) {
    throw new Error(`"${mask}" is not a valid subnet mask (bits must be contiguous)`);
  }
  let prefix = 32;
  let n = inverted;
  while (n > 0) {
    prefix--;
    n >>>= 1;
  }
  return prefix;
}

// Accepts a netmask in any of the forms the tool's input allows:
//   "24"              -> prefix length
//   "/24"             -> prefix length
//   "255.255.255.0"   -> dotted subnet mask
//   "0.0.0.255"       -> dotted wildcard mask (inverse of a subnet mask)
// Returns the prefix length, or throws with a message naming what was
// actually wrong (rather than folding every case into one generic error).
export function parseNetmaskInput(input) {
  if (typeof input !== "string") throw new Error("Netmask must be a string");
  const trimmed = input.trim();
  if (!trimmed) throw new Error("Enter a netmask (e.g. 24, /24, or 255.255.255.0)");

  if (/^\/?\d{1,2}$/.test(trimmed)) {
    const prefix = parseInt(trimmed.replace("/", ""), 10);
    if (prefix < 0 || prefix > 32) throw new Error(`Prefix length /${prefix} is out of range (0-32)`);
    return prefix;
  }

  if (trimmed.includes(".")) {
    try {
      return maskToPrefix(trimmed);
    } catch {
      // Not a valid subnet mask — try it as a wildcard mask instead
      // (a wildcard is just the bitwise inverse of a subnet mask).
    }
    const wildcardInt = ipToInt(trimmed);
    const asMaskInt = ~wildcardInt >>> 0;
    try {
      return maskToPrefix(intToIp(asMaskInt));
    } catch {
      throw new Error(`"${input}" isn't a valid subnet mask or wildcard mask`);
    }
  }

  throw new Error(`"${input}" isn't a recognized netmask — use a prefix length (24) or dotted mask (255.255.255.0)`);
}

export function toBinaryOctets(int) {
  return [(int >>> 24) & 0xff, (int >>> 16) & 0xff, (int >>> 8) & 0xff, int & 0xff]
    .map((b) => b.toString(2).padStart(8, "0"))
    .join(".");
}

// Traditional classful designation (A-E). Informational only — real-world
// routing has been classless (CIDR) since the 90s, but people still ask
// "what class is this address" often enough that it's worth showing.
export function classify(ipInt) {
  const firstOctet = (ipInt >>> 24) & 0xff;
  if (firstOctet < 128) return "A";
  if (firstOctet < 192) return "B";
  if (firstOctet < 224) return "C";
  if (firstOctet < 240) return "D (multicast)";
  return "E (reserved)";
}

// Special-use ranges worth calling out (RFC 1918 private space, loopback,
// link-local/APIPA, multicast, and the all-ones broadcast address). An
// address can only be in one of these at a time, so first match wins.
const SPECIAL_RANGES = [
  { label: "Private (RFC 1918)", cidr: "10.0.0.0/8" },
  { label: "Private (RFC 1918)", cidr: "172.16.0.0/12" },
  { label: "Private (RFC 1918)", cidr: "192.168.0.0/16" },
  { label: "Loopback", cidr: "127.0.0.0/8" },
  { label: "Link-local (APIPA)", cidr: "169.254.0.0/16" },
  { label: "Carrier-grade NAT (RFC 6598)", cidr: "100.64.0.0/10" },
  { label: "Multicast", cidr: "224.0.0.0/4" },
  { label: "Reserved (Class E)", cidr: "240.0.0.0/4" },
  { label: "Limited broadcast", cidr: "255.255.255.255/32" },
];

export function specialUse(ipInt) {
  for (const { label, cidr } of SPECIAL_RANGES) {
    const [addr, prefixStr] = cidr.split("/");
    const prefix = parseInt(prefixStr, 10);
    const maskInt = prefixToMaskInt(prefix);
    if ((ipToInt(addr) & maskInt) === (ipInt & maskInt)) return label;
  }
  return null;
}

// Splits a combined "ip/prefix" (or "ip/dotted-mask") input like
// "192.168.1.130/24" into its two parts. `netmask` is null when the input
// has no "/", so callers can fall back to a separately entered netmask
// field rather than treating the absence as an error themselves.
export function splitCombinedInput(input) {
  if (typeof input !== "string") return { ip: input, netmask: null };
  const idx = input.indexOf("/");
  if (idx === -1) return { ip: input.trim(), netmask: null };
  return { ip: input.slice(0, idx).trim(), netmask: input.slice(idx + 1).trim() };
}

// Same as calculate(), but accepts the IP field either as a bare address
// ("192.168.1.130", paired with a separate netmask input) or as a combined
// "address/prefix" or "address/dotted-mask" CIDR-style value
// ("192.168.1.130/24") — in which case the suffix after "/" is used as the
// netmask and the separate netmask field is ignored. This is the form the
// UI calls; calculate() itself still expects the two apart.
export function calculateFromInputs(ipInput, netmaskInput) {
  const { ip, netmask: netmaskFromIp } = splitCombinedInput(ipInput);
  if (!ip) throw new Error("Enter an IPv4 address, e.g. 192.168.1.130 or 192.168.1.130/24");
  const effectiveNetmask = netmaskFromIp !== null ? netmaskFromIp : netmaskInput;
  if (!effectiveNetmask || !effectiveNetmask.trim()) {
    throw new Error(
      "Enter a netmask (e.g. 24, /24, 255.255.255.0), or include it in the IP field as 192.168.1.130/24"
    );
  }
  return calculate(ip, effectiveNetmask);
}

// Full network calculation for a given IP + prefix length. /31 (RFC 3021
// point-to-point) has no network/broadcast distinction — both addresses are
// usable hosts. /32 is a single host with no usable range at all.
export function calculate(ipStr, netmaskStr) {
  const ipInt = ipToInt(ipStr);
  const prefix = parseNetmaskInput(netmaskStr);
  const maskInt = prefixToMaskInt(prefix);
  const wildcardInt = ~maskInt >>> 0;

  const networkInt = (ipInt & maskInt) >>> 0;
  const broadcastInt = prefix === 32 ? ipInt : (networkInt | wildcardInt) >>> 0;

  const isPointToPoint = prefix === 31;
  const isSingleHost = prefix === 32;
  const hasHostRange = !isPointToPoint && !isSingleHost;

  const firstHostInt = isPointToPoint ? networkInt : hasHostRange ? (networkInt + 1) >>> 0 : networkInt;
  const lastHostInt = isPointToPoint ? broadcastInt : hasHostRange ? (broadcastInt - 1) >>> 0 : broadcastInt;

  const totalAddresses = Math.pow(2, 32 - prefix);
  const usableHosts = isPointToPoint ? 2 : isSingleHost ? 1 : Math.max(0, totalAddresses - 2);

  return {
    inputIp: intToIp(ipInt),
    inputIpInt: ipInt,
    prefix,
    cidr: `${intToIp(networkInt)}/${prefix}`,
    subnetMask: intToIp(maskInt),
    wildcardMask: intToIp(wildcardInt),
    networkAddress: intToIp(networkInt),
    networkAddressInt: networkInt,
    broadcastAddress: intToIp(broadcastInt),
    broadcastAddressInt: broadcastInt,
    firstHost: intToIp(firstHostInt),
    lastHost: intToIp(lastHostInt),
    totalAddresses,
    usableHosts,
    hasHostRange,
    isPointToPoint,
    isSingleHost,
    ipClass: classify(ipInt),
    specialUse: specialUse(ipInt),
    isPrivate: specialUse(ipInt) === "Private (RFC 1918)",
    binary: {
      ip: toBinaryOctets(ipInt),
      mask: toBinaryOctets(maskInt),
      network: toBinaryOctets(networkInt),
      broadcast: toBinaryOctets(broadcastInt),
    },
  };
}

export const EXAMPLE = {
  ip: "192.168.1.130",
  netmask: "255.255.255.192",
};