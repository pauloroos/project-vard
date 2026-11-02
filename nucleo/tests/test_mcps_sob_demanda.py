"""MCPs locais do cérebro sobem só no primeiro pedido de provedor de API, uma vez."""
from __future__ import annotations

import asyncio

import server


class GerenciadorFalso:
    def __init__(self) -> None:
        self.adicionados: list[str] = []

    async def adicionar_stdio(self, nome, comando, args) -> None:
        await asyncio.sleep(0.01)
        self.adicionados.append(nome)


def test_liga_uma_vez_mesmo_com_pedidos_simultaneos(monkeypatch) -> None:
    falso = GerenciadorFalso()
    monkeypatch.setattr(server, "_ferramentas_cerebro", falso)
    monkeypatch.setattr(server, "_mcps_locais", {"ligados": False, "tarefa": None})
    import vard.segredos
    monkeypatch.setattr(vard.segredos, "servidores_locais", lambda: {"a": {"command": "x", "args": []}, "b": {"command": "y", "args": []}})

    async def rodar():
        await asyncio.gather(server._ligar_mcps_locais(), server._ligar_mcps_locais())
        await server._ligar_mcps_locais()

    asyncio.run(rodar())
    assert falso.adicionados == ["a", "b"]
    assert server._mcps_locais["ligados"] is True


def test_pedido_cancelado_nao_interrompe_a_subida(monkeypatch) -> None:
    falso = GerenciadorFalso()
    monkeypatch.setattr(server, "_ferramentas_cerebro", falso)
    monkeypatch.setattr(server, "_mcps_locais", {"ligados": False, "tarefa": None})
    import vard.segredos
    monkeypatch.setattr(vard.segredos, "servidores_locais", lambda: {"a": {"command": "x", "args": []}, "b": {"command": "y", "args": []}})

    async def rodar():
        primeiro = asyncio.ensure_future(server._ligar_mcps_locais())
        await asyncio.sleep(0.005)  # cancela no meio da subida de "a"
        primeiro.cancel()
        await server._ligar_mcps_locais()  # o seguinte espera a mesma subida, sem repetir

    asyncio.run(rodar())
    assert falso.adicionados == ["a", "b"]


def test_partida_do_nucleo_nao_sobe_mcps(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    import vard.segredos
    chamados: list[str] = []
    monkeypatch.setattr(vard.segredos, "servidores_locais", lambda: chamados.append("x") or {})
    with TestClient(server.app):
        pass
    assert chamados == []
