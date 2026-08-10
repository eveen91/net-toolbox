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
