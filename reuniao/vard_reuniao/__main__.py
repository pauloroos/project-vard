"""python -m vard_reuniao: sobe o serviço em 127.0.0.1:VARD_REUNIAO_PORT (4720)."""
import logging
import os
import sys
import threading
import time

from .config import pasta_dados

# Antes de qualquer import de torch/pyannote/huggingface: nada de rede, nada de telemetria.
_LOCAL = pasta_dados()
os.environ["PYANNOTE_METRICS_ENABLED"] = "0"      # forçado: a telemetria do pyannote manda metadados para otel.pyannote.ai
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HOME", str(_LOCAL / "modelos" / "hf"))

import uvicorn  # noqa: E402

log = logging.getLogger("vard_reuniao")


def _log() -> None:
    pasta = _LOCAL / "logs"
    pasta.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
        handlers=[logging.FileHandler(pasta / "reuniao.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def _vigiar_dispositivos(sessao) -> None:
    while True:
        time.sleep(5)
        try:
            sessao.verificar_dispositivos()
        except Exception:  # noqa: BLE001
            log.exception("verificar_dispositivos")


def main() -> None:
    _log()
    from .servico import criar_app

    app = criar_app()
    threading.Thread(target=_vigiar_dispositivos, args=(app.state.sessao,), daemon=True, name="vigia-dispositivos").start()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("VARD_REUNIAO_PORT", "4720")), log_level="info")


if __name__ == "__main__":
    main()
