"""Aceite tolerante do núcleo no Windows (0.9.7).

No laço Proactor do asyncio (o padrão no Windows, e o núcleo precisa dele para abrir as CLIs com
`asyncio.create_subprocess_exec`), quando um cliente desiste da conexão antes do aceite o AcceptEx
falha com WinError 64 (ERROR_NETNAME_DELETED) ou 1236 (ERROR_CONNECTION_ABORTED). O asyncio trata
isso como erro do socket de escuta e o FECHA: o núcleo continua vivo, mas não atende mais ninguém.
O supervisor do vard.exe vê a /saude falhar, reinicia o núcleo e o widget diz "Perdi a conexão".

A correção embrulha `IocpProactor.accept`: nesses dois códigos, com a escuta ainda aberta, o aceite
é refeito em silêncio; qualquer outro erro segue como antes.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger("vard")

# ERROR_NETNAME_DELETED, ERROR_CONNECTION_ABORTED: o cliente sumiu; a escuta está boa.
TRANSITORIOS = {64, 1236}


def aceite_tolerante(original):
    """Envolve um `accept(self, listener)` do proactor para refazer o aceite nos erros transitórios."""

    def accept(self, listener):
        resultado = self._loop.create_future()
        atual = [None]

        def tentar():
            f = original(self, listener)
            atual[0] = f

            def pronto(f):
                if resultado.done():
                    return
                if f.cancelled():
                    resultado.cancel()
                    return
                erro = f.exception()
                if erro is None:
                    resultado.set_result(f.result())
                elif (isinstance(erro, OSError) and getattr(erro, "winerror", None) in TRANSITORIOS
                      and listener.fileno() != -1):
                    log.info("aceite: cliente desistiu da conexão (WinError %s); sigo escutando", erro.winerror)
                    tentar()
                else:
                    resultado.set_exception(erro)

            f.add_done_callback(pronto)

        def cancelado(r):
            if r.cancelled() and atual[0] is not None:
                atual[0].cancel()

        resultado.add_done_callback(cancelado)
        tentar()
        return resultado

    accept._vard_tolerante = True
    return accept


def instalar() -> None:
    """Instala o aceite tolerante no IocpProactor (só no Windows; chamar de novo não muda nada)."""
    if sys.platform != "win32":
        return
    from asyncio import windows_events
    if getattr(windows_events.IocpProactor.accept, "_vard_tolerante", False):
        return
    windows_events.IocpProactor.accept = aceite_tolerante(windows_events.IocpProactor.accept)
