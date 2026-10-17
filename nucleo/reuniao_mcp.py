"""MCP da reunião: controla o vard-reuniao (4720) por seis ferramentas curtas. Transporte stdio.

Toda ferramenta devolve uma frase em português e nunca levanta (mesmo contrato da mesa).
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from vard import reuniao
from vard.seguro import seguro

mcp = MCPServer("reuniao")


@mcp.tool()
@seguro("iniciar a reunião")
def reuniao_iniciar() -> str:
    """Começa a acompanhar a reunião (grava e transcreve). Use para: acompanha, começa ou grava a reunião."""
    return reuniao.iniciar()


@mcp.tool()
@seguro("encerrar a reunião")
def reuniao_encerrar() -> str:
    """Encerra a reunião em andamento. Use para: encerra, para ou termina a reunião."""
    return reuniao.encerrar()


@mcp.tool()
@seguro("ver a reunião")
def reuniao_status() -> str:
    """Diz se há reunião em andamento (há quanto tempo, quantas falas) ou qual foi a última."""
    return reuniao.status()


@mcp.tool()
@seguro("gerar a ata")
def reuniao_ata(tipo: str = "ata", qual: str = "ultima") -> str:
    """Gera a ata ou o relatório (tipo ata|relatorio) de uma reunião. qual: ultima ou data AAAA-MM-DD."""
    return reuniao.abrir_ata(qual, tipo)


@mcp.tool()
@seguro("nomear o falante")
def reuniao_falante(n: int, nome: str, qual: str = "ultima") -> str:
    """Dá nome a um falante da reunião: n é o número (1, 2...), nome é como o usuário o chama."""
    if n < 1 or not (nome or "").strip():
        return reuniao.nomear_falante("", n, nome)
    return reuniao.nomear_falante(reuniao.pasta_por_pedido(qual), n, nome)


@mcp.tool()
@seguro("guardar a ata")
def reuniao_guardar(qual: str = "ultima") -> str:
    """Guarda a ata da reunião na memória de longo prazo. Só quando o usuário pedir."""
    return reuniao.guardar_na_memoria(qual)


if __name__ == "__main__":
    from vard.instalaveis import limpar_ambiente_mcp
    limpar_ambiente_mcp()
    mcp.run()
