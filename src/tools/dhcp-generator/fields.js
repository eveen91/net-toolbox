// Adapted from dhcp-tool/frontend/src/components/workspace-controls.tsx.
// Same generator-facing keys; labels follow net::toolbox's interface language.
export const globalFields = [
  { key: 'domain', label: 'Domain', max: 253 },
  { key: 'dns', label: 'DNS servers', help: '1–3 IPv4 addresses, separated by commas. Blank inherits or omits the option.' },
  { key: 'default_lease_time', label: 'Default lease (seconds)', type: 'number' },
  { key: 'max_lease_time', label: 'Maximum lease (seconds)', type: 'number' },
];
export const subnetFields = [
  { key: 'cidr', label: 'Subnet CIDR', max: 18, required: true },
  { key: 'gateway', label: 'Gateway IPv4', max: 15 },
  { key: 'interface_address', label: 'Interface IPv4 addresses', help: 'Cluster member addresses / VIP, separated by commas or spaces. Excluded from pools and reservations.' },
  ...globalFields,
];

export const splitAddresses = value => Array.isArray(value) ? value : String(value || '').split(/[\s,]+/).filter(Boolean);
function options(source) {
  const result = {};
  for (const field of globalFields) {
    const value = source[field.key];
    if (value == null || String(value).trim() === '') continue;
    result[field.key] = field.type === 'number' ? Number(value) : field.key === 'dns' ? splitAddresses(value) : String(value).trim();
  }
  return result;
}
export function toConfiguration(draft) {
  return { firewall: String(draft.firewall || '').trim(), profile: draft.profile, ...options(draft), subnets: (draft.subnets || []).map(subnet => ({
    cidr: String(subnet.cidr || '').trim(), active: subnet.active !== false, ...options(subnet),
    ...(String(subnet.gateway || '').trim() ? { gateway: subnet.gateway.trim() } : {}),
    ...(splitAddresses(subnet.interface_address).length ? { interface_address: splitAddresses(subnet.interface_address) } : {}),
    gaia_host_name_fallback: Boolean(subnet.gaia_host_name_fallback),
    pools: (subnet.pools || []).map(pool => ({ start: String(pool.start || '').trim(), end: String(pool.end || '').trim(), active: pool.active !== false })),
    reservations: (subnet.reservations || []).map(row => ({ id: String(row.id || '').trim(), mac: String(row.mac || '').trim(), ip: String(row.ip || '').trim(), active: row.active !== false })),
  })) };
}
export const emptyConfiguration = () => ({ firewall: '', profile: 'R81.10', subnets: [] });
export const emptySubnet = () => ({ cidr: '', active: true, pools: [], reservations: [] });
