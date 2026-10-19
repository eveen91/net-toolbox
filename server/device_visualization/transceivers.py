"""Documented per-socket modules, independent of the physical SFP cage."""
MODULES={'sfp-1g':('sfp',1),'sfp-10g':('sfp',10),'sfp28-25g':('sfp',25),'rj45-1g':('ethernet',1)}


def effective(family,speed,module):
    return MODULES[module] if module else (family,speed)
