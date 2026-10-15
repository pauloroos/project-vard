"""Testes da T6b: laço do cérebro usa persona montada do perfil como mensagem de sistema.

A persona é aplicada entre turnos sem reiniciar a sessão; mudar perfil.json
muda o próximo turno. Provedor FALSO recebe a persona e confirma que ela
chega ao adaptador.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from vard.cerebro.contratos import EventoPedido, Origem, Pedido, TipoEvento
from vard.cerebro.laco import executar_pedido, _obter_persona
from vard.cerebro.provedores import AdaptadorProvedor, EventoInferencia


class AdaptadorFalsoComPersona(AdaptadorProvedor):
    """Adaptador falso que captura as mensagens recebidas para inspeção."""

    def __init__(self) -> None:
        self.mensagens_recebidas: list[dict[str, Any]] = []
        self.nome = "falso_persona"

    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        self.mensagens_recebidas = list(mensagens)
        yield EventoInferencia(tipo="texto", dados={"conteudo": "resposta do falso"})
        yield EventoInferencia(tipo="fim", dados={})


@pytest.fixture(autouse=True)
def _isola_pedidos_sessoes(tmp_path, monkeypatch):
    """Isola pedidos e sessões em pasta temporária."""
    from vard.cerebro import pedidos, sessoes

    pedidos.definir_pasta(tmp_path / "pedidos")
    monkeypatch.setattr(sessoes, "_pasta_sessoes", lambda: tmp_path / "sessoes")
    yield
    pedidos.limpar_tudo()


@pytest.fixture
def perfil_falso(tmp_path, monkeypatch):
    """Cria um perfil.json falso na pasta de config temporária."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    perfil_path = cfg_dir / "perfil.json"
    perfil_data = {
        "tom": "direto",
        "personalidade": "prático",
        "instrucoes": "Responda sempre em português.",
        "sobre_usuario": "Usuário de teste.",
        "versao": 1,
    }
    perfil_path.write_text(json.dumps(perfil_data), encoding="utf-8")

    # Aponta config.pasta_config para o diretório temporário
    from vard import config as modulo_config

    monkeypatch.setattr(modulo_config, "pasta_config", lambda: cfg_dir)
    # Limpa cache da persona
    import vard.cerebro.laco as laco_mod

    laco_mod._persona_cache = None
    laco_mod._persona_versao = 0
    return perfil_path


async def test_laco_envia_persona_como_system_message(perfil_falso, tmp_path):
    """O laço insere a persona montada como primeira mensagem de sistema."""
    from vard.cerebro import pedidos

    adaptador = AdaptadorFalsoComPersona()
    pedido = Pedido(
        pedido_id="p-persona-1",
        sessao_id="s-persona-1",
        origem=Origem.PAINEL,
        texto="qual é a capital do brasil?",
    )
    info, _ = pedidos.admitir(pedido)
    eventos: list[EventoPedido] = []

    await executar_pedido(pedido, adaptador, lambda ev: eventos.append(ev))

    # Verifica que a primeira mensagem é system com conteúdo da persona
    assert len(adaptador.mensagens_recebidas) >= 2
    msg_system = adaptador.mensagens_recebidas[0]
    assert msg_system["role"] == "system"
    assert "Responda sempre em português" in msg_system["content"]
    assert "direto" in msg_system["content"] or "prático" in msg_system["content"]


async def test_laco_atualiza_persona_entre_turnos(perfil_falso, tmp_path):
    """Mudar perfil.json entre turnos atualiza a persona no próximo pedido."""
    from vard.cerebro import pedidos, sessoes
    import vard.cerebro.laco as laco_mod

    adaptador = AdaptadorFalsoComPersona()

    # Primeiro turno
    pedido1 = Pedido(
        pedido_id="p-persona-2a",
        sessao_id="s-persona-2",
        origem=Origem.PAINEL,
        texto="primeira pergunta",
    )
    pedidos.admitir(pedido1)
    await executar_pedido(pedido1, adaptador, lambda ev: None)
    persona_primeiro = adaptador.mensagens_recebidas[0]["content"]

    # Muda o perfil
    perfil_data = {
        "tom": "poético",
        "personalidade": "lírico",
        "instrucoes": "Use metáforas nas respostas.",
        "sobre_usuario": "Poeta de teste.",
        "versao": 1,
    }
    perfil_falso.write_text(json.dumps(perfil_data), encoding="utf-8")
    # Invalida cache
    laco_mod._persona_cache = None

    # Segundo turno na mesma sessão
    pedido2 = Pedido(
        pedido_id="p-persona-2b",
        sessao_id="s-persona-2",
        origem=Origem.PAINEL,
        texto="segunda pergunta",
    )
    pedidos.admitir(pedido2)
    await executar_pedido(pedido2, adaptador, lambda ev: None)
    persona_segundo = adaptador.mensagens_recebidas[0]["content"]

    assert persona_primeiro != persona_segundo
    assert "metáforas" in persona_segundo or "poético" in persona_segundo


def test_obter_persona_sem_perfil_devolve_vazio(tmp_path, monkeypatch):
    """Sem perfil.json nem persona.md, _obter_persona devolve string vazia."""
    from vard import config as modulo_config

    cfg_dir = tmp_path / "config_vazia"
    cfg_dir.mkdir()
    monkeypatch.setattr(modulo_config, "pasta_config", lambda: cfg_dir)

    import vard.cerebro.laco as laco_mod

    laco_mod._persona_cache = None
    resultado = _obter_persona()
    assert isinstance(resultado, str)