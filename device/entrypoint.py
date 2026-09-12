#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

IANA_IF_TYPE_YANG = (
    "/src/sysrepo/modules/subscribed_notifications/iana-if-type@2014-05-08.yang"
)
INIT_FLAG = Path("/etc/sysrepo/.sandbox-initialized")
YAML_TO_JSON = "/opt/sandbox/init/yaml_to_json.py"

ENV = {
    "USER": "root",
    "NP2_MODULE_DIR": "/usr/share/yang/modules/netopeer2",
    "LN2_MODULE_DIR": "/usr/share/yang/modules/libnetconf2",
    "NP2_MODULE_PERMS": "666",
    "NP2_MODULE_OWNER": "root",
    "NP2_MODULE_GROUP": "root",
    "SYSREPOCTL_EXECUTABLE": "/usr/bin/sysrepoctl",
    "SYSREPOCFG_EXECUTABLE": "/usr/bin/sysrepocfg",
}


def run(args, **kwargs):
    kwargs.setdefault("check", True)
    return subprocess.run(args, **kwargs)


def list_modules():
    listing = run(["sysrepoctl", "-l"], check=True, text=True, capture_output=True)
    modules = {}
    for line in listing.stdout.splitlines():
        if "|" not in line or line.lstrip().startswith("Module"):
            continue
        parts = [part.strip() for part in line.split("|")]
        name = parts[0]
        if not name or name.startswith("-"):
            continue
        modules[name] = {
            "flags": parts[2] if len(parts) > 2 else "",
            "features": parts[-1].split() if len(parts) >= 7 else [],
        }
    return modules


def implemented(modules, name):
    return "I" in modules.get(name, {}).get("flags", "")


def install_modules():
    modules = list_modules()
    # ietf-interfaces importa iana-if-type, pero necesitamos que quede
    # implementado para usar identidades como ethernetCsmacd.
    if not implemented(modules, "iana-if-type"):
        run(
            [
                "sysrepoctl",
                "-i",
                IANA_IF_TYPE_YANG,
                "-p",
                "666",
                "-o",
                "root",
                "-g",
                "root",
                "-v2",
            ]
        )
        modules = list_modules()
    features = modules.get("ietf-interfaces", {}).get("features", [])
    for feature in ("arbitrary-names", "pre-provisioning", "if-mib"):
        if feature not in features:
            run(["sysrepoctl", "-c", "ietf-interfaces", "-e", feature, "-v2"])


def load_seed(module, yaml_name):
    yaml_path = Path("/opt/sandbox/init") / yaml_name
    json_path = Path("/tmp") / yaml_path.with_suffix(".json").name
    run(["python3", YAML_TO_JSON, str(yaml_path), str(json_path)])
    run(
        [
            "sysrepocfg",
            f"--edit={json_path}",
            "-d",
            "running",
            "-f",
            "json",
            "-m",
            module,
            "-v2",
        ]
    )
    run(["sysrepocfg", "--copy-from=running", "-d", "startup", "-m", module, "-v2"])
    json_path.unlink(missing_ok=True)


def seed_datastores():
    if INIT_FLAG.exists():
        return
    load_seed("ietf-interfaces", "interfaz/interfaces.yaml")
    INIT_FLAG.touch()


def terminate(procs, *_args):
    for proc in procs:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)


def wait_services(plugin, server):
    procs = (plugin, server)

    def on_signal(signum, frame):
        terminate(procs)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    while plugin.poll() is None and server.poll() is None:
        time.sleep(0.2)
    finished = plugin if plugin.poll() is not None else server
    status = finished.returncode if finished.returncode is not None else 1
    terminate(procs)
    for proc in procs:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    print(f"Un proceso principal terminó con estado {status}", file=sys.stderr)
    return status if status >= 0 else 1


def main():
    os.environ.update(ENV)
    run(["chpasswd"], input="root:netconf\n", text=True)
    ssh_dir = Path("/root/.ssh")
    ssh_dir.mkdir(parents=True, exist_ok=True)
    ssh_dir.chmod(0o700)
    run(["/usr/share/netopeer2/scripts/setup.sh"])
    install_modules()
    run(["/usr/share/netopeer2/scripts/merge_hostkey.sh"])
    run(["/usr/share/netopeer2/scripts/merge_config.sh"])
    seed_datastores()
    plugin = subprocess.Popen(["python3", "-m", "netconf_lab"])
    server = subprocess.Popen(["netopeer2-server", "-d", "-v2"])
    return wait_services(plugin, server)


if __name__ == "__main__":
    sys.exit(main())
