#!/usr/bin/env python3
import asyncio
import datetime as dt
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import sysrepo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s device-plugin: %(message)s")
sysrepo.configure_logging(py_logging=True)
BOOT_MONOTONIC = time.monotonic()
BOOT_TIME = dt.datetime.now(dt.timezone.utc)
ALLOWED_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,14}$")
PROTECTED = {"eth0", "lo"}

def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)

def find_key(mapping, suffix, default=None):
    if not isinstance(mapping, dict):
        return default
    for key, value in mapping.items():
        if key.split(":")[-1] == suffix:
            return value
    return default

def configured_interfaces(conn):
    with conn.start_session("running") as sess:
        try:
            data = sess.get_data("/ietf-interfaces:interfaces")
        except sysrepo.SysrepoNotFoundError:
            return []
    root_data = find_key(data, "interfaces", {})
    return find_key(root_data, "interface", []) or []

def reconcile_kernel(conn):
    for interface in configured_interfaces(conn):
        name = interface.get("name", "")
        if name in PROTECTED or not ALLOWED_NAME.fullmatch(name):
            continue
        exists = run("ip", "link", "show", "dev", name, check=False).returncode == 0
        if not exists:
            run("ip", "link", "add", name, "type", "dummy")
        ipv4 = find_key(interface, "ipv4", {}) or {}
        mtu = ipv4.get("mtu")
        if mtu:
            run("ip", "link", "set", "dev", name, "mtu", str(mtu))
        run("ip", "-4", "address", "flush", "dev", name)
        if ipv4.get("enabled", True):
            for address in ipv4.get("address", []):
                ip = address.get("ip")
                prefix = address.get("prefix-length")
                if ip is not None and prefix is not None:
                    run("ip", "address", "add", f"{ip}/{prefix}", "dev", name)
        run("ip", "link", "set", "dev", name, "up" if interface.get("enabled", True) else "down")

def link_snapshot():
    result = run("ip", "-j", "-s", "link", "show")
    return {item["ifname"]: item for item in json.loads(result.stdout)}

async def interface_oper_data(xpath, private_data):
    conn = private_data
    links = link_snapshot()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    output = []
    for config in configured_interfaces(conn):
        name = config.get("name")
        link = links.get(name, {})
        flags = link.get("flags", [])
        enabled = config.get("enabled", True)
        stats = link.get("stats64") or link.get("stats") or {}
        rx, tx = stats.get("rx", {}), stats.get("tx", {})
        output.append({
            "name": name,
            "admin-status": "up" if enabled else "down",
            "oper-status": "up" if "UP" in flags else ("down" if link else "not-present"),
            "last-change": now,
            "if-index": int(link.get("ifindex", 1)),
            "phys-address": link.get("address", "00:00:00:00:00:00"),
            "speed": 10000000000 if name == "lo0" else 1000000000,
            "statistics": {
                "discontinuity-time": BOOT_TIME.isoformat(timespec="seconds"),
                "in-octets": int(rx.get("bytes", 0)),
                "in-unicast-pkts": int(rx.get("packets", 0)),
                "in-discards": int(rx.get("dropped", 0)),
                "in-errors": int(rx.get("errors", 0)),
                "out-octets": int(tx.get("bytes", 0)),
                "out-unicast-pkts": int(tx.get("packets", 0)),
                "out-discards": int(tx.get("dropped", 0)),
                "out-errors": int(tx.get("errors", 0)),
            },
        })
    return {"interfaces": {"interface": output}}

async def system_oper_data(xpath, private_data):
    load = os.getloadavg()[0]
    cpu_count = max(os.cpu_count() or 1, 1)
    meminfo = {}
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            meminfo[key] = int(value.strip().split()[0])
    used = 100.0 * (1.0 - meminfo.get("MemAvailable", 0) / meminfo["MemTotal"])
    return {"system": {"state": {
        "vendor": "NETCONF Sandbox", "model": "Virtual Router SR-NP2",
        "serial-number": "LAB-20260912-001", "software-version": "1.0.0",
        "boot-time": BOOT_TIME.isoformat(timespec="seconds"),
        "uptime-seconds": int(time.monotonic() - BOOT_MONOTONIC),
        "cpu-percent": round(min(100.0, load * 100.0 / cpu_count), 1),
        "memory-used-percent": round(used, 1),
    }}}

async def inventory_oper_data(xpath, private_data):
    return {"inventory": {"component": [
        {"name": "chassis-0", "class": "chassis", "serial-number": "LAB-20260912-001", "description": "Virtual chassis", "oper-status": "up"},
        {"name": "routing-engine-0", "class": "module", "serial-number": "RE-0001", "description": "Virtual control plane", "oper-status": "up"},
        {"name": "fan-0", "class": "fan", "serial-number": "FAN-0001", "description": "Virtual cooling", "oper-status": "up"},
        {"name": "psu-0", "class": "power-supply", "serial-number": "PSU-0001", "description": "Virtual power supply", "oper-status": "up"},
    ]}}

async def module_change_cb(event, req_id, changes, private_data):
    if event == "done":
        logging.info("Configuración aplicada en %s (request-id=%s)", private_data, req_id)
    await asyncio.sleep(0)

async def ping_rpc(xpath, input_params, event, private_data):
    if event != "rpc":
        return {}
    destination = input_params["destination"]
    count = int(input_params.get("count", 3))
    result = run("ping", "-n", "-c", str(count), "-W", "1", destination, check=False)
    received = 0
    match = re.search(r"(\d+) packets transmitted, (\d+) received", result.stdout)
    if match:
        received = int(match.group(2))
    return {"success": received > 0, "packets-sent": count, "packets-received": received,
            "message": "reachable" if received else "no response"}

async def reboot_rpc(xpath, input_params, event, private_data):
    global BOOT_MONOTONIC, BOOT_TIME
    if event != "rpc":
        return {}
    delay = int(input_params.get("delay-seconds", 0))
    if delay:
        await asyncio.sleep(delay)
    BOOT_MONOTONIC = time.monotonic()
    BOOT_TIME = dt.datetime.now(dt.timezone.utc)
    return {"accepted": True, "message": "Simulated reboot completed"}

async def reconcile_loop(conn, stop_event):
    while not stop_event.is_set():
        try:
            reconcile_kernel(conn)
        except Exception:
            logging.exception("Error reconciliando interfaces Linux")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        with sysrepo.SysrepoConnection() as conn:
            with conn.start_session() as sess:
                sess.subscribe_module_change("ietf-interfaces", None, module_change_cb, private_data="ietf-interfaces", asyncio_register=True)
                sess.subscribe_module_change("sandbox-device", None, module_change_cb, private_data="sandbox-device", asyncio_register=True)
                sess.subscribe_oper_data_request("ietf-interfaces", "/ietf-interfaces:interfaces/interface", interface_oper_data, private_data=conn, asyncio_register=True, strict=True)
                sess.subscribe_oper_data_request("sandbox-device", "/sandbox-device:system/state", system_oper_data, asyncio_register=True, strict=True)
                sess.subscribe_oper_data_request("sandbox-device", "/sandbox-device:inventory", inventory_oper_data, asyncio_register=True, strict=True)
                sess.subscribe_rpc_call("/sandbox-device:ping", ping_rpc, asyncio_register=True)
                sess.subscribe_rpc_call("/sandbox-device:reboot", reboot_rpc, asyncio_register=True)
                loop.run_until_complete(reconcile_loop(conn, stop_event))
        return 0
    except Exception:
        logging.exception("El plugin terminó inesperadamente")
        return 1
    finally:
        loop.close()

if __name__ == "__main__":
    sys.exit(main())
