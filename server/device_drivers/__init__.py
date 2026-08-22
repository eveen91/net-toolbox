from . import cisco_ios
from . import aruba_cx
from . import checkpoint_gaia

DRIVERS = {
    "cisco_ios": cisco_ios,
    "aruba_aoscx": aruba_cx,
    "checkpoint_gaia": checkpoint_gaia,
}


def get_driver(device_type):
    if device_type not in DRIVERS:
        raise ValueError(f"Unknown device_type: {device_type}")
    return DRIVERS[device_type]
