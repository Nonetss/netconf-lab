import asyncio
import logging

from .interfaces.oper import interface_oper_data
from .system.oper import components_state_oper_data, system_state_oper_data


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
    sess.subscribe_oper_data_request(
        "ietf-interfaces",
        "/ietf-interfaces:interfaces/interface",
        interface_oper_data,
        private_data=conn,
        asyncio_register=True,
        strict=True,
    )
    sess.subscribe_oper_data_request(
        "ietf-system",
        "/ietf-system:system-state",
        system_state_oper_data,
        asyncio_register=True,
        strict=True,
    )
    sess.subscribe_oper_data_request(
        "openconfig-platform",
        "/openconfig-platform:components/component",
        components_state_oper_data,
        private_data=conn,
        asyncio_register=True,
        strict=True,
    )
