// Parses pasted routing-table text into { hosts, warnings }.
//
// Format — one or more host blocks, each starting with "@hostname",
// followed by its interfaces (%name cidr [- description]) and
// routes as "network -> next hop" (or "network,next hop"),
// with an optional egress interface as a third field:
//
//   @web01
//   %eth0 10.0.1.5/24 - primary interface
//   10.0.1.0/24 -> 10.0.1.1
//   10.0.2.0/24 -> 10.0.1.1, eth0
//   0.0.0.0/0 -> 10.0.1.254
//
//   @web02
//   %eth0 10.0.2.5/24
//   10.0.2.0/24 -> 10.0.2.1
//
// Blank lines and lines starting with "#" are ignored. Malformed lines are
// skipped and reported in `warnings` rather than aborting the whole parse.

const ROUTE_RE = /^(\S+)\s*(?:->|,)\s*(\S+)(?:\s*(?:->|,)\s*(\S+))?$/;

// "directly connected" has a space in it, but the draft format's next-hop
// field is a single token — so the draft uses the compact "directly-connected"
// spelling, and we translate to/from the space-separated form (the one the
// backend validates and stores) at the parse/serialize boundary.
const DIRECT_TOKEN = "directly-connected";
const DIRECT_PHRASE = "directly connected";

function normalizeNextHop(token) {
  return token.toLowerCase() === DIRECT_TOKEN ? DIRECT_PHRASE : token;
}

function denormalizeNextHop(nextHop) {
  return nextHop.toLowerCase() === DIRECT_PHRASE ? DIRECT_TOKEN : nextHop;
}

export function parseRoutingData(text) {
  const lines = text.split("\n");
  const hosts = [];
  const warnings = [];
  let current = null;

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const lineNo = idx + 1;
    if (!line || line.startsWith("#")) return;

    if (line.startsWith("@")) {
      const name = line.slice(1).trim();
      if (!name) {
        warnings.push(`Line ${lineNo}: host name missing after "@"`);
        current = null;
        return;
      }
      current = { host: name, routes: [], interfaces: [] };
      hosts.push(current);
      return;
    }

    if (!current) {
      warnings.push(`Line ${lineNo}: "${line}" found before any "@hostname" line — skipped`);
      return;
    }

    if (line.startsWith("%")) {
      const rest = line.slice(1).trim();
      const dashIdx = rest.indexOf(" - ");
      let mainPart = rest;
      let desc = null;
      if (dashIdx !== -1) {
        mainPart = rest.slice(0, dashIdx).trim();
        desc = rest.slice(dashIdx + 3).trim();
      }
      const parts = mainPart.split(/\s+/);
      if (parts.length < 2) {
        warnings.push(`Line ${lineNo}: could not parse "${line}" as "%name ip/cidr [- description]"`);
        return;
      }
      current.interfaces.push({ name: parts[0], ipAddress: parts[1], description: desc || null });
      return;
    }

    const match = line.match(ROUTE_RE);
    if (!match) {
      warnings.push(`Line ${lineNo}: could not parse "${line}" as "network -> next hop" or "%interface cidr"`);
      return;
    }

    current.routes.push({
      network: match[1],
      nextHop: normalizeNextHop(match[2]),
      interface: match[3] || "",
    });
  });

  return { hosts, warnings };
}

// One "@host" block of text for a single host's interfaces + routes.
export function formatHostBlock(host, routes, interfaces = []) {
  const lines = [`@${host}`];
  for (const i of interfaces || []) {
    let line = `%${i.name} ${i.ipAddress}`;
    if (i.description) line += ` - ${i.description}`;
    lines.push(line);
  }
  for (const r of routes || []) {
    const iface = r.interface ? `, ${r.interface}` : "";
    lines.push(`${r.network} -> ${denormalizeNextHop(r.nextHop)}${iface}`);
  }
  return lines.join("\n");
}

// Turns [{host, routes, interfaces}] (the shape the backend returns) back
// into the "@host / %interface / network -> next hop" text format.
export function serializeHosts(hosts) {
  return hosts.map((h) => formatHostBlock(h.host, h.routes, h.interfaces)).join("\n\n");
}

// Merges one host's parsed routes + interfaces into the draft text —
// replacing that host's block if it's already there, appending otherwise.
// Used by the device-output importer so re-importing the same host
// overwrites rather than duplicates it in the draft.
export function upsertHost(rawText, host, routes, interfaces = []) {
  const { hosts } = parseRoutingData(rawText);
  const idx = hosts.findIndex((h) => h.host === host);
  const entry = { host, routes, interfaces };
  if (idx >= 0) {
    hosts[idx] = entry;
  } else {
    hosts.push(entry);
  }
  return serializeHosts(hosts);
}

