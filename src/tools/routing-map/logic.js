// Parses pasted routing-table text into { hosts, warnings }.
//
// Format — one or more host blocks, each starting with "@hostname",
// followed by its routes as "network -> next hop" (or "network,next hop"),
// with an optional interface as a third field:
//
//   @web01
//   10.0.1.0/24 -> 10.0.1.1
//   10.0.2.0/24 -> 10.0.1.1, eth0
//   0.0.0.0/0 -> 10.0.1.254
//
//   @web02
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
      current = { host: name, routes: [] };
      hosts.push(current);
      return;
    }

    if (!current) {
      warnings.push(`Line ${lineNo}: "${line}" found before any "@hostname" line — skipped`);
      return;
    }

    const match = line.match(ROUTE_RE);
    if (!match) {
      warnings.push(`Line ${lineNo}: could not parse "${line}" as "network -> next hop"`);
      return;
    }

    current.routes.push({ network: match[1], nextHop: normalizeNextHop(match[2]), interface: match[3] || "" });
  });

  return { hosts, warnings };
}

// One "@host" block of text for a single host's routes.
export function formatHostBlock(host, routes) {
  const lines = routes.map((r) => {
    const iface = r.interface ? `, ${r.interface}` : "";
    return `${r.network} -> ${denormalizeNextHop(r.nextHop)}${iface}`;
  });
  return [`@${host}`, ...lines].join("\n");
}

// Turns [{host, routes:[{network, nextHop, interface}]}] (the shape the
// backend returns) back into the "@host / network -> next hop" text format,
// so saved data can be loaded back into the editable textarea.
export function serializeHosts(hosts) {
  return hosts.map((h) => formatHostBlock(h.host, h.routes)).join("\n\n");
}

// Merges one host's parsed routes into the draft text — replacing that
// host's block if it's already there, appending a new one otherwise.
// Used by the device-output importer so re-importing the same host
// overwrites rather than duplicates it in the draft.
export function upsertHost(rawText, host, routes) {
  const { hosts } = parseRoutingData(rawText);
  const idx = hosts.findIndex((h) => h.host === host);
  if (idx >= 0) {
    hosts[idx] = { host, routes };
  } else {
    hosts.push({ host, routes });
  }
  return serializeHosts(hosts);
}

// ---------------------------------------------------------------------------
// Device output interpreter — parses CLI "show route" output (tested against
// a Brocade/Ruckus-style routing table) into { host, routes, warnings }.
//
// Handles lines like:
//   S    10.1.0.0/16      via 10.226.20.5, eth4.355, cost 0, age 4627970
//   C    10.226.0.64/26   is directly connected, eth1
// and picks the device name off a CLI prompt on the first line, e.g.
//   rzdc1>show route
//
// Any line without a recognizable network/prefix (legend, banners, blank
// lines, annotation lines) is silently ignored rather than treated as an
// error — those make up most of this kind of output.
// ---------------------------------------------------------------------------

const PROMPT_RE = /^([A-Za-z0-9_.-]+)>/;
const CIDR_RE = /\b(\d{1,3}(?:\.\d{1,3}){3}\/\d{1,2})\b/;
const CONNECTED_RE = /directly connected,?\s*(\S+)/i;
const VIA_RE = /via\s+(\S+?),\s*(\S+)/i;

export function parseDeviceRouteOutput(text) {
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

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const lineNo = idx + 1;
    if (!line) return;

    const cidrMatch = line.match(CIDR_RE);
    if (!cidrMatch) return; // legend / header / annotation line — not an error, just skip
    const network = cidrMatch[1];

    const connectedMatch = line.match(CONNECTED_RE);
    if (connectedMatch) {
      routes.push({ network, nextHop: "directly connected", interface: connectedMatch[1].replace(/,$/, "") });
      return;
    }

    const viaMatch = line.match(VIA_RE);
    if (viaMatch) {
      routes.push({ network, nextHop: viaMatch[1], interface: viaMatch[2].replace(/,$/, "") });
      return;
    }

    warnings.push(
      `Line ${lineNo}: found network ${network} but no "via <next hop>" or "directly connected" — skipped`
    );
  });

  if (!host) {
    warnings.push('Couldn\'t detect a device name from the first line — using "unknown-device". Rename it by editing the draft\'s "@" line.');
    host = "unknown-device";
  }

  return { host, routes, warnings };
}

export const EXAMPLE_DEVICE_OUTPUT = `rzdc1>show route
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

export const EXAMPLE = `@web01
10.0.1.0/24 -> 10.0.1.1
10.0.2.0/24 -> 10.0.1.254
0.0.0.0/0 -> 10.0.1.254

@web02
10.0.2.0/24 -> 10.0.2.1
10.0.1.0/24 -> 10.0.2.254
0.0.0.0/0 -> 10.0.2.254

@dc01
10.0.0.0/16 -> 10.0.0.1
0.0.0.0/0 -> 10.0.0.254`;

