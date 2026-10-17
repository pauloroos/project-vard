"""Botão Testar das Configurações: chave do cofre do provedor salvo e CLIs sem endereço."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def server(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    import server as srv
    return srv


def _paineis(srv, provedores):
    arq = srv.config.arquivo_config("paineis.json")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"versao": 1, "provedores": provedores, "ativo": None, "reserva": None,
                               "agentes": {}, "mcps": []}), encoding="utf-8")


LM = {"id": "lm1", "nome": "LM", "tipo": "lmstudio", "url_base": "http://127.0.0.1:1234",
      "modelo": "m", "credencial_ref": "provedor:lm1"}


def test_chave_do_cofre_vai_so_para_o_endereco_salvo(server, monkeypatch):
    _paineis(server, [LM])
    monkeypatch.setattr(server, "_resolver_credencial_cofre", lambda ref, tipo: "segredo-ficticio")
    base = {"tipo": "lmstudio", "provedor_id": "lm1"}
    assert server._chave_do_teste({**base, "base_url": "http://127.0.0.1:1234/v1/"}) == "segredo-ficticio"
    assert server._chave_do_teste({**base, "base_url": "http://outro.invalid:1234"}) == ""
    assert server._chave_do_teste({**base, "tipo": "openai_compat", "base_url": "http://127.0.0.1:1234"}) == ""
    assert server._chave_do_teste({**base, "base_url": "http://127.0.0.1:1234", "chave": "digitada"}) == "digitada"
    assert server._chave_do_teste({"tipo": "lmstudio", "base_url": "http://127.0.0.1:1234"}) == ""


async def _post(server, corpo):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1") as c:
        return await c.post("/primeiro-uso/cerebro/testar", json=corpo)


@pytest.mark.asyncio
async def test_cli_sem_endereco_nao_e_recusada_e_avisa_quando_falta(server, monkeypatch):
    from vard.cerebro import cli_deteccao
    monkeypatch.setattr(cli_deteccao, "detectar", lambda: [{"tipo": "cli-claude", "instalada": False}])
    r = await _post(server, {"tipo": "cli-claude", "base_url": "", "modelo": ""})
    assert r.status_code == 200
    assert r.json() == {"ok": False, "detalhe": "cli_nao_encontrada", "primeiro_token_ms": None}


@pytest.mark.asyncio
async def test_codex_instalado_conta_como_ok_sem_rodar(server, monkeypatch):
    from vard.cerebro import cli_deteccao
    monkeypatch.setattr(cli_deteccao, "detectar",
                        lambda: [{"tipo": "cli-codex", "instalada": True, "versao": "codex-cli 0.1"}])
    r = await _post(server, {"tipo": "cli-codex", "base_url": "", "modelo": ""})
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_claude_testa_numa_sessao_descartavel_e_encerra(server, monkeypatch):
    from vard.cerebro import cli_deteccao
    from vard.primeiro_uso import cerebro
    monkeypatch.setattr(cli_deteccao, "detectar", lambda: [{"tipo": "cli-claude", "instalada": True, "versao": "2"}])
    encerradas = []

    class Supervisor:
        async def canal(self, provedor, sessao):
            assert sessao.startswith("teste-") and provedor.yolo is False
            return object()

        async def nova_conversa(self, sessao):
            encerradas.append(sessao)

    monkeypatch.setattr(server, "_obter_supervisor_cli", lambda: Supervisor())

    async def consumir(adaptador):
        return {"ok": True, "detalhe": "resposta_recebida", "primeiro_token_ms": 5}

    monkeypatch.setattr(cerebro, "consumir_teste", consumir)
    r = await _post(server, {"tipo": "cli-claude", "base_url": "", "modelo": "claude-haiku-5-5"})
    assert r.json()["ok"] is True
    assert len(encerradas) == 1 and encerradas[0].startswith("teste-")