// ---------------------------------------------------------------------------
// Device output interpreters — each one turns a specific vendor's CLI output
// into { host, routes, interfaces, warnings }. Add a new vendor by writing
// its parse function + example below, then adding one entry to
// DEVICE_PARSERS at the bottom of this section — the UI's parser selector
// reads that list, nothing else needs to change.
// ---------------------------------------------------------------------------

const PROMPT_RE = /^([A-Za-z0-9_.-]+)>/; // Checkpoint-style: "rzdc1>show route"
const ARUBA_PROMPT_RE = /^([A-Za-z0-9_.-]+)#/; // Aruba-style: "switch01# show ip route"
const CIDR_RE = /\b(\d{1,3}(?:\.\d{1,3}){3}\/\d{1,2})\b/;
const CIDR_FULL_RE = /^\d{1,3}(?:\.\d{1,3}){3}\/\d{1,2}$/;

function cleanIface(raw) {
  return raw.replace(/,$/, "");
}

// Given a network in CIDR form ("10.226.0.64/26"), returns the first usable
// host address in that network, keeping the same "/prefix" suffix
// ("10.226.0.65/26"). Used when a connected route's network is recorded as
// an interface address — the network address itself isn't assignable to an
// interface, so we want ".1" (the first host), not ".0".
// For /31 and /32 there's no separate "network address" vs. "host address"
// distinction, so the address is returned unchanged.
function firstUsableAddress(cidr) {
  const [addr, prefixStr] = cidr.split("/");
  const prefix = parseInt(prefixStr, 10);
  if (!addr || Number.isNaN(prefix) || prefix >= 31) return cidr;

  const octets = addr.split(".").map(Number);
  if (octets.length !== 4 || octets.some((o) => Number.isNaN(o))) return cidr;

  let asInt = ((octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]) >>> 0;
  const hostBits = 32 - prefix;
  const mask = hostBits === 32 ? 0 : (0xffffffff << hostBits) >>> 0;
  const networkInt = (asInt & mask) >>> 0;
  const firstHostInt = (networkInt + 1) >>> 0;

  const firstHost = [
    (firstHostInt >>> 24) & 0xff,
    (firstHostInt >>> 16) & 0xff,
    (firstHostInt >>> 8) & 0xff,
    firstHostInt & 0xff,
  ].join(".");

  return `${firstHost}/${prefix}`;
}

// Given an address in CIDR form ("10.226.0.65/26"), returns a string key
// identifying the network it belongs to ("10.226.0.64/26") — the address
// masked down to its network address, paired with the prefix length so
// e.g. a /24 and a /25 that happen to share a network address are still
// treated as different networks. Two interfaces are "on the same network"
// exactly when this key matches. Returns null for anything unparseable.
// Used by the Network Visualization graph to decide which hosts to draw
// an edge between.
export function networkKeyForCidr(cidr) {
  if (typeof cidr !== "string") return null;
  const parts = cidr.split("/");
  if (parts.length !== 2) return null;
  const prefix = parseInt(parts[1], 10);
  if (Number.isNaN(prefix) || prefix < 0 || prefix > 32) return null;

  const octets = parts[0].split(".").map(Number);
  if (octets.length !== 4 || octets.some((o) => Number.isNaN(o) || o < 0 || o > 255)) return null;

  const asInt = ((octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]) >>> 0;
  const hostBits = 32 - prefix;
  const mask = hostBits === 32 ? 0 : (0xffffffff << hostBits) >>> 0;
  const networkInt = (asInt & mask) >>> 0;

  const networkAddr = [
    (networkInt >>> 24) & 0xff,
    (networkInt >>> 16) & 0xff,
    (networkInt >>> 8) & 0xff,
    networkInt & 0xff,
  ].join(".");

  return `${networkAddr}/${prefix}`;
}

// ---- Checkpoint (Gaia) — "show route" -------------------------------------
//
// Handles lines like:
//   S    10.1.0.0/16      via 10.226.20.5, eth4.355, cost 0, age 4627970
//   C    10.226.0.64/26   is directly connected, eth1
// and picks the device name off a CLI prompt on the first line, e.g.
//   rzdc1>show route
//
// Connected (C) lines become both a route (next hop = "directly connected")
// and an interface entry (name = eth1, address = the connected CIDR).
//
// Any line without a recognizable network/prefix (legend, banners, blank
// lines, annotation lines) is silently ignored rather than treated as an
// error — those make up most of this kind of output.

