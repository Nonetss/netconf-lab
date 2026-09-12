import logging

import sysrepo  # pyright: ignore[reportMissingImports] -- solo existe dentro de la imagen Netopeer2


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s device-plugin: %(message)s")
    sysrepo.configure_logging(py_logging=True)
