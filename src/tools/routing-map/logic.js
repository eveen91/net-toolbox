// Parses pasted routing-table text into { hosts, warnings }.
//
// Format — one or more host blocks, each starting with "@hostname",
// followed by its interfaces (%name cidr [- description]) and
// routes as "network -> next hop" (or "network,next hop"):
//
//   @web01
//   %eth0 10.0.1.5/24 - primary interface
//   10.0.1.0/24 -> 10.0.1.1
//   0.0.0.0/0 -> 10.0.1.254
//
//   @web02
//   %eth0 10.0.2.5/24
//   10.0.2.0/24 -> 10.0.2.1
//
// Blank lines and lines starting with "#" are ignored. Malformed lines are
// skipped and reported in `warnings` rather than aborting the whole parse.

const ROUTE_RE = /^(\S+)\s*(?:->|,)\s*(\S+)$/;

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
      const name = parts[0];
      const ipAddress = parts[1];
      current.interfaces.push({ name, ipAddress, description: desc || null });
      return;
    }

    const match = line.match(ROUTE_RE);
    if (!match) {
      warnings.push(`Line ${lineNo}: could not parse "${line}" as "network -> next hop" or "%interface cidr"`);
      return;
    }

    current.routes.push({ network: match[1], nextHop: match[2] });
  });

  return { hosts, warnings };
}

// Turns [{host, routes:[...], interfaces:[...]}] back into the
// "@host / %interface / network -> next hop" text format.
export function serializeHosts(hosts) {
  return hosts
    .map((h) => {
      const lines = [`@${h.host}`];
      (h.interfaces || []).forEach((i) => {
        let line = `%${i.name} ${i.ipAddress}`;
        if (i.description) {
          line += ` - ${i.description}`;
        }
        lines.push(line);
      });
      (h.routes || []).forEach((r) => {
        lines.push(`${r.network} -> ${r.nextHop}`);
      });
      return lines.join("\n");
    })
    .join("\n\n");
}

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