const CONNECTED_RE = /directly connected(?:\s+to)?,?\s+(\S+)/i;
const VIA_RE = /via\s+(\S+?),\s*(\S+)/i;

export function parseCheckpointRouteOutput(text) {
  const lines = text.split("\n");
  const warnings = [];
  let host = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const promptMatch = line.match(PROMPT_RE);
    if (promptMatch) host = promptMatch[1];
    break; // only the first non-empty line is checked for a prompt
  }

  const routes = [];
  const interfaces = [];
  const seenIfaces = new Set();

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const lineNo = idx + 1;
    if (!line) return;

    const cidrMatch = line.match(CIDR_RE);
    if (!cidrMatch) return; // legend / header / annotation line — not an error, just skip
    const network = cidrMatch[1];

    const connectedMatch = line.match(CONNECTED_RE);
    if (connectedMatch) {
      const iface = cleanIface(connectedMatch[1]);
      routes.push({ network, nextHop: "directly connected", interface: iface });
      if (iface && !seenIfaces.has(iface)) {
        seenIfaces.add(iface);
        interfaces.push({ name: iface, ipAddress: firstUsableAddress(network), description: null });
      }
      return;
    }

    const viaMatch = line.match(VIA_RE);
    if (viaMatch) {
      routes.push({ network, nextHop: viaMatch[1], interface: cleanIface(viaMatch[2]) });
      return;
    }

    warnings.push(
      `Line ${lineNo}: found network ${network} but no "via <next hop>" or "directly connected" — skipped`
    );
  });

  if (!host) {
    warnings.push(
      'Couldn\'t detect a device name from the first line — using "unknown-device". Rename it by editing the draft\'s "@" line.'
    );
    host = "unknown-device";
  }

  return { host, routes, interfaces, warnings };
}

export const EXAMPLE_CHECKPOINT_OUTPUT = `rzdc1>show route
Codes: C - Connected, S - Static, R - RIP, B - BGP (D - Default),
       O - OSPF IntraArea (IA - InterArea, E - External, N - NSSA),
       A - Aggregate, K - Kernel Remnant, H - Hidden, P - Suppressed,
       NP - NAT Pool, U - Unreachable, i - Inactive

S               10.1.0.0/16         via 10.226.20.5, eth4.355, cost 0, age 4627970
S               10.2.0.0/16         via 10.226.2.70, eth2.307, cost 0, age 4627970
S               10.6.113.135/32     via 10.226.2.70, eth2.307, cost 0, age 4627970
                                        Ergo ip blacklist
C               10.226.0.64/26      is directly connected, eth1
C               10.226.0.192/26     is directly connected, eth1.301
C               10.226.1.0/26       is directly connected, eth1.302
S               10.226.8.0/21       via 10.226.20.5, eth4.355, cost 0, age 4627972`;

// ---- Aruba switch (ArubaOS-Switch / ProVision) — "show ip route" ----------
//
// Handles lines like:
//   0.0.0.0/0        10.117.7.254   10    static               1       1
//   10.117.5.0/24     Clients       20    connected            1       0
//   127.0.0.1/32       lo0                connected            1       0
//   127.0.0.0/8         reject            static               0       0
// and picks the device name off a CLI prompt on the first line, e.g.
//   switch01# show ip route
//
// Unlike Checkpoint's output, there's no leading route-code letter — each
// route line starts directly with the destination network. The "Gateway"
// column is either a next-hop IP (static/dynamic routes) or the egress
// interface name (VLAN name, "lo0", etc. — for "connected" routes). The
// "VLAN" column (a bare VLAN ID) is optional and only appears on some rows,
// so it's identified positionally, relative to the route-type keyword,
// rather than by a fixed column count. "reject" (null/blackhole) routes
// have no usable next hop and are skipped with a warning instead of being
// recorded as a route.

const ARUBA_TYPE_KEYWORDS = new Set(["static", "connected", "direct", "rip", "ospf", "bgp", "isis", "eigrp"]);

