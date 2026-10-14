"""MCP da memória: o ai-memory da VPS em três ferramentas curtas (decisão D1). Transporte stdio.

Toda ferramenta devolve uma frase em português e nunca levanta (mesmo contrato da mesa).
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from vard import memoria
from vard.seguro import seguro

mcp = MCPServer("memoria")


@mcp.tool()
@seguro("procurar na memória")
def memoria_buscar(pergunta: str) -> str:
    """PERGUNTAS sobre o passado: "o que decidimos...?", "lembra quando...?". Nunca para "lembra que..." (isso é memoria_gravar)."""
    return memoria.buscar(memoria.cliente(), pergunta)


@mcp.tool()
@seguro("ler a página da memória")
def memoria_ler(caminho: str, projeto: str = "") -> str:
    """Lê inteira uma página achada por memoria_buscar (caminho e projeto vêm do resultado)."""
    return memoria.ler(memoria.cliente(), caminho, projeto)


@mcp.tool()
@seguro("anotar na memória")
def memoria_gravar(titulo: str, texto: str) -> str:
    """GRAVA o que o usuário conta agora: "lembra que...", "anota que...", "não esquece que...". Título curto e o texto dito."""
    return memoria.gravar(memoria.cliente(), titulo, texto)


if __name__ == "__main__":
    mcp.run()
