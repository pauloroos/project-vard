"""python -m vard_voz: sobe o serviço em 127.0.0.1:VARD_VOZ_PORT (4710)."""
import logging
import os

import uvicorn

from .servidor import criar_app


def main() -> None:
    logging.basicConfig(level=logging.DEBUG if os.environ.get("VARD_VOZ_DEBUG") else logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(criar_app(), host="127.0.0.1", port=int(os.environ.get("VARD_VOZ_PORT", "4710")), log_level="info")


if __name__ == "__main__":
    main()
