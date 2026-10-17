"""MCP da mesa: ferramentas de Windows que o OpenJarvis chama. Transporte stdio.

Cada ferramenta devolve uma frase em português e nunca levanta exceção:
o agente lê a frase e decide o que dizer ao usuário.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
from pathlib import Path

import mss
from mcp.server.mcpserver import MCPServer

from vard import config, janelas, programas, segredos

# Apelidos e sites do usuário vêm da configuração externa (VARD_CONFIG), nunca do repositório.
ARQUIVO_PROGRAMAS = config.arquivo_config("programas.toml")
APELIDOS = programas.carregar_apelidos(ARQUIVO_PROGRAMAS)
SITES_USUARIO = programas.carregar_sites(ARQUIVO_PROGRAMAS)
PASTA_PRINTS = segredos.PASTA / "prints"

mcp = MCPServer("mesa")


def _seguro(acao: str):
    """Garante o contrato da mesa: toda ferramenta devolve frase em português, nunca levanta."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as exc:  # noqa: BLE001 — contrato da mesa
                return f"Não consegui {acao}: {type(exc).__name__}: {exc}"
        return wrapper
    return deco


@mcp.tool()
@_seguro("abrir o site")
def abrir_url(url: str) -> str:
    """Abre um site no navegador padrão. Aceita nome conhecido (youtube), domínio ou URL."""
    if not url.strip():
        return "Diga qual site abrir."
    alvo = programas.normalizar_url(url, programas.carregar_sites(config.arquivo_config("programas.toml")))
    try:
        os.startfile(alvo)
    except OSError as exc:
        return f"Não consegui abrir {alvo}: {exc}"
    return f"Abri {alvo} no navegador."


@mcp.tool()
@_seguro("abrir o programa")
def abrir_programa(nome: str) -> str:
    """Abre um programa pelo nome falado (vscode, chrome, orca, terminal...)."""
    if not nome.strip():
        return "Diga qual programa abrir."
    alvo = programas.resolver_programa(nome, programas.carregar_apelidos(config.arquivo_config("programas.toml")))
    if not alvo:
        return f"Não encontrei o programa '{nome}' nos apelidos, no PATH nem no menu Iniciar."
    try:
        os.startfile(alvo)
    except OSError as exc:
        return f"Encontrei '{nome}' em {alvo}, mas não consegui abrir: {exc}"
    return f"Abri {nome}."


@mcp.tool()
@_seguro("listar as janelas")
def listar_janelas() -> str:
    """Lista as janelas visíveis (título e programa). Use antes de focar ou fechar."""
    lista = janelas.listar()
    if not lista:
        return "Nenhuma janela visível."
    texto = "\n".join(f"- {j.titulo} ({j.processo})" for j in lista[:40])
    if len(lista) > 40:
        texto += f"\n(+{len(lista) - 40} janelas não listadas)"
    return texto


@mcp.tool()
@_seguro("focar a janela")
def focar_janela(titulo: str) -> str:
    """Traz para a frente a janela cujo título contém o trecho dado."""
    j = janelas.escolher(janelas.listar(), titulo)
    if not j:
        return f"Nenhuma janela com '{titulo}' no título."
    if janelas.focar(j):
        return f"Janela '{j.titulo}' em primeiro plano."
    return f"O Windows recusou trazer '{j.titulo}' para a frente."


@mcp.tool()
@_seguro("fechar a janela")
def fechar_janela(titulo: str) -> str:
    """Pede para fechar a janela cujo título contém o trecho (o programa pode perguntar 'salvar?')."""
    j = janelas.escolher(janelas.listar(), titulo)
    if not j:
        return f"Nenhuma janela com '{titulo}' no título."
    if janelas.fechar(j):
        return f"Pedi para fechar '{j.titulo}'."
    return f"A janela '{j.titulo}' já não existe."


@mcp.tool()
@_seguro("capturar a tela")
def print_da_tela(caminho: str = "") -> str:
    """Captura a tela inteira em PNG na pasta de prints e devolve o caminho do arquivo."""
    # Só o nome do arquivo conta: nunca grava fora da pasta de prints nem sobrescreve nada existente.
    base = Path(caminho).stem if caminho.strip() else f"tela-{dt.datetime.now():%Y%m%d-%H%M%S}"
    base = base or "tela"
    destino = PASTA_PRINTS / f"{base}.png"
    n = 2
    while destino.exists():
        destino = PASTA_PRINTS / f"{base}-{n}.png"
        n += 1
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with mss.mss() as s:
            s.shot(output=str(destino))
    except Exception as exc:
        return f"Não consegui capturar a tela: {exc}"
    return f"Print salvo em {destino}"


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


@mcp.tool()
@_seguro("ler a hora")
def hora_atual() -> str:
    """Devolve a data e a hora atuais do computador, em português."""
    agora = dt.datetime.now().astimezone()
    off = agora.utcoffset() or dt.timedelta(0)
    if off == dt.timedelta(hours=-4):
        zona = "horário de Manaus"
    else:
        h = int(off.total_seconds() // 60)
        zona = f"UTC{'-' if h < 0 else '+'}{abs(h) // 60:02d}:{abs(h) % 60:02d}"
    return (f"Agora são {agora.hour}h{agora.minute:02d} de {DIAS[agora.weekday()]}, {agora.day} de "
            f"{MESES[agora.month - 1]} de {agora.year} ({zona}).")


if __name__ == "__main__":
    from vard.instalaveis import limpar_ambiente_mcp
    limpar_ambiente_mcp()
    mcp.run()
