"""Testes de histórico da sessão no cérebro (FR-003 / US1).

Cobre:
- Gravação do par atômico pergunta/resposta em cada troca concluída.
- Segunda inferência recebe a pergunta e a resposta do turno anterior.
- Pedidos cancelados não gravam nada no histórico.
- Pedidos que falham não gravam nada no histórico.
- Limite de trocas completas mantido (descarta pares mais antigos por inteiro).
- Isolamento estrito entre sessões distintas.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from vard.cerebro import pedidos as modulo_pedidos, sessoes
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido, TipoEvento
from vard.cerebro.laco import executar_pedido
from vard.cerebro.provedores import AdaptadorFalso, AdaptadorProvedor, ErroProvedor, ResultadoInferencia


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


def _criar_pedido(pid: str = "p1", sid: str = "s1", texto: str = "olá") -> Pedido:
    ped = Pedido(pedido_id=pid, sessao_id=sid, origem=Origem.PAINEL, texto=texto)
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)
    return ped


@pytest.mark.asyncio
async def test_troca_concluida_grava_par_pergunta_resposta():
    """FR-003: Troca concluída com sucesso grava par pergunta/resposta no histórico."""
    ped = _criar_pedido(pid="ped-1", sid="sessao-1", texto="meu código fictício é AZUL")
    adp = AdaptadorFalso(resposta="Entendido, código anotado.")

    eventos: list[Any] = []
    await executar_pedido(ped, adp, lambda ev: eventos.append(ev))

    historico = sessoes.obter_historico("sessao-1")
    assert len(historico) == 2, f"Esperado par (2 mensagens), obtido: {historico}"
    assert historico[0] == {"role": "user", "content": "meu código fictício é AZUL"}
    assert historico[1] == {"role": "assistant", "content": "Entendido, código anotado."}


@pytest.mark.asyncio
async def test_segunda_inferencia_lembra_pergunta_anterior():
    """US1 / Cenário 3: O assistente recebe o contexto do turno anterior na inferência seguinte."""
    chamadas: list[list[dict[str, Any]]] = []

    class AdaptadorEcoContexto(AdaptadorProvedor):
        nome = "eco-contexto"

        async def inferir(self, mensagens, ferramentas=None):
            chamadas.append([dict(m) for m in mensagens])
            if len(chamadas) == 1:
                return ResultadoInferencia(provedor=self.nome, texto="Entendido.")
            # No segundo turno, verifica se o usuário mencionou AZUL
            user_msgs = [m["content"] for m in mensagens if m.get("role") == "user"]
            if any("AZUL" in str(c) for c in user_msgs):
                return ResultadoInferencia(provedor=self.nome, texto="Você disse que seu código é AZUL.")
            return ResultadoInferencia(provedor=self.nome, texto="Não lembro do código.")

    adp = AdaptadorEcoContexto()

    # Turno 1
    ped1 = _criar_pedido(pid="p-t1", sid="s-conversa", texto="meu código fictício é AZUL")
    await executar_pedido(ped1, adp, lambda ev: None)

    # Turno 2
    ped2 = _criar_pedido(pid="p-t2", sid="s-conversa", texto="qual código eu disse?")
    eventos: list[Any] = []
    await executar_pedido(ped2, adp, lambda ev: eventos.append(ev))

    # A segunda inferência deve ter recebido o histórico completo anterior
    mensagens_segundo_turno = chamadas[1]
    papéis_e_textos = [(m.get("role"), m.get("content")) for m in mensagens_segundo_turno if m.get("role") != "system"]
    assert ("user", "meu código fictício é AZUL") in papéis_e_textos
    assert ("assistant", "Entendido.") in papéis_e_textos
    assert ("user", "qual código eu disse?") in papéis_e_textos

    fim = next(e for e in eventos if e.tipo == TipoEvento.FIM)
    assert fim.dados["resposta"] == "Você disse que seu código é AZUL."


@pytest.mark.asyncio
async def test_pedido_cancelado_nao_grava_nada_no_historico():
    """FR-003: Pedidos cancelados não gravam nada no histórico da sessão."""
    class AdaptadorCancelado(AdaptadorProvedor):
        nome = "cancelado"

        async def inferir(self, mensagens, ferramentas=None):
            raise asyncio.CancelledError()

    ped = _criar_pedido(pid="p-cancel", sid="s-cancel", texto="mensagem que será cancelada")
    adp = AdaptadorCancelado()

    with pytest.raises(asyncio.CancelledError):
        await executar_pedido(ped, adp, lambda ev: None)

    historico = sessoes.obter_historico("s-cancel")
    assert historico == [], f"Histórico deveria estar vazio para pedido cancelado, obtido: {historico}"


@pytest.mark.asyncio
async def test_pedido_com_falha_nao_grava_nada_no_historico():
    """FR-003: Pedidos que falharam não gravam nada no histórico da sessão."""
    class AdaptadorComFalha(AdaptadorProvedor):
        nome = "falha"

        async def inferir(self, mensagens, ferramentas=None):
            raise ErroProvedor("erro_conexao_falso", "Falha de rede simulada")

    ped = _criar_pedido(pid="p-falha", sid="s-falha", texto="mensagem que vai falhar")
    adp = AdaptadorComFalha()

    eventos: list[Any] = []
    await executar_pedido(ped, adp, lambda ev: eventos.append(ev))

    # Garante que terminou em erro
    info = modulo_pedidos.consultar(ped.pedido_id)
    assert info is not None and info.estado == EstadoPedido.FALHOU

    historico = sessoes.obter_historico("s-falha")
    assert historico == [], f"Histórico deveria estar vazio para pedido que falhou, obtido: {historico}"


@pytest.mark.asyncio
async def test_limite_trocas_mantem_pares_completos():
    """FR-003: Limite de 10 trocas descarta pares usuário+assistente mais antigos inteiros."""
    sid = "sessao-limite"

    # Executa 12 trocas completas
    for i in range(1, 13):
        ped = _criar_pedido(pid=f"ped-{i}", sid=sid, texto=f"pergunta-{i}")
        adp = AdaptadorFalso(resposta=f"resposta-{i}")
        await executar_pedido(ped, adp, lambda ev: None)

    historico = sessoes.obter_historico(sid)
    # 10 trocas = 20 mensagens (10 pares usuário/assistente)
    assert len(historico) == 20

    # As trocas 1 e 2 devem ter sido descartadas; trocas 3 a 12 devem permanecer
    assert historico[0] == {"role": "user", "content": "pergunta-3"}
    assert historico[1] == {"role": "assistant", "content": "resposta-3"}
    assert historico[-2] == {"role": "user", "content": "pergunta-12"}
    assert historico[-1] == {"role": "assistant", "content": "resposta-12"}


@pytest.mark.asyncio
async def test_sessoes_distintas_isoladas():
    """Garante que trocas em sessões diferentes não se misturam."""
    ped_a = _criar_pedido(pid="p-a", sid="sessao-a", texto="pergunta A")
    ped_b = _criar_pedido(pid="p-b", sid="sessao-b", texto="pergunta B")

    await executar_pedido(ped_a, AdaptadorFalso(resposta="resposta A"), lambda ev: None)
    await executar_pedido(ped_b, AdaptadorFalso(resposta="resposta B"), lambda ev: None)

    hist_a = sessoes.obter_historico("sessao-a")
    hist_b = sessoes.obter_historico("sessao-b")

    assert [m["content"] for m in hist_a] == ["pergunta A", "resposta A"]
    assert [m["content"] for m in hist_b] == ["pergunta B", "resposta B"]
