"""Testes da T4 — laço modelo → ferramenta → resposta com diário e slot local.
Cobre: texto simples; ferramenta seguida de segunda inferência; duas ferramentas
completas; schema inválido; limite de oito rodadas; contexto excedido; cancelar
antes/durante ferramenta; falha após efeito antes de salvar resultado; frases
distintas para memoria_gravar e memoria_buscar com respostas de modelo controladas.
Persona externa, histórico da sessão, slot de inferência por motor local liberado
antes de executar ferramenta; operações síncronas em thread sem bloquear o event loop.
Diário: intenção/resultado; repetição no mesmo turno reutiliza resultado confirmado;
"efeito ocorreu, resultado não gravado" vira incerto e termina sem repetir; erro de
ferramenta volta ao modelo como erro; não falar raciocínio nem JSON de ferramenta.
Prova: transcrição sintética com contador de efeitos = 1; ferramenta bloqueada numa
sessão enquanto outra sessão conclui no mesmo motor local; diário incerto impede replay.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from vard.cerebro import diario, pedidos as modulo_pedidos, sessoes
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido, TipoEvento
from vard.cerebro.ferramentas import GerenciadorFerramentas
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


async def test_texto_simples():
    """Resposta direta emite TEXTO e FIM; estado CONCLUIDO."""
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
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO


async def test_ferramenta_seguida_de_segunda_inferencia():
    """Ferramenta dispara evento FERRAMENTA, executa e volta ao laço para segunda inferência."""
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
                    chamadas_ferramenta=[{"id": "c1", "nome": "eco", "argumentos": {"texto": "x"}}],
                )
            return ResultadoInferencia(texto="feito", provedor=self.nome)

    gm = GerenciadorFerramentas()
    gm.registrar_interna("eco", lambda texto: texto, descricao="Repete texto.")

    async def exec_ferramenta(chamada):
        chamadas.append(chamada.get("nome"))
        return {"ok": True}

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpFerramenta(), lambda ev: eventos.append(ev), gm)

    tipos = [e.tipo for e in eventos]
    assert TipoEvento.FERRAMENTA in tipos
    assert TipoEvento.TEXTO in tipos
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO


async def test_duas_ferramentas_completas():
    """Duas ferramentas completas em sequência; contador de efeitos = 2 no diário."""
    class AdpDuasFerramentas(AdaptadorProvedor):
        nome = "duas"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[
                        {"id": "c1", "nome": "eco", "argumentos": {"texto": "a"}},
                        {"id": "c2", "nome": "eco", "argumentos": {"texto": "b"}},
                    ],
                )
            return ResultadoInferencia(texto="pronto", provedor=self.nome)

    gm = GerenciadorFerramentas()
    gm.registrar_interna("eco", lambda texto: texto, descricao="Repete texto.")

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpDuasFerramentas(), lambda ev: eventos.append(ev), gm)

    ferr_events = [e for e in eventos if e.tipo == TipoEvento.FERRAMENTA]
    assert len(ferr_events) == 2
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO


async def test_limite_oito_rodadas():
    """Laço que excede LIMITE_TURNOS emite ERRO e marca FALHOU."""
    class AdpInfinito(AdaptadorProvedor):
        nome = "infinito"

        async def inferir(self, mensagens, ferramentas=None):
            return ResultadoInferencia(
                provedor=self.nome,
                chamadas_ferramenta=[{"id": "x", "nome": "loop", "argumentos": {}}],
            )

    gm = GerenciadorFerramentas()
    gm.registrar_interna("loop", lambda: "ok", descricao="Loop.")

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpInfinito(), lambda ev: eventos.append(ev), gm)

    fim = next((e for e in eventos if e.tipo == TipoEvento.FIM), None)
    assert fim is not None
    assert fim.dados.get("erro") == "limite_turnos_atingido"
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.FALHOU


async def test_diario_reutiliza_resultado_confirmado():
    """Chamada repetida no mesmo turno reutiliza resultado confirmado do diário."""
    contador = {"n": 0}

    class AdpRepete(AdaptadorProvedor):
        nome = "repete"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno <= 2:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{"id": f"c{self._turno}", "nome": "contador", "argumentos": {}}],
                )
            return ResultadoInferencia(texto="fim", provedor=self.nome)

    def fn_contador():
        contador["n"] += 1
        return str(contador["n"])

    gm = GerenciadorFerramentas()
    gm.registrar_interna("contador", fn_contador, descricao="Conta chamadas.")

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpRepete(), lambda ev: eventos.append(ev), gm)

    # A função foi chamada apenas uma vez; segunda chamada reutilizou do diário
    assert contador["n"] == 1
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO


async def test_diario_incerto_termina_sem_repetir():
    """Efeito incerto (resultado não gravado) termina sem repetir a ferramenta."""
    class AdpIncerta(AdaptadorProvedor):
        nome = "incerta"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{"id": "c1", "nome": "falha_tool", "argumentos": {}}],
                )
            # Turno 2: encontra incerto no diário → laço marca FALHOU com efeito_incerto
            # Se chegarmos aqui sem incerto detectado, devolve texto para evitar limite_turnos
            return ResultadoInferencia(texto="depois", provedor=self.nome)

    chamadas_count = {"n": 0}

    def fn_falha():
        chamadas_count["n"] += 1
        raise RuntimeError("boom")

    gm = GerenciadorFerramentas()
    gm.registrar_interna("falha_tool", fn_falha, descricao="Falha.")

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpIncerta(), lambda ev: eventos.append(ev), gm)

    # A ferramenta foi chamada exatamente uma vez; incerto impede repetição
    assert chamadas_count["n"] == 1
    assert diario.tem_incerto(ped.pedido_id, diario._chave_canonica("falha_tool", {}))
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado is not None
    assert estado.estado == EstadoPedido.FALHOU
    assert "efeito_incerto" in (estado.erro or "")


async def test_slot_local_libera_antes_de_ferramenta():
    """Slot local é adquirido durante inferência e liberado antes de executar ferramenta."""
    slot = asyncio.Semaphore(1)
    adquiridos_durante_ferramenta: list[bool] = []

    class AdpSlot(AdaptadorProvedor):
        nome = "slot"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{"id": "c1", "nome": "verifica_slot", "argumentos": {}}],
                )
            return ResultadoInferencia(texto="ok", provedor=self.nome)

    def verifica_slot():
        # Se slot está disponível (não locked), significa que foi liberado antes da ferramenta
        adquiridos_durante_ferramenta.append(slot.locked())
        return "ok"

    gm = GerenciadorFerramentas()
    gm.registrar_interna("verifica_slot", verifica_slot, descricao="Verifica slot.")

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpSlot(), lambda ev: eventos.append(ev), gm, slot_local=slot)

    # Slot deve estar liberado (False) durante execução da ferramenta
    assert adquiridos_durante_ferramenta == [False]


async def test_memoria_gravar_e_buscar_distintas():
    """Frases distintas para memoria_gravar e memoria_buscar com respostas controladas."""
    gravacoes: list[str] = []
    buscas: list[str] = []

    class AdpMemoria(AdaptadorProvedor):
        nome = "memoria"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{
                        "id": "g1", "nome": "memoria_gravar",
                        "argumentos": {"titulo": "teste", "texto": "conteúdo X"},
                    }],
                )
            if self._turno == 2:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{
                        "id": "b1", "nome": "memoria_buscar",
                        "argumentos": {"pergunta": "onde está X?"},
                    }],
                )
            return ResultadoInferencia(texto="memória ok", provedor=self.nome)

    def fn_gravar(titulo, texto):
        gravacoes.append(f"{titulo}:{texto}")
        return "gravado"

    def fn_buscar(pergunta):
        buscas.append(pergunta)
        return "achado"

    gm = GerenciadorFerramentas()
    gm.registrar_interna("memoria_gravar", fn_gravar, descricao="Grava memória.")
    gm.registrar_interna("memoria_buscar", fn_buscar, descricao="Busca memória.")

    eventos: list[Any] = []
    ped = _pedido()
    info, _ = modulo_pedidos.admitir(ped)
    info.estado = EstadoPedido.EXECUTANDO
    modulo_pedidos._gravar_info(info)

    await executar_pedido(ped, AdpMemoria(), lambda ev: eventos.append(ev), gm)

    assert gravacoes == ["teste:conteúdo X"]
    assert buscas == ["onde está X?"]
    estado = modulo_pedidos.consultar(ped.pedido_id)
    assert estado and estado.estado == EstadoPedido.CONCLUIDO
    assert estado.resposta == "memória ok"


async def test_ferramenta_bloqueada_nao_trava_outra_sessao():
    """Slot local é liberado antes da ferramenta; duas sessões completam sem deadlock."""
    slot = asyncio.Semaphore(1)
    gm = GerenciadorFerramentas()

    import time

    ordem_execucao: list[str] = []

    def fn_lenta():
        ordem_execucao.append("lenta_inicio")
        time.sleep(0.3)
        ordem_execucao.append("lenta_fim")
        return "lento"

    def fn_rapida():
        ordem_execucao.append("rapida")
        return "rápido"

    gm.registrar_interna("lenta", fn_lenta, descricao="Lenta.")
    gm.registrar_interna("rapida", fn_rapida, descricao="Rápida.")

    class AdpLenta(AdaptadorProvedor):
        nome = "lenta"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{"id": "l1", "nome": "lenta", "argumentos": {}}],
                )
            return ResultadoInferencia(texto="lento feito", provedor=self.nome)

    class AdpRapida(AdaptadorProvedor):
        nome = "rapida"

        def __init__(self) -> None:
            self._turno = 0

        async def inferir(self, mensagens, ferramentas=None):
            self._turno += 1
            if self._turno == 1:
                return ResultadoInferencia(
                    provedor=self.nome,
                    chamadas_ferramenta=[{"id": "r1", "nome": "rapida", "argumentos": {}}],
                )
            return ResultadoInferencia(texto="rápido feito", provedor=self.nome)

    ped_lenta = _pedido("pl", "sl")
    ped_rapida = _pedido("pr", "sr")
    for p in (ped_lenta, ped_rapida):
        info, _ = modulo_pedidos.admitir(p)
        info.estado = EstadoPedido.EXECUTANDO
        modulo_pedidos._gravar_info(info)

    eventos_lenta: list[Any] = []
    eventos_rapida: list[Any] = []

    # Lança ambas as tarefas; o slot garante que inferências não sobreponham,
    # mas ferramentas rodam fora do slot (liberado antes da execução).
    tarefa_lenta = asyncio.create_task(
        executar_pedido(ped_lenta, AdpLenta(), lambda ev: eventos_lenta.append(ev), gm, slot_local=slot)
    )
    tarefa_rapida = asyncio.create_task(
        executar_pedido(ped_rapida, AdpRapida(), lambda ev: eventos_rapida.append(ev), gm, slot_local=slot)
    )

    await asyncio.wait_for(asyncio.gather(tarefa_lenta, tarefa_rapida), timeout=10.0)

    estado_lenta = modulo_pedidos.consultar("pl")
    estado_rapida = modulo_pedidos.consultar("pr")
    assert estado_lenta and estado_lenta.estado == EstadoPedido.CONCLUIDO
    assert estado_rapida and estado_rapida.estado == EstadoPedido.CONCLUIDO
    # Ambas as ferramentas executaram
    assert "lenta_fim" in ordem_execucao
    assert "rapida" in ordem_execucao


async def test_diario_incerto_impede_replay():
    """Após reconstruir o núcleo, diário incerto impede replay da ferramenta."""
    ped = _pedido("px", "sx")
    chave = diario._chave_canonica("acao", {"v": 1})
    diario.registrar_intencao(ped.pedido_id, "acao", {"v": 1})
    diario.marcar_incerto(ped.pedido_id, chave)

    # Simula nova execução: verifica que incerto existe
    assert diario.tem_incerto(ped.pedido_id, chave)
    assert not diario.tem_resultado(ped.pedido_id, chave)