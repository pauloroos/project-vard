"""Testes da T3 — laço de inferência, diário de ferramentas e limites.
Cobre: resposta direta, chamada de ferramenta com resultado, limite de turnos,
erro do adaptador e evento FIM sempre emitido.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from vard.cerebro import pedidos as modulo_pedidos, sessoes
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido, TipoEvento
from vard.cerebro.laco import executar_pedido
from vard.cerebro.provedores import AdaptadorFalso, AdaptadorProvedor, ResultadoInferencia


@pytest.fixture(autouse=True)
def _isolar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dados = tmp_path / "dados"
    cfg = tmp_path / "config"
    dados.mkdir()
    cfg.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    modulo_pedidos.definir_pasta(dados / "cerebro" / "pedidos")
    modulo_pedidos.limpar_tudo()
    yield
    modulo_pedidos.limpar_tudo()


def _pedido(pid: str = "p1", sid: str = "s1", texto: str = "oi") -> Pedido:
    return Pedido(pedido_id=pid, sessao_id=sid, origem=Origem.PAINEL, texto=texto)


async def test_resposta_direta_emite_texto_e_fim():
    """Adaptador que devolve texto gera eventos TEXTO e FIM; estado fica CONCLUIDO."""
    eventos: list[Any] = []
    adp = AdaptadorFalso(resposta="olá mundo")
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, adp, lambda ev: eventos.append(ev))

    tipos = [e.tipo for e in eventos]
    assert TipoEvento.TEXTO in tipos
    assert TipoEvento.FIM in tipos
    fim = next(e for e in eventos if e.tipo == TipoEvento.FIM)
    assert fim.dados["resposta"] == "olá mundo"
    assert fim.dados.get("erro") is None
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO
    assert estado.resposta == "olá mundo"
    assert estado.provedor_usado == "falso"


async def test_ferramenta_executa_e_continua():
    """Chamada de ferramenta dispara evento FERRAMENTA, executa e volta ao laço."""
    chamadas: list[str] = []

    class AdpFerramenta(AdaptadorProvedor):
        nome = "ferramenta"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{"id": "c1", "name": "eco", "arguments": {"v": 1}}],
                )
            return ResultadoInferencia(texto="feito", provedor=self.nome)

    async def exec_ferramenta(chamada):
        chamadas.append(chamada.get("name"))
        return {"ok": True}

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpFerramenta(), lambda ev: eventos.append(ev), exec_ferramenta)

    tipos = [e.tipo for e in eventos]
    assert TipoEvento.FERRAMENTA in tipos
    assert TipoEvento.TEXTO in tipos
    assert chamadas == ["eco"]
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO


async def test_limite_turnos_gera_erro():
    """Laço que excede LIMITE_TURNOS emite ERRO e marca FALHOU."""

    class AdpInfinito(AdaptadorProvedor):
        nome = "infinito"

        async def inferir(self, mensagens, ferramentas=None):
            # Sempre devolve chamada de ferramenta sem resposta final
            return ResultadoInferencia(
                provedor=self.nome,
                chamadas_ferramenta=[{"id": "x", "name": "loop"}],
            )

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpInfinito(), lambda ev: eventos.append(ev), lambda c: {"ok": True})

    fim = next((e for e in eventos if e.tipo == TipoEvento.FIM), None)
    assert fim is not None
    assert fim.dados.get("erro") == "limite_turnos_atingido"
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.FALHOU


async def test_erro_do_adaptador_emite_evento_erro():
    """Falha na inferência emite ERRO e FIM com erro; estado FALHOU."""
    eventos: list[Any] = []
    adp = AdaptadorFalso(falhar=True)
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, adp, lambda ev: eventos.append(ev))

    tipos = [e.tipo for e in eventos]
    assert TipoEvento.ERRO in tipos
    assert TipoEvento.FIM in tipos
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.FALHOU
    assert estado.erro == "falha_simulada"


async def test_historico_da_sessao_eh_atualizado():
    """Resposta do assistente entra no histórico da sessão após execução."""
    adp = AdaptadorFalso(resposta="resposta X")
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, adp, lambda ev: None)

    hist = sessoes.obter_historico(ped.sessao_id)
    conteudos = [m.get("content") for m in hist if m.get("role") == "assistant"]
    assert "resposta X" in conteudos
    sessoes.limpar(ped.sessao_id)