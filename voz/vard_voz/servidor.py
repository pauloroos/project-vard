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


def criar_app(motor=None, carregar_em_thread: bool = True) -> FastAPI:
    if motor is None:
        from .motor import Motor
        motor = Motor(os.environ.get("VARD_VOZ_DEVICE", "cuda"))

    @asynccontextmanager
    async def vida(app):
        if carregar_em_thread:
            def _carga():
                try:
                    motor.carregar()
                except Exception:
                    log.exception("falha ao carregar o motor")
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
        return {"pronta": bool(motor.pronta), "voz": VOZ, "device": motor.device, "aquecida": bool(motor.aquecida)}

    @app.get("/vozes")
    def vozes():
        if not motor.pronta:
            return JSONResponse({"erro": "aquecendo"}, status_code=503)
        return {"vozes": motor.vozes(), "atual": VOZ}

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
        if not (motor.pronta and motor.aquecida):
            return JSONResponse({"erro": "aquecendo"}, status_code=503)
        if voz is not None and not motor.tem_voz(voz):
            return JSONResponse({"erro": "voz_desconhecida"}, status_code=400)
        texto = normalizar(texto)
        log.info("falar: %d chars", len(texto))
        log.debug("falar (normalizado): %s", texto)
        if fluxo or "audio/pcm" in request.headers.get("accept", ""):
            return StreamingResponse(
                motor.falar_fluxo(texto, vel, voz), media_type="audio/pcm",
                headers={"X-Taxa": "24000", "X-Canais": "1", "X-Formato": "s16le"},
            )
        wav = await run_in_threadpool(motor.falar, texto, vel, voz)
        return Response(wav, media_type="audio/wav")

    return app
