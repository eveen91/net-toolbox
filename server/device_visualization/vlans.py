import re


def normalize_trunk(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Allowed VLANs must be a list, ranges or all')
    value=value.strip().lower()
    if not value:
        return None
    if value=='all':
        return 'all'
    if len(value)>2000:
        raise ValueError('Allowed VLAN list is too long')
    vlans=set()
    for token in value.split(','):
        token=token.strip()
        if not re.fullmatch(r'[0-9]+(?:\s*-\s*[0-9]+)?',token):
            raise ValueError('Use VLAN IDs, comma-separated ranges or all')
        ends=[int(n.strip()) for n in token.split('-')]
        start,end=ends[0],ends[-1]
        if not 1<=start<=end<=4094:
            raise ValueError('VLAN IDs and ranges must be from 1 to 4094')
        vlans.update(range(start,end+1))
    groups=[]
    for vlan in sorted(vlans):
        if groups and vlan==groups[-1][1]+1:groups[-1][1]=vlan
        else:groups.append([vlan,vlan])
    return ','.join(str(a) if a==b else f'{a}-{b}' for a,b in groups)
