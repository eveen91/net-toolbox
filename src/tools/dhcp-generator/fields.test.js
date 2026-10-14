import { describe, expect, it } from 'vitest';
import { toConfiguration, splitAddresses } from './fields.js';
describe('DHCP editor serialization', () => {
  it('preserves inactive entries and converts editable options to generator types', () => {
    const result = toConfiguration({ firewall: ' fw-lab ', profile: 'R82.10', dns: '192.0.2.2, 192.0.2.3', default_lease_time: '3600', domain: '', subnets: [{ cidr: '192.0.2.0/24', interface_address: '192.0.2.1 192.0.2.4', active: false, pools: [{ start: '192.0.2.10', end: '192.0.2.20', active: false }], reservations: [{ id: ' printer ', mac: '00:11:22:33:44:55', ip: '192.0.2.30', active: false }] }] });
    expect(result.firewall).toBe('fw-lab');
    expect(result.default_lease_time).toBe(3600);
    expect(result.dns).toEqual(['192.0.2.2', '192.0.2.3']);
    expect(result).not.toHaveProperty('domain');
    expect(result.subnets[0].interface_address).toEqual(['192.0.2.1', '192.0.2.4']);
    expect(result.subnets[0].active).toBe(false);
    expect(result.subnets[0].pools[0].active).toBe(false);
    expect(result.subnets[0].reservations[0]).toEqual({ id: 'printer', mac: '00:11:22:33:44:55', ip: '192.0.2.30', active: false });
  });
  it('retains inherited options and address arrays from imported snapshots', () => {
    expect(splitAddresses(['192.0.2.1'])).toEqual(['192.0.2.1']);
    const result = toConfiguration({ firewall: 'fw', profile: 'R81.10', subnets: [{ cidr: '192.0.2.0/24', dns: ['192.0.2.2'], max_lease_time: '', pools: [], reservations: [] }] });
    expect(result.subnets[0].dns).toEqual(['192.0.2.2']);
    expect(result.subnets[0]).not.toHaveProperty('max_lease_time');
    expect(result.subnets[0].pools).toEqual([]);
  });
});
