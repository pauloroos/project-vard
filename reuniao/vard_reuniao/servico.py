"""API do vard-reuniao em 127.0.0.1:4720. Só localhost, sem CORS, recusa qualquer Origin (ninguém chama por página)."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import armazenamento as arm
from . import config, diarizacao
from .sessao import Sessao

log = logging.getLogger("vard_reuniao.servico")
VERSAO = "0.1.0"
PASTA_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}(-[0-9]+)?")


class CorpoDiarizar(BaseModel):
    pasta: str


class CorpoFalante(BaseModel):
    pasta: str
    n: int = Field(ge=1)
    nome: str = Field(min_length=1, max_length=60)


def criar_app(sessao: Sessao | None = None, *, raiz: Path = arm.RAIZ, diarizacao_estado=None, carregar_vad: bool = False) -> FastAPI:
    """Carga preguiçosa (0.9.4 leve): o modelo VAD só é carregado quando a primeira reunião
    começa, não no arranque do serviço. `carregar_vad=True` mantém o comportamento antigo
    para testes que dependem dele."""
    raiz = Path(raiz)
    if sessao is None:
        sessao = Sessao(config.carregar(), raiz=raiz)
        if carregar_vad:
            sessao.precarregar()
    diarizacao_estado = diarizacao_estado or diarizacao.estado
    try:        # nenhuma sessão existe ainda: toda reunião sem fim é de um serviço que caiu
        conf = getattr(sessao, "conf", None) or config.carregar()
        arm.fechar_orfas(raiz, getattr(sessao, "agora", dt.datetime.now)(), guardar_audio=conf.guardar_audio, apagar_audio_horas=conf.apagar_audio_horas)
    except Exception:  # noqa: BLE001
        log.exception("fechar reuniões órfãs")
    app = FastAPI(title="vard-reuniao")
    app.state.sessao = sessao

    @app.middleware("http")
    async def so_localhost(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"erro": "Só localhost."}, status_code=421)
        if request.headers.get("origin") is not None:
            return JSONResponse({"erro": "origem_recusada"}, status_code=403)
        return await call_next(request)

    @app.get("/status")
    def status():
        return {**sessao.status(), "versao": VERSAO, "diarizacao": diarizacao_estado(),
                "offline": os.environ.get("HF_HUB_OFFLINE") == "1",
                "telemetria_desligada": os.environ.get("PYANNOTE_METRICS_ENABLED") == "0"}

    @app.post("/iniciar")
    def iniciar():
        r = sessao.iniciar()
        return JSONResponse(r, status_code=200 if r.get("ok") else (409 if r.get("erro") == "ja_ativa" else 500))

    @app.post("/encerrar")
    def encerrar():
        r = sessao.encerrar()
        return JSONResponse(r, status_code=200 if r.get("ok") else 409)

    @app.get("/lista")
    def lista(n: int = 10):
        n = max(1, min(int(n), 200))
        return [{"pasta": r.pasta, "inicio": r.inicio, "fim": r.fim, "duracao_s": r.duracao_s, "ata": r.ata,
                 "relatorio": r.relatorio, "diarizada": r.diarizada} for r in arm.listar(raiz, n)]

    def _pasta(nome: str) -> Path | None:
        if not PASTA_RE.fullmatch(nome):
            return None
        p = raiz / nome
        return p if (p / "reuniao.json").is_file() else None

    @app.get("/reuniao/{pasta}")
    def reuniao(pasta: str):
        p = _pasta(pasta)
        if p is None:
            return JSONResponse({"erro": "nao_encontrada"}, status_code=404)
        r = arm.Reuniao.carregar(p)
        return {**asdict(r), "falas": [asdict(f) for f in arm.Transcricao(p).falas()]}

    @app.post("/diarizar")
    def diarizar(corpo: CorpoDiarizar):
        p = _pasta(corpo.pasta)
        if p is None:
            return JSONResponse({"erro": "nao_encontrada"}, status_code=404)
        if p.name == sessao.status().get("pasta"):
            return JSONResponse({"ok": False, "erro": "ativa"}, status_code=409)    # áudio incompleto e transcrição viva
        est = diarizacao_estado()
        if not est.get("pronta"):
            return JSONResponse({"erro": "indisponivel", "motivo": est.get("motivo") or diarizacao.MOTIVO_AUSENTE}, status_code=503)
        r = sessao.diarizar_pasta_em_thread(p.name)
        return JSONResponse(r, status_code=202 if r.get("ok") else 409)

    @app.post("/falante")
    def falante(corpo: CorpoFalante):
        p = _pasta(corpo.pasta)
        if p is None:
            return JSONResponse({"erro": "nao_encontrada"}, status_code=404)
        arq = p / "falantes.json"
        try:
            falantes = {str(k): str(v) for k, v in json.loads(arq.read_text(encoding="utf-8")).items()}
        except (OSError, ValueError, AttributeError):
            falantes = {}
        falantes[str(corpo.n)] = corpo.nome.strip()
        arq.write_text(json.dumps(falantes, ensure_ascii=False, indent=1), encoding="utf-8")
        arm.Transcricao(p).reescrever(falantes)
        return {"ok": True, "falantes": falantes}

    return app
