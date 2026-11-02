"""Transcrição pelo servidor sherpa-onnx do OpenWhispr (servidor falso local, sem rede externa)."""
from __future__ import annotations

import io
import json
import struct
import threading
import wave

import numpy as np
import pytest
from websockets.sync.server import serve

from vard_voz import modelos_stt
from vard_voz.modelos_stt import OPENWHISPR, GerenciadorModelos
from vard_voz.transcricao import TAXA, MotorSTT


def _wav(segundos: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(TAXA)
        w.writeframes((np.sin(np.arange(int(TAXA * segundos)) / 20) * 8000).astype(np.int16).tobytes())
    return buf.getvalue()


@pytest.fixture
def servidor_falso(monkeypatch):
    recebido: dict = {}

    def tratar(ws):
        msg = ws.recv()
        taxa, n = struct.unpack("<ii", msg[:8])
        recebido.update(taxa=taxa, n=n, amostras=len(msg[8:]) // 4)
        ws.send(json.dumps({"text": " Aurora, que horas são? "}))
        recebido["fim"] = ws.recv()

    srv = serve(tratar, "127.0.0.1", 0)
    porta = srv.socket.getsockname()[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("VARD_STT_OPENWHISPR_URL", f"ws://127.0.0.1:{porta}")
    yield recebido
    srv.shutdown()


def test_transcreve_pelo_openwhispr(servidor_falso) -> None:
    stt = MotorSTT(modelo=OPENWHISPR)
    stt.carregar()
    texto, conf = stt.transcrever_bytes(_wav(0.5))
    assert texto == "Aurora, que horas são?"
    assert conf == 1.0
    assert servidor_falso["taxa"] == TAXA
    assert servidor_falso["n"] == servidor_falso["amostras"] * 4 == TAXA * 2  # 0,5 s em float32
    assert servidor_falso["fim"] == "Done"


def test_openwhispr_fechado_nao_carrega(monkeypatch) -> None:
    monkeypatch.setenv("VARD_STT_OPENWHISPR_URL", "ws://127.0.0.1:1")
    stt = MotorSTT(modelo=OPENWHISPR)
    with pytest.raises(RuntimeError, match="OpenWhispr"):
        stt.carregar()
    assert not stt.pronta


def test_catalogo_trata_openwhispr_como_externo(servidor_falso, tmp_path) -> None:
    g = GerenciadorModelos(cache=tmp_path, baixador=lambda *_: pytest.fail("não baixa nada"), em_thread=False)
    assert g.baixado(OPENWHISPR) is True
    assert g.baixar(OPENWHISPR)["estado"] == "concluido"
    (tmp_path / "models--").mkdir()  # o que um repo vazio apontaria: não pode ser apagado
    g.apagar(OPENWHISPR)
    assert (tmp_path / "models--").exists()
    assert any(m["id"] == OPENWHISPR for m in g.listar())
    assert modelos_stt.POR_ID[OPENWHISPR].tamanho_mb == 0
