import asyncio
import contextlib
import json
import logging
import re
import subprocess

import sysrepo  # pyright: ignore[reportMissingImports] -- solo existe dentro de la imagen Netopeer2

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


async def reconcile_loop(conn, stop_event):
    while not stop_event.is_set():
        try:
            reconcile_kernel(conn)
        except Exception:
            logging.exception("Error reconciliando interfaces Linux")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=2)
