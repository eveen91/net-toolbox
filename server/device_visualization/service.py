"""Identity-aware configuration reconciliation and removal previews."""

def proposals(config, current=None):
    result = data_proposals(config, current)
    enabled = config.managementPort if current is None or "managementPort" in config.model_fields_set else current["managementPort"]
    if enabled:
        controllers = ('A', 'B') if config.deviceType == 'storage' else (None,)
        for controller in controllers:
            existing = next((p['groupId'] for p in (current or {}).get('ports', []) if p['isManagement'] and p.get('controller') == controller), None)
            result.append({'id': existing, 'kind': 'family', 'slot': None, 'name': 'MGMT', 'family': 'ethernet', 'groupKey': f'mgmt-{controller}' if controller else 'mgmt', 'count': 1, 'speedGbps': 1})
    return result


def data_proposals(config, current=None):
    from .repository import Missing, Invalid
    if config.deviceType == 'cable-management':
        return []
    old = current or {}
    if config.deviceType not in ('server', 'storage'):
        existing = {g['family']: g for g in old.get('portGroups',[])}
        return [{'id':existing.get(g.family,{}).get('id'),'kind':'family','slot':None,'name':None,**g.model_dump()} for g in config.portGroups]
    existing = {g['id']:g for g in old.get('networkCards',[])}
    result=[]
    for card in config.networkCards:
        if card.id is not None:
            if card.id not in existing:
                raise Missing()
            if card.slotNumber != existing[card.id]['slotNumber'] or card.controller != existing[card.id].get('controller'):
                raise Invalid('An existing network card cannot change its physical slot')
        slot = card.slotNumber + (8 if card.controller == 'B' else 0)
        result.append({'kind':'nic','slot':slot,**card.model_dump()})
    return result


def preview_data(current, proposed):
    by_id={g['id']:g for g in proposed if g['id'] is not None}
    removed=[p for p in current['ports'] if p['groupId'] not in by_id or
             p['family']!=by_id[p['groupId']]['family'] or p['number']>by_id[p['groupId']]['count']]
    return {'deviceId':current['id'],'version':current['version'],
            'removedCardCount':sum(g['id'] not in by_id for g in current.get('networkCards',[])),
            'removedConfiguredPortCount':sum(bool(p.get('portMode') or p.get('ipAddress') or p.get('connectionId') or p.get('transceiver')) for p in removed),
            'removedPortCount':len(removed),'removedAssignedPortCount':sum(bool(p['leadsTo']) for p in removed),
            'removedLabelledPortCount':sum(bool(p['label']) for p in removed),'removedPorts':removed}


def execute(operation, *args, **kwargs):
    # Persistence keeps the lock/version/audit transaction together.
    from . import repository
    return getattr(repository, operation)(*args, **kwargs)
