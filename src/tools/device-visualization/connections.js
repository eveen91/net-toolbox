import { FAMILY_NAMES } from './logic.js';

export const isAppliance = device => ['router', 'firewall', 'storage', 'storage-shelf', 'server'].includes(device?.deviceType);
export const hasDocumentation = port => !!(port.ipAddress || port.portMode || port.leadsTo || port.label);
export function vlanDescription(port) {
  if (port.portMode === 'access') return `Access VLAN ${port.accessVlan}`;
  if (port.portMode === 'trunk') return `Trunk ${port.trunkVlans}${port.nativeVlan ? ` · Native ${port.nativeVlan}` : ''}`;
  return '';
}
export function connectionPorts(ports, query = '', scope = 'documented', controller = 'all', cardId = 'all') {
  const needle = query.trim().toLowerCase();
  return ports.filter(port => (controller==='all'||port.controller===controller) && (cardId==='all'||String(port.groupId)===cardId) && (scope === 'all' || (scope === 'management' ? port.isManagement : hasDocumentation(port))) &&
    [port.name, port.cardName, port.label, port.ipAddress, port.leadsTo, FAMILY_NAMES[port.family], vlanDescription(port), port.isManagement ? 'mgmt management' : '']
      .some(value => (value || '').toLowerCase().includes(needle)))
    .sort((a, b) => (a.controller||'').localeCompare(b.controller||'') || Number(!!b.isManagement) - Number(!!a.isManagement));
}

export function networkCardTitle(port,cards) {
  if(port.isManagement)return 'Management';
  const card=cards.find(card=>card.id===port.groupId);
  return `NIC ${port.slotNumber}${card?.name?` · ${card.name}`:''}`;
}
