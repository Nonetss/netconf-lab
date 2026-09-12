import asyncio
import logging

from .interfaces.oper import interface_oper_data
from .system.oper import inventory_oper_data, system_oper_data
from .system.rpc import ping_rpc, reboot_rpc


async def module_change_cb(event, req_id, changes, private_data):
    if event == "done":
        logging.info("Configuración aplicada en %s (request-id=%s)", private_data, req_id)
    await asyncio.sleep(0)


def register(sess, conn):
    sess.subscribe_module_change(
        "ietf-interfaces",
        None,
        module_change_cb,
        private_data="ietf-interfaces",
        asyncio_register=True,
    )
    sess.subscribe_module_change(
        "sandbox-device",
        None,
        module_change_cb,
        private_data="sandbox-device",
        asyncio_register=True,
    )
    sess.subscribe_oper_data_request(
        "ietf-interfaces",
        "/ietf-interfaces:interfaces/interface",
        interface_oper_data,
        private_data=conn,
        asyncio_register=True,
        strict=True,
    )
    sess.subscribe_oper_data_request(
        "sandbox-device",
        "/sandbox-device:system/state",
        system_oper_data,
        asyncio_register=True,
        strict=True,
    )
    sess.subscribe_oper_data_request(
        "sandbox-device",
        "/sandbox-device:inventory",
        inventory_oper_data,
        asyncio_register=True,
        strict=True,
    )
    sess.subscribe_rpc_call("/sandbox-device:ping", ping_rpc, asyncio_register=True)
    sess.subscribe_rpc_call("/sandbox-device:reboot", reboot_rpc, asyncio_register=True)
