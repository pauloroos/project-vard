"""O patch local do OpenJarvis (allowed_chat_ids do Telegram) precisa estar aplicado."""
from pathlib import Path

import ast
import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from types import SimpleNamespace

import pytest

RAIZ_OJ = Path(os.environ.get("VARD_TESTE_OPENJARVIS_SRC", "checkout-ficticio"))
ARQ = RAIZ_OJ / "src/openjarvis/system/_channel_kwargs.py"


@pytest.mark.pc_real
def test_telegram_repassa_allowed_chat_ids():
    assert 'kw["allowed_chat_ids"]' in ARQ.read_text(encoding="utf-8")


ARQ_EXTRA = RAIZ_OJ / "src/openjarvis/engine/_openai_compat.py"


@pytest.mark.pc_real
def test_chat_extra_aplicado_nos_tres_payloads():
    texto = ARQ_EXTRA.read_text(encoding="utf-8")
    assert "OPENJARVIS_CHAT_EXTRA" in texto and texto.count("**_chat_extra(),") == 3


CANAL = ARQ.parents[1] / "channels" / "telegram.py"
PATCH_MARCA = Path(__file__).resolve().parents[2] / "scripts" / "openjarvis" / "patches" / "openjarvis-telegram-marca.patch"


@pytest.mark.pc_real
@pytest.mark.parametrize("caso", ["permitido", "negado", "sem_variavel", "falha_escrita"])
def test_patch_marca_so_mensagem_aceita_sem_derrubar_canal(tmp_path, monkeypatch, caso):
    clone = CANAL.parents[3]
    rel = "src/openjarvis/channels/telegram.py"
    original = subprocess.run(["git", "-C", str(clone), "show", f"HEAD:{rel}"],
                              check=True, capture_output=True).stdout
    copia = tmp_path / rel
    copia.parent.mkdir(parents=True)
    copia.write_bytes(original)
    assert PATCH_MARCA.exists(), "o patch da marca precisa ser distribuído"
    subprocess.run(["git", "apply", "--check", str(PATCH_MARCA)], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "apply", str(PATCH_MARCA)], cwd=tmp_path, check=True, capture_output=True)
    arvore = ast.parse(copia.read_text(encoding="utf-8"))
    # Executa o callback real e o helper do patch, sem iniciar polling nem carregar o núcleo.
    funcoes = [n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name in ("_vard_marcar_telegram", "_handle_msg")]
    marca = tmp_path / "ultimo-telegram.json"
    if caso == "sem_variavel":
        monkeypatch.delenv("VARD_MARCA_TELEGRAM", raising=False)
    else:
        monkeypatch.setenv("VARD_MARCA_TELEGRAM", str(tmp_path if caso == "falha_escrita" else marca))
    trocas = []
    if caso == "permitido":
        marca.write_text('{"ts": 1}', encoding="utf-8")
        substituir = os.replace

        def substituir_atomico(origem, destino):
            assert json.loads(marca.read_text(encoding="utf-8")) == {"ts": 1}
            assert json.loads(Path(origem).read_text(encoding="utf-8"))["ts"] >= antes
            trocas.append((origem, destino))
            substituir(origem, destino)

        monkeypatch.setattr(os, "replace", substituir_atomico)
    recebidas = []
    def receber(cm):
        if caso == "permitido":
            assert marca.exists(), "a origem precisa ser gravada antes de entregar ao agente"
        recebidas.append(cm)
    canal = SimpleNamespace(_allowed_chat_ids="42", _handlers=[receber], _bus=None)
    ambiente = dict(os=os, json=json, time=time, tempfile=tempfile, Path=Path, logger=logging.getLogger(__name__),
                    self=canal, ChannelMessage=SimpleNamespace)
    exec(compile(ast.Module(body=funcoes, type_ignores=[]), str(copia), "exec"), ambiente)
    msg = SimpleNamespace(from_user=None, text="data de hoje", message_id=1,
                          chat=SimpleNamespace(id=99 if caso == "negado" else 42))
    antes = time.time()
    asyncio.run(ambiente["_handle_msg"](SimpleNamespace(message=msg), None))
    assert len(recebidas) == (0 if caso == "negado" else 1)
    if caso == "permitido":
        dados = json.loads(marca.read_text(encoding="utf-8"))
        assert set(dados) == {"ts"} and antes <= dados["ts"] <= time.time()
        assert len(trocas) == 1
    else:
        assert not marca.exists()
    assert not list(tmp_path.glob("*.tmp"))
