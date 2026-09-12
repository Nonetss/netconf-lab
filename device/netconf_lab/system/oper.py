import os

from ..state import boot_state


async def system_oper_data(xpath, private_data):
    load = os.getloadavg()[0]
    cpu_count = max(os.cpu_count() or 1, 1)
    meminfo = {}
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            meminfo[key] = int(value.strip().split()[0])
    used = 100.0 * (1.0 - meminfo.get("MemAvailable", 0) / meminfo["MemTotal"])
    return {
        "system": {
            "state": {
                "vendor": "NETCONF Sandbox",
                "model": "Virtual Router SR-NP2",
                "serial-number": "LAB-20260912-001",
                "software-version": "1.0.0",
                "boot-time": boot_state.time_iso(),
                "uptime-seconds": boot_state.uptime_seconds(),
                "cpu-percent": round(min(100.0, load * 100.0 / cpu_count), 1),
                "memory-used-percent": round(used, 1),
            }
        }
    }


async def inventory_oper_data(xpath, private_data):
    return {
        "inventory": {
            "component": [
                {
                    "name": "chassis-0",
                    "class": "chassis",
                    "serial-number": "LAB-20260912-001",
                    "description": "Virtual chassis",
                    "oper-status": "up",
                },
                {
                    "name": "routing-engine-0",
                    "class": "module",
                    "serial-number": "RE-0001",
                    "description": "Virtual control plane",
                    "oper-status": "up",
                },
                {
                    "name": "fan-0",
                    "class": "fan",
                    "serial-number": "FAN-0001",
                    "description": "Virtual cooling",
                    "oper-status": "up",
                },
                {
                    "name": "psu-0",
                    "class": "power-supply",
                    "serial-number": "PSU-0001",
                    "description": "Virtual power supply",
                    "oper-status": "up",
                },
            ]
        }
    }
