"""API do vard-voz. Só 127.0.0.1; guardas de Host/Origin iguais às da ponte (server.py)."""
from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .motor import VOZ
from .normalizar import normalizar

log = logging.getLogger("vard_voz")
MAX_CHARS = 400

# Mesma lista da ponte (4700 + webview do HUD em produção / dev).
ORIGENS_OK = {
    "http://127.0.0.1:4700", "http://localhost:4700",
    "http://tauri.localhost", "http://localhost:1420",
}


_NAO_FORNECIDO = object()


def criar_app(motor=None, motor_kokoro=_NAO_FORNECIDO, carregar_em_thread: bool = True) -> FastAPI:
    if motor is None:
        from .motor import Motor
        motor = Motor(os.environ.get("VARD_VOZ_DEVICE", "cuda"))
    if motor_kokoro is _NAO_FORNECIDO:
        try:
            from .kokoro import MotorKokoro
            motor_kokoro = MotorKokoro(os.environ.get("VARD_VOZ_DEVICE", "cpu"))
        except Exception:
            log.warning("kokoro indisponivel; apenas XTTS ativo")
            motor_kokoro = None

    @asynccontextmanager
    async def vida(app):
        if carregar_em_thread:
            def _carga():
                try:
                    motor.carregar()
                except Exception:
                    log.exception("falha ao carregar o motor XTTS")
                if motor_kokoro is not None:
                    try:
                        motor_kokoro.carregar()
                    except Exception:
                        log.exception("falha ao carregar o motor Kokoro")
            threading.Thread(target=_carga, daemon=True, name="carga-motor").start()
        yield

    app = FastAPI(title="vard-voz", lifespan=vida)

    @app.middleware("http")
    async def so_localhost(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"erro": "Só localhost."}, status_code=421)
        origem = request.headers.get("origin")
        if origem and origem not in ORIGENS_OK:
            return JSONResponse({"erro": "origem_recusada"}, status_code=403)
        return await call_next(request)

    app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGENS_OK), allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.get("/saude")
    def saude():
        kokoro_pronta = motor_kokoro is not None and motor_kokoro.pronta and motor_kokoro.aquecida
        xtts_pronta = motor.pronta and motor.aquecida
        pronta = xtts_pronta or kokoro_pronta
        voz_atual = VOZ if xtts_pronta else (next(iter(VOZES_KOKORO), "") if kokoro_pronta else VOZ)
        device = motor.device if xtts_pronta else (motor_kokoro.device if kokoro_pronta else motor.device)
        return {
            "pronta": pronta,
            "voz": voz_atual,
            "device": device,
            "aquecida": pronta,
            "kokoro": kokoro_pronta,
            "xtts": xtts_pronta,
        }

    @app.get("/vozes")
    def vozes():
        if not motor.pronta and motor_kokoro is None:
            return JSONResponse({"erro": "aquecendo"}, status_code=503)
        lista = list(motor.vozes()) if motor.pronta else []
        if motor_kokoro is not None:
            from .kokoro import VOZES_KOKORO
            for vid in VOZES_KOKORO:
                if vid not in lista:
                    lista.append(vid)
        atual = VOZ if motor.pronta else (next(iter(VOZES_KOKORO), "") if motor_kokoro is not None else "")
        return {"vozes": lista, "atual": atual}

    def _motor_para_voz(voz: str | None):
        """Escolhe o motor adequado para a voz pedida. Kokoro tem prioridade quando a voz é dele."""
        if voz and motor_kokoro is not None:
            from .kokoro import VOZES_KOKORO
            if voz in VOZES_KOKORO:
                if motor_kokoro.pronta and motor_kokoro.aquecida:
                    return motor_kokoro
                return None  # Kokoro pedido mas não pronto → 503
        if motor.pronta and motor.aquecida:
            return motor
        if motor_kokoro is not None and motor_kokoro.pronta and motor_kokoro.aquecida:
            return motor_kokoro
        return None

    @app.post("/falar")
    async def falar(corpo: dict, request: Request, fluxo: int = 0):
        texto = str(corpo.get("texto", "")).strip()
        if not texto or len(texto) > MAX_CHARS:
            return JSONResponse({"erro": "texto_invalido"}, status_code=400)
        try:
            vel = float(corpo.get("velocidade", 1.0))
        except (TypeError, ValueError):
            return JSONResponse({"erro": "velocidade_invalida"}, status_code=400)
        voz = str(corpo.get("voz", "") or "").strip() or None
        alvo = _motor_para_voz(voz)
        if alvo is None:
            return JSONResponse({"erro": "aquecendo"}, status_code=503)
        if voz is not None and not alvo.tem_voz(voz):
            return JSONResponse({"erro": "voz_desconhecida"}, status_code=400)
        texto = normalizar(texto)
        log.info("falar: %d chars motor=%s voz=%s", len(texto), type(alvo).__name__, voz)
        log.debug("falar (normalizado): %s", texto)
        if fluxo or "audio/pcm" in request.headers.get("accept", ""):
            return StreamingResponse(
                alvo.falar_fluxo(texto, vel, voz), media_type="audio/pcm",
                headers={"X-Taxa": "24000", "X-Canais": "1", "X-Formato": "s16le"},
            )
        wav = await run_in_threadpool(alvo.falar, texto, vel, voz)
        return Response(wav, media_type="audio/wav")

    return app
