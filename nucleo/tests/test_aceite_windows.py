"""Aceite tolerante do núcleo no Windows (0.9.7).

No laço Proactor do asyncio, um cliente que desiste da conexão antes do aceite faz o AcceptEx falhar
com WinError 64; o asyncio então fecha o socket de escuta e o núcleo para de atender (o supervisor
do vard.exe vê a /saude falhar e reinicia o núcleo: o widget diz "Perdi a conexão").
"""
from __future__ import annotations

import asyncio
import socket
import sys

import pytest

from vard import aceite_windows


class _Futuro:
    """Futuro do aceite já resolvido, como o IocpProactor devolve."""

    def __init__(self, loop, *, erro: BaseException | None = None, valor=None):
        self._f = loop.create_future()
        if erro is not None:
            self._f.set_exception(erro)
        else:
            self._f.set_result(valor)

    def __getattr__(self, nome):
        return getattr(self._f, nome)


class _Escuta:
    def __init__(self):
        self.aberto = True

    def fileno(self) -> int:
        return 7 if self.aberto else -1


def _proactor_falso(loop, respostas):
    chamadas = []

    def original(self, listener):
        chamadas.append(listener)
        r = respostas.pop(0)
        return _Futuro(loop, erro=r) if isinstance(r, BaseException) else _Futuro(loop, valor=r)

    eu = type("Proactor", (), {"_loop": loop})()
    return eu, original, chamadas


def _erro_win(codigo: int) -> OSError:
    e = OSError(22, "erro de rede fictício")
    e.winerror = codigo
    return e


def test_erro_transitorio_tenta_de_novo_sem_propagar():
    loop = asyncio.new_event_loop()
    try:
        eu, original, chamadas = _proactor_falso(loop, [_erro_win(64), _erro_win(1236), ("conexao", "endereco")])
        aceitar = aceite_windows.aceite_tolerante(original)
        f = aceitar(eu, _Escuta())
        assert loop.run_until_complete(asyncio.wait_for(f, 1)) == ("conexao", "endereco")
        assert len(chamadas) == 3
    finally:
        loop.close()


def test_outro_erro_continua_propagando():
    loop = asyncio.new_event_loop()
    try:
        eu, original, _ = _proactor_falso(loop, [_erro_win(10024)])
        f = aceite_windows.aceite_tolerante(original)(eu, _Escuta())
        with pytest.raises(OSError):
            loop.run_until_complete(asyncio.wait_for(f, 1))
    finally:
        loop.close()


def test_escuta_fechada_nao_insiste():
    loop = asyncio.new_event_loop()
    try:
        escuta = _Escuta()
        escuta.aberto = False
        eu, original, chamadas = _proactor_falso(loop, [_erro_win(64), ("c", "e")])
        f = aceite_windows.aceite_tolerante(original)(eu, escuta)
        with pytest.raises(OSError):
            loop.run_until_complete(asyncio.wait_for(f, 1))
        assert len(chamadas) == 1
    finally:
        loop.close()


def test_cancelar_o_aceite_cancela_o_de_dentro():
    loop = asyncio.new_event_loop()
    try:
        dentro = loop.create_future()
        eu = type("Proactor", (), {"_loop": loop})()
        f = aceite_windows.aceite_tolerante(lambda self, l: dentro)(eu, _Escuta())
        f.cancel()
        loop.run_until_complete(asyncio.sleep(0))
        assert dentro.cancelled()
    finally:
        loop.close()


@pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
def test_instalar_e_idempotente_e_o_servidor_real_segue_aceitando():
    from asyncio import windows_events
    aceite_windows.instalar()
    primeira = windows_events.IocpProactor.accept
    aceite_windows.instalar()
    assert windows_events.IocpProactor.accept is primeira

    async def cenario():
        async def eco(leitor, escritor):
            escritor.write(await leitor.read(4))
            await escritor.drain()
            escritor.close()

        servidor = await asyncio.start_server(eco, "127.0.0.1", 0)
        porta = servidor.sockets[0].getsockname()[1]
        respostas = []
        for _ in range(3):
            leitor, escritor = await asyncio.open_connection("127.0.0.1", porta)
            escritor.write(b"oi!!")
            await escritor.drain()
            respostas.append(await leitor.read(4))
            escritor.close()
        # Cliente que reseta (RST) a conexão logo após conectar: o servidor continua atendendo.
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00")
        s.connect(("127.0.0.1", porta))
        s.close()
        await asyncio.sleep(0.1)
        leitor, escritor = await asyncio.open_connection("127.0.0.1", porta)
        escritor.write(b"fim!")
        await escritor.drain()
        respostas.append(await leitor.read(4))
        escritor.close()
        servidor.close()
        await servidor.wait_closed()
        return respostas

    loop = asyncio.ProactorEventLoop()
    try:
        assert loop.run_until_complete(asyncio.wait_for(cenario(), 10)) == [b"oi!!"] * 3 + [b"fim!"]
    finally:
        loop.close()


def test_servidor_instala_o_aceite_tolerante_no_windows():
    import server  # noqa: F401
    if sys.platform == "win32":
        from asyncio import windows_events
        assert getattr(windows_events.IocpProactor.accept, "_vard_tolerante", False)
