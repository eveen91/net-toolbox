from typing import Literal

PortNaming = Literal['family', 'unit-slot-port', 'unit-zero-port', 'unit-port', 'port']


def port_name(device, family, number, ordinal):
    naming=device['port_naming'] if device['device_type']=='switch' else 'family'
    if naming=='unit-slot-port':
        return f"{device['port_unit']}/{device['port_slot']}/{ordinal}"
    if naming=='unit-zero-port':
        return f"{device['port_unit']}/0/{ordinal}"
    if naming=='unit-port':
        return f"{device['port_unit']}/{ordinal}"
    if naming=='port':
        return str(ordinal)
    return f"{ {'ethernet':'Eth','sfp':'SFP','qsfp':'QSFP'}[family]} {number}"