export function parseArubaRouteOutput(text) {
  const lines = text.split("\n");
  const warnings = [];
  let host = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const promptMatch = line.match(ARUBA_PROMPT_RE);
    if (promptMatch) host = promptMatch[1];
    break;
  }

  const routes = [];
  const interfaces = [];
  const seenIfaces = new Set();

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const lineNo = idx + 1;
    if (!line) return;

    const tokens = line.split(/\s+/);
    if (tokens.length < 3 || !CIDR_FULL_RE.test(tokens[0])) return; // header/separator/banner — skip silently
    const network = tokens[0];
    const gateway = tokens[1];

    const typeIdx = tokens.findIndex((t, i) => i >= 2 && ARUBA_TYPE_KEYWORDS.has(t.toLowerCase()));
    if (typeIdx === -1) {
      warnings.push(
        `Line ${lineNo}: found network ${network} but no recognizable route type (static/connected/...) — skipped`
      );
      return;
    }
    const type = tokens[typeIdx].toLowerCase();
    const vlanToken = tokens[typeIdx - 1];
    const vlanId = typeIdx - 1 > 1 && /^\d+$/.test(vlanToken) ? vlanToken : null;

    if (type === "connected" || type === "direct") {
      const iface = gateway;
      routes.push({ network, nextHop: "directly connected", interface: iface });
      if (iface && !seenIfaces.has(iface)) {
        seenIfaces.add(iface);
        interfaces.push({ name: iface, ipAddress: firstUsableAddress(network), description: null });
      }
      return;
    }

    if (gateway.toLowerCase() === "reject") {
      warnings.push(`Line ${lineNo}: ${network} is a null/reject route — skipped (no next hop to record)`);
      return;
    }

    routes.push({ network, nextHop: gateway, interface: vlanId ? `vlan${vlanId}` : "" });
  });

  if (!host) {
    warnings.push(
      'Couldn\'t detect a device name from the first line — using "unknown-device". Rename it by editing the draft\'s "@" line.'
    );
    host = "unknown-device";
  }

  return { host, routes, interfaces, warnings };
}

export const EXAMPLE_ARUBA_OUTPUT = `Aruba-2540-48G-PoEP-4SFPP# show ip route
IP Route Entries

  Destination         Gateway         VLAN  Type       Sub-Type   Metric  Dist.
  ------------------- --------------- ----- ---------- ---------- ------- -----
  0.0.0.0/0            10.117.7.254   10    static                1       1
  10.117.5.0/24        Clients        20    connected             1       0
  10.117.7.0/24        Servers        10    connected             1       0
  127.0.0.0/8          reject               static                0       0
  127.0.0.1/32         lo0                  connected             1       0`;

// ---- Aruba switch (ArubaOS-CX) — "show ip route" --------------------------
//
// A different Aruba product line from the one above (ArubaOS-CX rather than
// ArubaOS-Switch/ProVision) with an entirely different table layout:
//
//   Prefix              Nexthop         Interface  VRF(egress)  Origin/Type  Distance/Metric  Age
//   0.0.0.0/0           10.226.110.1    vlan556     -            S           [1/0]            03m:00w:02d
//   10.226.104.0/24     -               vlan550     -            C           [0/0]            -
//   10.226.104.2/32     -               vlan550     -            L           [0/0]            -
//
// Every data row is a fixed 7 tokens once the header/banner/separator lines
// (identified the same way as the other Aruba parser: no CIDR as the first
// token) are filtered out, so fields are read positionally: prefix, nexthop,
// interface, vrf (unused), origin code, distance/metric (unused), age (unused).
//
// "L" (local) rows are a host route for an interface's own address — these
// don't go into `routes` at all, only into `interfaces`, using the paired
// "C" (connected) row for the same interface to recover the real subnet size
// (an "L" row alone is always a /32, which isn't the interface's actual
// prefix length). "C" rows still become both a route (next hop "directly
// connected") and a fallback interface entry, in case a VLAN has a connected
// route but no local one in the pasted output.

