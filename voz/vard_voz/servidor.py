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
from .transcricao import MotorSTT, LIMITE_BYTES

log = logging.getLogger("vard_voz")
MAX_CHARS = 400
LIMITE_UPLOAD_STT = LIMITE_BYTES  # 10 MiB

# Mesma lista da ponte (4700 + webview do HUD em produção / dev).
ORIGENS_OK = {
    "http://127.0.0.1:4700", "http://localhost:4700",
    "http://tauri.localhost", "http://localhost:1420",
}


_NAO_FORNECIDO = object()


class _MotorAusente:
    """Lugar do XTTS quando ele não está disponível: nunca fica pronto e não tem vozes."""

    pronta = False
    aquecida = False
    device = ""

    def carregar(self) -> None:
        return None

    def vozes(self) -> list:
        return []


def _xtts_disponivel() -> bool:
    """XTTS instalado? Pelo registro de pacotes do núcleo quando ele está importável; o serviço de voz
    roda no próprio ambiente (sem o núcleo), e aí decide pelo pacote do XTTS presente (D12)."""
    try:
        from nucleo.vard.pacotes import InstaladorPacotes
    except Exception:
        import importlib.util

        return importlib.util.find_spec("TTS") is not None
    try:
        return InstaladorPacotes().esta_instalado("xtts-v2")
    except Exception:
        return False


