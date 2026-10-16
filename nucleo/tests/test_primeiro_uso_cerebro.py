"""Testes do módulo de teste de cérebro para o assistente de primeiro uso (T3).
Cobre: validação de entrada, montagem de adaptador, timeout, erro de provedor,
resposta válida e integração com a rota /primeiro-uso/cerebro/testar.
Nenhum teste real contra LM Studio ou API externa; tudo com dublês.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vard.primeiro_uso import cerebro as modulo_cerebro
from vard.cerebro.provedores import ErroProvedor, EventoInferencia


@pytest.mark.asyncio
async def test_cerebro_base_url_vazia_devolve_falha():
    resultado = await modulo_cerebro.testar_cerebro(
        tipo="openai_compat", base_url="", modelo="llama-3"
    )
    assert resultado["ok"] is False
    assert resultado["detalhe"] == "base_url_vazia"
    assert resultado["primeiro_token_ms"] is None


@pytest.mark.asyncio
async def test_cerebro_modelo_vazio_devolve_falha():
    resultado = await modulo_cerebro.testar_cerebro(
        tipo="openai_compat", base_url="http://provedor.invalid", modelo=""
    )
    assert resultado["ok"] is False
    assert resultado["detalhe"] == "modelo_vazio"
    assert resultado["primeiro_token_ms"] is None


@pytest.mark.asyncio
async def test_cerebro_tipo_desconhecido_devolve_falha():
    resultado = await modulo_cerebro.testar_cerebro(
        tipo="inexistente", base_url="http://provedor.invalid", modelo="llama-3"
    )
    assert resultado["ok"] is False
    assert "tipo_de_provedor_desconhecido" in resultado["detalhe"]


@pytest.mark.asyncio
async def test_cerebro_resposta_valida_devolve_ok():
    eventos = [
        EventoInferencia("texto", {"conteudo": "pronto"}),
        EventoInferencia("fim", {}),
    ]

    async def stream_falso(*_args, **_kwargs):
        for ev in eventos:
            yield ev

    mock_adaptador = MagicMock()
    mock_adaptador.inferir = stream_falso

    with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
        resultado = await modulo_cerebro.testar_cerebro(
            tipo="openai_compat", base_url="http://provedor.invalid", modelo="llama-3"
        )

    assert resultado["ok"] is True
    assert resultado["detalhe"] == "resposta_recebida"
    assert isinstance(resultado["primeiro_token_ms"], int)
    assert resultado["primeiro_token_ms"] >= 0


@pytest.mark.asyncio
async def test_cerebro_timeout_devolve_falha():
    async def stream_lento(*_args, **_kwargs):
        await asyncio.sleep(60)
        yield EventoInferencia("fim", {})

    mock_adaptador = MagicMock()
    mock_adaptador.inferir = stream_lento

    # Força timeout curto para o teste
    original = modulo_cerebro.TIMEOUT_TOTAL_S
    modulo_cerebro.TIMEOUT_TOTAL_S = 0.1
    try:
        with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
            resultado = await modulo_cerebro.testar_cerebro(
                tipo="openai_compat", base_url="http://provedor.invalid", modelo="llama-3"
            )
    finally:
        modulo_cerebro.TIMEOUT_TOTAL_S = original

    assert resultado["ok"] is False
    assert "timeout" in resultado["detalhe"]


@pytest.mark.asyncio
async def test_cerebro_erro_provedor_devolve_falha():
    mock_adaptador = MagicMock()

    async def stream_erro(*_args, **_kwargs):
        raise ErroProvedor("auth_401", False, "credencial recusada")
        yield  # pragma: no cover

    mock_adaptador.inferir = stream_erro

    with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
        resultado = await modulo_cerebro.testar_cerebro(
            tipo="openai_compat", base_url="http://provedor.invalid", modelo="llama-3", chave="sk-falsa"
        )

    assert resultado["ok"] is False
    assert "auth_401" in resultado["detalhe"]


@pytest.mark.asyncio
async def test_cerebro_sem_resposta_devolve_falha():
    """Stream que emite apenas 'fim' sem texto conta como falha."""

    async def stream_vazio(*_args, **_kwargs):
        yield EventoInferencia("fim", {})

    mock_adaptador = MagicMock()
    mock_adaptador.inferir = stream_vazio

    with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
        resultado = await modulo_cerebro.testar_cerebro(
            tipo="openai_compat", base_url="http://provedor.invalid", modelo="llama-3"
        )

    assert resultado["ok"] is False
    assert resultado["detalhe"] == "sem_resposta_do_modelo"


def test_montar_adaptador_tipos_conhecidos():
    """Verifica que todos os tipos conhecidos criam adaptadores sem erro."""
    tipos_validos = [
        ("openai_compat", "http://provedor.invalid", "m", ""),
        ("lmstudio", "http://provedor.invalid", "m", ""),
        ("local", "http://provedor.invalid", "m", ""),
        ("anthropic", "https://api.anthropic.com", "claude-3", "sk-x"),
        ("google", "https://generativelanguage.googleapis.com", "gemini-2.5-flash", "key"),
        ("openai_nativo", "https://api.openai.com", "gpt-4o-mini", "sk-x"),
    ]
    for tipo, url, modelo, chave in tipos_validos:
        adaptador = modulo_cerebro._montar_adaptador(tipo, url, modelo, chave)
        assert adaptador is not None, f"tipo {tipo} deveria criar adaptador"


def test_montar_adaptador_tipo_invalido_levanta():
    with pytest.raises(ValueError, match="tipo_de_provedor_desconhecido"):
        modulo_cerebro._montar_adaptador("desconhecido", "http://x", "m", "")
# Contratos HTTP reais contra dublê em porta livre.
from tests.dubles.lmstudio_primeiro_uso import provedor_falso


async def test_lmstudio_lista_modelos_baixados_e_contexto():
    with provedor_falso() as (url, _):
        modelos = await modulo_cerebro.listar_modelos("lmstudio", url)
    assert [m["id"] for m in modelos] == ["antigo", "novo"]
    assert modelos[0]["instancias"][0]["contexto"] == 4096


async def test_troca_descarrega_confirma_ausencia_carrega():
    with provedor_falso() as (url, estado):
        resultado = await modulo_cerebro.trocar_modelo(url, "novo")
    assert resultado["ok"] is True
    chamadas = estado["requisicoes"]
    assert [c[1] for c in chamadas] == ["/api/v1/models", "/api/v1/models/unload",
        "/api/v1/models", "/api/v1/models/load", "/api/v1/models"]
    assert chamadas[3][2] == {"model": "novo"}


async def test_ausencia_nao_confirmada_impede_carga():
    with provedor_falso() as (url, estado):
        estado["recusar_descarga"] = True
        resultado = await modulo_cerebro.trocar_modelo(url, "novo")
    assert resultado["ok"] is False
    assert not any(c[1].endswith("/load") for c in estado["requisicoes"])


async def test_modelo_inexistente_nao_descarrega_nem_infere():
    with provedor_falso() as (url, estado):
        resultado = await modulo_cerebro.testar_cerebro("lmstudio", url, "ausente")
    assert resultado["ok"] is False
    assert all(c[0] == "GET" for c in estado["requisicoes"])


async def test_provedor_fechado_falha_sem_alternar():
    import socket
    with socket.socket() as reservado:
        reservado.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{reservado.getsockname()[1]}"
        resultado = await modulo_cerebro.testar_cerebro("openai_compat", url, "novo")
    assert resultado["ok"] is False
    assert resultado["detalhe"] == "conexao"


async def test_externo_sem_credencial_nao_envia_http():
    with provedor_falso() as (url, estado):
        resultado = await modulo_cerebro.testar_cerebro("anthropic", url, "novo")
    assert resultado["detalhe"] == "credencial_ausente"
    assert estado["requisicoes"] == []


async def test_sse_interrompido_com_texto_nao_e_sucesso():
    with provedor_falso() as (url, estado):
        estado["interromper"] = True
        resultado = await modulo_cerebro.testar_cerebro("openai_compat", url, "novo")
    assert resultado["ok"] is False
    assert resultado["detalhe"] == "sse_interrompido"


async def test_teste_local_cpu_sem_historico_ferramentas_ou_troca():
    with provedor_falso() as (url, estado):
        resultado = await modulo_cerebro.testar_cerebro("lmstudio", url, "antigo")
    assert resultado["ok"] is True
    corpo = estado["requisicoes"][-1][2]
    assert corpo["model"] == "anterior"
    assert corpo["messages"] == [{"role": "user", "content": "Responda apenas: pronto"}]
    assert "tools" not in corpo
    assert not any(c[1].endswith(("/load", "/unload")) for c in estado["requisicoes"])


async def test_modelo_baixado_nao_residente_exige_troca_explicita():
    with provedor_falso() as (url, estado):
        resultado = await modulo_cerebro.testar_cerebro("lmstudio", url, "novo")
    assert resultado["detalhe"] == "modelo_nao_carregado"
    assert all(c[0] == "GET" for c in estado["requisicoes"])



async def test_rotas_http_da_etapa_com_provedor_falso(tmp_path, monkeypatch):
    import sys
    import httpx
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    monkeypatch.setenv("VARD_HUD_CONFIG_DIR", str(tmp_path / "hud"))
    import server
    with provedor_falso() as (url, estado):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1") as cliente:
            corpo = {"tipo": "lmstudio", "base_url": url, "modelo": "novo"}
            lista = await cliente.post("/primeiro-uso/cerebro/modelos", json=corpo)
            assert lista.json()["modelos"][1]["id"] == "novo"
            troca = await cliente.post("/primeiro-uso/cerebro/trocar", json=corpo)
            assert troca.json()["ok"] is True
            teste = await cliente.post("/primeiro-uso/cerebro/testar", json=corpo)
            assert teste.json()["ok"] is True
            invalido = await cliente.post("/primeiro-uso/cerebro/testar", json={**corpo, "modelo": {}})
            assert invalido.status_code == 422
            recusado = await cliente.post("/primeiro-uso/cerebro/trocar", json=corpo, headers={"Origin": "https://externo.invalid"})
            assert recusado.status_code == 403


async def test_timeout_total_30_segundos_contra_http_lento():
    import time
    assert modulo_cerebro.TIMEOUT_TOTAL_S == 30
    with provedor_falso() as (url, estado):
        estado["atraso"] = 31
        inicio = time.monotonic()
        resultado = await modulo_cerebro.testar_cerebro("openai_compat", url, "novo")
        duracao = time.monotonic() - inicio
    assert resultado["ok"] is False
    assert resultado["detalhe"] in ("timeout_30s", "timeout")
    assert 29 <= duracao < 32


async def test_ferramenta_hora_pelo_laco_08_com_sse_real(tmp_path, monkeypatch):
    from datetime import datetime
    from vard.cerebro import pedidos, sessoes
    from vard.cerebro.contratos import Pedido, Origem, EstadoPedido
    from vard.cerebro.ferramentas import GerenciadorFerramentas
    from vard.cerebro.laco import executar_pedido
    pedidos.definir_pasta(tmp_path / "pedidos")
    pedidos.limpar_tudo()
    chamadas = []
    def hora():
        resultado = datetime.now().strftime("%H:%M:%S")
        chamadas.append(resultado)
        return resultado
    gm = GerenciadorFerramentas()
    gm.registrar_interna("hora", hora, descricao="Hora local sem efeitos colaterais")
    ped = Pedido(pedido_id="prova-hora", sessao_id="sessao-hora", origem=Origem.PAINEL, texto="Que horas são?")
    pedidos.admitir(ped)
    eventos = []
    try:
        with provedor_falso() as (url, estado):
            await executar_pedido(ped, modulo_cerebro._montar_adaptador("openai_compat", url, "novo"), eventos.append, gm)
        info = pedidos.consultar(ped.pedido_id)
        assert info.estado == EstadoPedido.CONCLUIDO
        assert len(chamadas) == 1
        assert chamadas[0] in info.resposta
        assert len(estado["sse"]) == 2
        assert any(e.tipo.value == "ferramenta" for e in eventos)
    finally:
        await gm.fechar_tudo()
        pedidos.limpar_tudo()
        pedidos.definir_pasta(None)
