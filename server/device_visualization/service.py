"""Identity-aware configuration reconciliation and removal previews."""

def proposals(config, current=None):
    from .repository import Missing, Invalid
    old = current or {}
    if config.deviceType != 'server':
        existing = {g['family']: g for g in old.get('portGroups',[])}
        return [{'id':existing.get(g.family,{}).get('id'),'kind':'family','slot':None,'name':None,**g.model_dump()} for g in config.portGroups]
    existing = {g['id']:g for g in old.get('networkCards',[])}
    result=[]
    for card in config.networkCards:
        if card.id is not None:
            if card.id not in existing:
                raise Missing()
            if card.slotNumber != existing[card.id]['slotNumber']:
                raise Invalid('An existing network card cannot change its physical slot')
        result.append({'kind':'nic','slot':card.slotNumber,**card.model_dump()})
    return result


def preview_data(current, proposed):
    by_id={g['id']:g for g in proposed if g['id'] is not None}
    removed=[p for p in current['ports'] if p['groupId'] not in by_id or
             p['family']!=by_id[p['groupId']]['family'] or p['number']>by_id[p['groupId']]['count']]
    return {'deviceId':current['id'],'version':current['version'],
            'removedCardCount':sum(g['id'] not in by_id for g in current.get('networkCards',[])),
            'removedConfiguredPortCount':sum(bool(p.get('portMode')) for p in removed),
            'removedPortCount':len(removed),'removedAssignedPortCount':sum(bool(p['leadsTo']) for p in removed),
            'removedLabelledPortCount':sum(bool(p['label']) for p in removed),'removedPorts':removed}


def execute(operation, *args, **kwargs):
    # Persistence keeps the lock/version/audit transaction together.
    from . import repository
    return getattr(repository, operation)(*args, **kwargs)
