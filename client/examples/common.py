import os
from ncclient import manager

def connect():
    return manager.connect(
        host=os.getenv("NETCONF_HOST", "device"),
        port=int(os.getenv("NETCONF_PORT", "830")),
        username=os.getenv("NETCONF_USER", "root"),
        password=os.getenv("NETCONF_PASSWORD", "netconf"),
        hostkey_verify=False, allow_agent=False, look_for_keys=False, timeout=15,
    )
