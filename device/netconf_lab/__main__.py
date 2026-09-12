import asyncio
import logging
import signal
import sys

import sysrepo  # pyright: ignore[reportMissingImports] -- solo existe dentro de la imagen Netopeer2

from .interfaces.kernel import reconcile_loop
from .logging_conf import setup_logging
from .subscriptions import register


def main():
    setup_logging()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        with sysrepo.SysrepoConnection() as conn, conn.start_session() as sess:
            register(sess, conn)
            loop.run_until_complete(reconcile_loop(conn, stop_event))
        return 0
    except Exception:
        logging.exception("El plugin terminó inesperadamente")
        return 1
    finally:
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