export function parseArubaCxRouteOutput(text) {
  const lines = text.split("\n");
  const warnings = [];
  let host = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const promptMatch = line.match(ARUBA_PROMPT_RE);
    if (promptMatch) host = promptMatch[1];
    break;
  }

  const routes = [];
  const cPrefixByIface = new Map(); // interface -> prefix length, from "C" rows
  const cNetworkByIface = new Map(); // interface -> network, fallback if no "L" row
  const localRows = []; // { hostIp, iface }, from "L" rows

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const lineNo = idx + 1;
    if (!line) return;

    const tokens = line.split(/\s+/);
    if (tokens.length < 5 || !CIDR_FULL_RE.test(tokens[0])) return; // header/separator/banner — skip silently

    const network = tokens[0];
    const nexthop = tokens[1];
    const iface = tokens[2];
    const origin = tokens[4];

    if (origin === "L") {
      localRows.push({ hostIp: network.split("/")[0], iface });
      return;
    }

    if (origin === "C") {
      cPrefixByIface.set(iface, network.split("/")[1]);
      cNetworkByIface.set(iface, network);
      routes.push({ network, nextHop: "directly connected", interface: iface });
      return;
    }

    // Static / dynamic (S, R, B, O, D, or a compound Origin/Type code) — needs a real next hop.
    if (!nexthop || nexthop === "-") {
      warnings.push(`Line ${lineNo}: ${network} (origin "${origin}") has no next hop — skipped`);
      return;
    }
    routes.push({ network, nextHop: nexthop, interface: iface && iface !== "-" ? iface : "" });
  });

  const interfaces = [];
  const seenIfaces = new Set();
  for (const { hostIp, iface } of localRows) {
    if (seenIfaces.has(iface)) continue;
    seenIfaces.add(iface);
    const prefixLen = cPrefixByIface.get(iface);
    interfaces.push({ name: iface, ipAddress: `${hostIp}/${prefixLen || "32"}`, description: null });
  }
  for (const [iface, network] of cNetworkByIface.entries()) {
    if (seenIfaces.has(iface)) continue;
    seenIfaces.add(iface);
    interfaces.push({ name: iface, ipAddress: firstUsableAddress(network), description: null });
  }

  if (!host) {
    warnings.push(
      'Couldn\'t detect a device name from the first line — using "unknown-device". Rename it by editing the draft\'s "@" line.'
    );
    host = "unknown-device";
  }

  return { host, routes, interfaces, warnings };
}

export const EXAMPLE_ARUBA_CX_OUTPUT = `DE-DC-CR-01# show ip route
Displaying ipv4 routes selected for forwarding
Origin Codes: C - connected, S - static, L - local
              R - RIP, B - BGP, O - OSPF, D - DHCP
Type Codes:   E - External BGP, I - Internal BGP, V - VPN, EV - EVPN
              IA - OSPF internal area, E1 - OSPF external type 1
              E2 - OSPF external type 2
VRF: default
Prefix              Nexthop                                  Interface     VRF(egress)       Origin/   Distance/    Age
                                                                                             Type      Metric
--------------------------------------------------------------------------------------------------------
0.0.0.0/0           10.226.110.1                             vlan556       -                 S         [1/0]        03m:00w:02d
10.226.104.0/24     -                                        vlan550       -                 C         [0/0]        -
10.226.104.2/32     -                                        vlan550       -                 L         [0/0]        -
10.226.106.0/24     -                                        vlan552       -                 C         [0/0]        -
10.226.106.2/32     -                                        vlan552       -                 L         [0/0]        -
212.159.53.224/29   10.226.255.89                            vlan703       -                 S         [1/0]        03m:00w:02d`;

// ---- Parser registry — the UI's parser selector reads this list ----------

export const DEVICE_PARSERS = [
  {
    id: "checkpoint",
    label: "Checkpoint (Gaia) — show route",
    parse: parseCheckpointRouteOutput,
    example: EXAMPLE_CHECKPOINT_OUTPUT,
  },
  {
    id: "aruba-provision",
    label: "Aruba Switch (ArubaOS-Switch/ProVision) — show ip route",
    parse: parseArubaRouteOutput,
    example: EXAMPLE_ARUBA_OUTPUT,
  },
  {
    id: "aruba-cx",
    label: "Aruba Switch (ArubaOS-CX) — show ip route",
    parse: parseArubaCxRouteOutput,
    example: EXAMPLE_ARUBA_CX_OUTPUT,
  },
];

// Back-compat aliases — the original names, kept in case anything else
// still imports them directly.
export const parseDeviceRouteOutput = parseCheckpointRouteOutput;
export const EXAMPLE_DEVICE_OUTPUT = EXAMPLE_CHECKPOINT_OUTPUT;

export const EXAMPLE = `@web01
%eth0 10.0.1.5/24 - primary interface
%eth1 10.0.1.6/24
10.0.1.0/24 -> 10.0.1.1
10.0.2.0/24 -> 10.0.1.254
0.0.0.0/0 -> 10.0.1.254

@web02
%eth0 10.0.2.5/24
10.0.2.0/24 -> 10.0.2.1
10.0.1.0/24 -> 10.0.2.254
0.0.0.0/0 -> 10.0.2.254

@dc01
%eth0 10.0.0.5/16 - domain controller
10.0.0.0/16 -> 10.0.0.1
0.0.0.0/0 -> 10.0.0.254`;