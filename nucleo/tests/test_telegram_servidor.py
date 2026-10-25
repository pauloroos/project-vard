"""Rotas do Telegram no núcleo e o poller que sobe sem OpenJarvis.

O poller real não fala com a rede: processar_updates vira um dublê que só espera.
Token fictício, cofre em memória (cofre_falso) e pastas temporárias.
"""
from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import httpx
import pytest
import tomli_w

from vard import config as cfg_mod
from vard import telegram as tg

TOKEN = "123456789:FICTICIO_token-de-teste_abc"
ALVO = "vard:canal:telegram"


@pytest.fixture
async def nucleo(monkeypatch):
    import server

    chamadas = []

    async def sem_rede(self):
        chamadas.append(self)
        await asyncio.sleep(0.01)
        return 0

    monkeypatch.setattr(tg.TelegramPoller, "processar_updates", sem_rede)
    transporte = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://127.0.0.1") as cliente:
        yield server, cliente, chamadas
    await server._parar_telegram()


@pytest.fixture
def oj(tmp_path, monkeypatch) -> Path:
    casa = tmp_path / "oj-casa"
    casa.mkdir()
    (casa / "config.toml").write_text(tomli_w.dumps({"channel": {"enabled": True, "telegram": {
        "bot_token": TOKEN, "allowed_chat_ids": "111", "parse_mode": "Markdown"}}}), encoding="utf-8")
    monkeypatch.setenv("OPENJARVIS_HOME", str(casa))
    return casa / "config.toml"


async def test_estado_mostra_botao_de_trazer_sem_token(nucleo, oj):
    _, cliente, _ = nucleo
    r = await cliente.get("/telegram")
    j = r.json()
    assert r.status_code == 200
    assert j["token_configurado"] is False and j["ligado"] is False and j["rodando"] is False
    assert j["openjarvis"]["pode_trazer"] is True
    assert TOKEN not in r.text


async def test_trazer_do_openjarvis_liga_o_poller_sem_reiniciar(nucleo, oj, cofre_falso):
    server, cliente, chamadas = nucleo
    r = await cliente.post("/telegram/trazer_openjarvis", json={})
    j = r.json()
    assert j["ok"] is True and j["rodando"] is True
    assert TOKEN not in r.text
    assert cofre_falso[ALVO] == TOKEN
    await asyncio.sleep(0.05)
    assert chamadas, "o poller do Vard começou a ler o bot"
    estado = (await cliente.get("/telegram")).json()
    assert estado["rodando"] is True and estado["token_configurado"] is True
    assert estado["openjarvis"]["ja_migrado"] is True and estado["openjarvis"]["pode_trazer"] is False


async def test_trazer_por_cima_exige_substituir(nucleo, oj, cofre_falso):
    _, cliente, _ = nucleo
    cofre_falso[ALVO] = "555555:OUTRO_token_ficticio"
    tg.gravar_config_telegram({"habilitado": True, "chats_permitidos": ["999"]})
    j = (await cliente.post("/telegram/trazer_openjarvis", json={})).json()
    assert j["ok"] is False and j["motivo"] == "ja_configurado"
    j = (await cliente.post("/telegram/trazer_openjarvis", json={"substituir": True})).json()
    assert j["ok"] is True and cofre_falso[ALVO] == TOKEN


async def test_configurar_desliga_e_religa(nucleo, cofre_falso):
    server, cliente, _ = nucleo
    cofre_falso[ALVO] = TOKEN
    j = (await cliente.post("/telegram/configurar", json={"ligado": True, "chat": "111"})).json()
    assert j == {"ok": True, "rodando": True}
    tarefa = server._telegram["tarefa"]
    assert (await cliente.post("/telegram/sincronizar")).json()["rodando"] is True
    assert server._telegram["tarefa"] is tarefa, "mesma configuração não reinicia o poller"
    j = (await cliente.post("/telegram/configurar", json={"ligado": False})).json()
    assert j == {"ok": True, "rodando": False}
    assert server._telegram["tarefa"] is None
    dados = tomllib.loads(cfg_mod.arquivo_config("telegram.toml").read_text(encoding="utf-8"))
    assert dados["chats_permitidos"] == ["111"] and "token" not in dados


async def test_configurar_recusa_corpo_invalido(nucleo):
    _, cliente, _ = nucleo
    assert (await cliente.post("/telegram/configurar", json={"ligado": "sim"})).status_code == 422


async def test_poller_sobe_so_com_telegram_toml_e_cofre_sem_openjarvis(nucleo, cofre_falso, monkeypatch):
    server, _, _ = nucleo
    monkeypatch.delenv("OPENJARVIS_HOME", raising=False)
    cofre_falso[ALVO] = TOKEN
    tg.gravar_config_telegram({"habilitado": True, "chats_permitidos": ["111"]})
    assert await server._sincronizar_telegram() is True
    tg.gravar_config_telegram({"habilitado": True, "chats_permitidos": []})
    assert await server._sincronizar_telegram() is False


def test_lifespan_usa_a_sincronizacao():
    texto = (Path(__file__).resolve().parent.parent / "server.py").read_text(encoding="utf-8")
    inicio = texto.index("async def lifespan(app):")
    corpo = texto[inicio:texto.index("app = FastAPI(", inicio)]
    assert "await _sincronizar_telegram()" in corpo and "await _parar_telegram()" in corpo
    codigo = "\n".join(l.split("#")[0] for l in corpo.splitlines())
    assert "openjarvis" not in codigo.lower(), "o Telegram do Vard não depende do OpenJarvis"


async def test_conflito_409_marca_o_poller(tmp_path, monkeypatch):
    """409 = outro consumidor no mesmo bot (OpenJarvis ligado): o laço espera mais em vez de insistir."""
    transporte = httpx.MockTransport(lambda request: httpx.Response(409, json={"ok": False}))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: original(*a, **{**kw, "transport": transporte}))
    poller = tg.TelegramPoller(token=TOKEN, chats_permitidos={"111"}, estado_arquivo=tmp_path / "e.json")
    assert await poller.processar_updates() == 0
    assert poller.conflito is True
    assert tg.ESPERA_CONFLITO_S > tg.POLL_INTERVAL_PADRAO
