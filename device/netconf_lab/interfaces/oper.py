import datetime as dt

from ..state import boot_state
from .kernel import configured_interfaces, link_snapshot


async def interface_oper_data(xpath, private_data):
    conn = private_data
    links = link_snapshot()
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    output = []
    for config in configured_interfaces(conn):
        name = config.get("name")
        link = links.get(name, {})
        flags = link.get("flags", [])
        enabled = config.get("enabled", True)
        stats = link.get("stats64") or link.get("stats") or {}
        rx, tx = stats.get("rx", {}), stats.get("tx", {})
        output.append(
            {
                "name": name,
                "admin-status": "up" if enabled else "down",
                "oper-status": "up" if "UP" in flags else ("down" if link else "not-present"),
                "last-change": now,
                "if-index": int(link.get("ifindex", 1)),
                "phys-address": link.get("address", "00:00:00:00:00:00"),
                "speed": 10000000000 if name == "lo0" else 1000000000,
                "statistics": {
                    "discontinuity-time": boot_state.time_iso(),
                    "in-octets": int(rx.get("bytes", 0)),
                    "in-unicast-pkts": int(rx.get("packets", 0)),
                    "in-discards": int(rx.get("dropped", 0)),
                    "in-errors": int(rx.get("errors", 0)),
                    "out-octets": int(tx.get("bytes", 0)),
                    "out-unicast-pkts": int(tx.get("packets", 0)),
                    "out-discards": int(tx.get("dropped", 0)),
                    "out-errors": int(tx.get("errors", 0)),
                },
            }
        )
    return {"interfaces": {"interface": output}}
