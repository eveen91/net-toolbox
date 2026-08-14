// Lightweight client-side checks so the form can flag obvious mistakes
// before round-tripping to the backend, which remains the source of truth
// for validation (subnet membership, uniqueness, etc.).

const IPV4_RE = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;

export function looksLikeIPv4(value) {
  const m = IPV4_RE.exec((value || "").trim());
  if (!m) return false;
  return m.slice(1).every((octet) => Number(octet) <= 255);
}

export function looksLikeCidr(value) {
  const parts = (value || "").trim().split("/");
  if (parts.length !== 2) return false;
  const [addr, prefix] = parts;
  const p = Number(prefix);
  if (!Number.isInteger(p) || p < 0 || p > 32) return false;
  return looksLikeIPv4(addr);
}

export function formatVlan(vlan) {
  return vlan === null || vlan === undefined || vlan === "" ? "—" : `VLAN ${vlan}`;
}

export function formatTimestamp(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// Sorts dotted-quad addresses numerically (10.0.0.2 before 10.0.0.10)
// rather than as plain strings.
export function compareAddresses(a, b) {
  const toParts = (ip) => ip.split(".").map(Number);
  const pa = toParts(a);
  const pb = toParts(b);
  for (let i = 0; i < 4; i++) {
    if (pa[i] !== pb[i]) return pa[i] - pb[i];
  }
  return 0;
}

export function utilizationPercent(subnet) {
  if (!subnet || !subnet.totalAddresses) return 0;
  const allocated = subnet.usedCount + subnet.reservedCount;
  return Math.min(100, Math.round((allocated / subnet.totalAddresses) * 100));
}

export const STATUS_LABELS = {
  used: "Used",
  free: "Free",
  reserved: "Reserved",
};

// Groups a flat subnets list (each with a parentId) into a tree. Preserves
// the incoming order (already sorted by network address) within each level.
export function buildSubnetTree(subnets) {
  const byId = new Map(subnets.map((s) => [s.id, { ...s, children: [] }]));
  const roots = [];
  for (const node of byId.values()) {
    if (node.parentId != null && byId.has(node.parentId)) {
      byId.get(node.parentId).children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

// Walks parentId links to build the list of ancestors (top-level first),
// for a breadcrumb above the selected subnet's detail.
export function ancestorChain(subnets, subnetId) {
  const byId = new Map(subnets.map((s) => [s.id, s]));
  const chain = [];
  let current = byId.get(subnetId);
  while (current && current.parentId != null && byId.has(current.parentId)) {
    current = byId.get(current.parentId);
    chain.unshift(current);
  }
  return chain;
}

export function addressesToCsv(addresses) {
  const headers = [
    "address", "status", "hostname", "description",
    "team", "machineType", "vmCluster", "environment", "locked", "updatedAt",
  ];
  const escape = (value) => {
    const str = value === null || value === undefined ? "" : String(value);
    if (/[",\n]/.test(str)) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const rows = addresses.map((addr) =>
    headers.map((h) => escape(addr[h])).join(",")
  );
  return [headers.join(","), ...rows].join("\r\n");
}