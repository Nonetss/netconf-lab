import asyncio
import re

from ..interfaces.kernel import run
from ..state import boot_state


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
    return {
        "success": received > 0,
        "packets-sent": count,
        "packets-received": received,
        "message": "reachable" if received else "no response",
    }


async def reboot_rpc(xpath, input_params, event, private_data):
    if event != "rpc":
        return {}
    delay = int(input_params.get("delay-seconds", 0))
    if delay:
        await asyncio.sleep(delay)
    boot_state.reset()
    return {"accepted": True, "message": "Simulated reboot completed"}