def criar_app(
    motor=None,
    motor_kokoro=_NAO_FORNECIDO,
    motor_edge=_NAO_FORNECIDO,
    motor_piper=_NAO_FORNECIDO,
    stt=None,
    carregar_em_thread: bool = True,
) -> FastAPI:
    if motor is None:
        # XTTS só é instanciado se estiver disponível; sem ele, um motor vazio (não pronto)
        # ocupa o lugar e Kokoro/Edge/Piper assumem. Nunca None: o resto do serviço usa motor.pronta.
        if _xtts_disponivel():
            try:
                from .motor import Motor
                # Descarga por ociosidade DESLIGADA por padrão (0): medido em 16/10/2026, a RAM do modelo não volta
                # ao Windows ao descarregar dentro do mesmo processo e a recarga soma outros ~3 GB. Liga com
                # VARD_VOZ_OCIOSO_S quando o XTTS rodar num processo próprio que possa ser encerrado.
                ocioso_s = float(os.environ.get("VARD_VOZ_OCIOSO_S", "0"))
                motor = Motor(os.environ.get("VARD_VOZ_DEVICE", "cuda"), ocioso_s=ocioso_s)
            except Exception:
                log.warning("xtts-v2 instalado mas motor falhou ao iniciar")
        if motor is None:
            motor = _MotorAusente()
    if motor_kokoro is _NAO_FORNECIDO:
        try:
            from .kokoro import MotorKokoro
            motor_kokoro = MotorKokoro(os.environ.get("VARD_VOZ_DEVICE", "cpu"))
        except Exception:
            log.warning("kokoro indisponivel")
            motor_kokoro = None
    if motor_edge is _NAO_FORNECIDO:
        try:
            from .edge import MotorEdge
            motor_edge = MotorEdge()
        except Exception:
            log.warning("edge-tts indisponivel")
            motor_edge = None
    if motor_piper is _NAO_FORNECIDO:
        try:
            from .piper import MotorPiper
            motor_piper = MotorPiper()
        except Exception:
            log.warning("piper-tts indisponivel")
            motor_piper = None
    if stt is None:
        # STT é opcional: só instancia se o extra estiver instalado. Sem ele, /transcribe devolve 503.
        try:
            stt = MotorSTT(
                modelo=os.environ.get("VARD_STT_MODEL", "base"),
                device=os.environ.get("VARD_STT_DEVICE", "cpu"),
                compute_type=os.environ.get("VARD_STT_COMPUTE", "int8"),
            )
        except Exception:
            log.warning("MotorSTT indisponível; /transcribe retornará 503 até instalação do extra stt")
            stt = None

    # Lista de motores opcionais na ordem de prioridade de reserva.
    motores_opcionais = [
        ("kokoro", motor_kokoro),
        ("edge", motor_edge),
        ("piper", motor_piper),
    ]

    @asynccontextmanager
    async def vida(app):
        if carregar_em_thread:
            def _carga():
                try:
                    motor.carregar()
                except Exception:
                    log.exception("falha ao carregar o motor XTTS")
                for nome, m in motores_opcionais:
                    if m is not None:
                        try:
                            m.carregar()
                        except Exception:
                            log.exception("falha ao carregar o motor %s", nome)
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
        # 0.9.4 leve rodada 2: separa "instalado/disponível" de "carregado agora".
        # xtts=true significa que o XTTS está instalado e pode ser carregado sob demanda,
        # mesmo que esteja descarregado no momento. xtts_carregado diz se está na memória agora.
        xtts_instalado = not isinstance(motor, _MotorAusente)
        xtts_carregado = motor.pronta and motor.aquecida
        kokoro_ok = motor_kokoro is not None and motor_kokoro.pronta and motor_kokoro.aquecida
        edge_ok = motor_edge is not None and motor_edge.pronta and motor_edge.aquecida
        piper_ok = motor_piper is not None and motor_piper.pronta and motor_piper.aquecida
        pronta = xtts_carregado or kokoro_ok or edge_ok or piper_ok
        if xtts_carregado:
            voz_atual = VOZ
            device = motor.device
        elif kokoro_ok:
            from .kokoro import VOZES_KOKORO
            voz_atual = next(iter(VOZES_KOKORO), "")
            device = motor_kokoro.device
        elif edge_ok:
            from .edge import VOZES_EDGE_PT_BR
            voz_atual = next(iter(VOZES_EDGE_PT_BR), "")
            device = "cloud"
        elif piper_ok:
            from .piper import VOZES_PIPER_PT_BR
            voz_atual = next(iter(VOZES_PIPER_PT_BR), "")
            device = "cpu"
        else:
            voz_atual = VOZ
            device = motor.device
        return {
            "pronta": pronta,
            "ok": True,
            "pid": os.getpid(),
            "versao": "0.1.0",
            "voz": voz_atual,
            "device": device,
            "aquecida": pronta,
            "xtts": xtts_instalado,
            "xtts_carregado": xtts_carregado,
            "kokoro": kokoro_ok,
            "edge": edge_ok,
            "piper": piper_ok,
        }

    @app.get("/vozes")
    def vozes():
        # 0.9.4 leve rodada 2: lista vozes do XTTS mesmo descarregado (ele está instalado
        # e pode ser recarregado sob demanda). Só devolve 503 se nenhum motor estiver disponível.
        xtts_instalado = not isinstance(motor, _MotorAusente)
        algum_motor_pronto = motor.pronta or any(m is not None and m.pronta for _, m in motores_opcionais)
        if not xtts_instalado and not algum_motor_pronto:
            return JSONResponse({"erro": "aquecendo"}, status_code=503)
        # Lista vozes do XTTS (mesmo descarregado, motor.vozes() devolve pelo menos VOZ)
        lista = list(motor.vozes()) if xtts_instalado else []
        for nome, m in motores_opcionais:
            if m is not None and m.pronta:
                for v in m.vozes():
                    if v not in lista:
                        lista.append(v)
        if motor.pronta:
            atual = VOZ
        elif motor_kokoro is not None and motor_kokoro.pronta:
            from .kokoro import VOZES_KOKORO
            atual = next(iter(VOZES_KOKORO), "")
        elif motor_edge is not None and motor_edge.pronta:
            from .edge import VOZES_EDGE_PT_BR
            atual = next(iter(VOZES_EDGE_PT_BR), "")
        elif motor_piper is not None and motor_piper.pronta:
            from .piper import VOZES_PIPER_PT_BR
            atual = next(iter(VOZES_PIPER_PT_BR), "")
        else:
            atual = ""
        return {"vozes": lista, "atual": atual}

    def _xtts_utilizavel() -> bool:
        """XTTS carregado agora, ou descarregado por ociosidade (já carregou antes): falar() recarrega sozinho."""
        if motor.pronta and motor.aquecida:
            return True
        return not isinstance(motor, _MotorAusente) and bool(getattr(motor, "_nomes", None))

    def _motor_para_voz(voz: str | None):
        """Escolhe o motor adequado para a voz pedida; fallback segue ordem XTTS→Kokoro→Edge→Piper."""
        if voz:
            # Roteamento explícito por ID de voz
            if motor_kokoro is not None:
                from .kokoro import VOZES_KOKORO
                if voz in VOZES_KOKORO:
                    return motor_kokoro if motor_kokoro.pronta and motor_kokoro.aquecida else None
            if motor_edge is not None:
                from .edge import VOZES_EDGE_PT_BR
                if voz in VOZES_EDGE_PT_BR:
                    return motor_edge if motor_edge.pronta and motor_edge.aquecida else None
            if motor_piper is not None:
                from .piper import VOZES_PIPER_PT_BR
                if voz in VOZES_PIPER_PT_BR:
                    return motor_piper if motor_piper.pronta and motor_piper.aquecida else None
            # Voz do XTTS: retorna o motor mesmo que não reconheça a voz,
            # para que /falar valide e devolva 400 (voz_desconhecida) em vez de 503.
            if _xtts_utilizavel():
                return motor
            return None  # Voz pedida mas nenhum motor pronto
        # Sem voz específica: primeiro motor disponível
        if _xtts_utilizavel():
            return motor
        for _, m in motores_opcionais:
            if m is not None and m.pronta and m.aquecida:
                return m
        return None

    @app.post("/v1/speech/transcribe")
    async def transcrever(request: Request):
        """Transcrição STT própria (compatível com OpenJarvis). Requer extra 'stt' instalado."""
        if stt is None or not stt.pronta:
            return JSONResponse({"erro": "stt_indisponivel"}, status_code=503)
        ct = request.headers.get("content-type", "")
        if "multipart/form-data" in ct:
            form = await request.form()
            arquivo = form.get("file")
            if arquivo is None or not hasattr(arquivo, "read"):
                return JSONResponse({"erro": "arquivo_ausente"}, status_code=400)
            audio = await arquivo.read()
        else:
            audio = await request.body()
        if not audio:
            return JSONResponse({"erro": "audio_vazio"}, status_code=400)
        if len(audio) > LIMITE_UPLOAD_STT:
            return JSONResponse({"erro": "audio_grande_demais"}, status_code=413)
        try:
            texto, confianca = await run_in_threadpool(stt.transcrever_bytes, audio)
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        except RuntimeError as exc:
            log.warning("transcrever falhou: %s", exc)
            return JSONResponse({"erro": "stt_falhou"}, status_code=503)
        return {"text": texto, "confidence": confianca}

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
