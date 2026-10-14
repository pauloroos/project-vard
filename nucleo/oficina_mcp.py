"""MCP da oficina: dispara tarefas em agentes (Orca) e acompanha até o fim. Transporte stdio.

Toda ferramenta devolve uma frase em português e nunca levanta (mesmo contrato da mesa). O trabalho
demorado vai para um trabalhador (processo separado); a vigia sobe no __main__ (Tarefa 3).
"""
from __future__ import annotations

import datetime as dt

from mcp.server.mcpserver import MCPServer

from vard import executor, oficina, tarefas, trabalhador, vigia
from vard.seguro import seguro

mcp = MCPServer("oficina")


def _orca(t: tarefas.Tarefa | None = None):
    """Roteador: cada tarefa vai ao executor dela (terminal local ou Orca), pelo handle que guardou."""
    return executor.roteador(oficina.carregar_conf())


def _agora() -> dt.datetime:
    return dt.datetime.now().astimezone()


@mcp.tool()
@seguro("disparar a tarefa")
def disparar_tarefa(ferramenta: str, repo: str, pedido: str) -> str:
    """Põe claude, codex, opencode ou agy (Antigravity) para trabalhar num projeto; ferramenta=pesquisa (repo vazio) pesquisa um assunto."""
    repos = oficina.carregar_repos()
    if not repos and oficina.simples(ferramenta) != "pesquisa":
        return "A oficina não está configurada; cadastre os projetos em repos.toml."
    repetida = oficina.achar_duplicada(ferramenta, repo, pedido, repos=repos, agora=_agora())
    if repetida:
        return f"Já disparei a tarefa {repetida.n}; aviso quando terminar."
    t = oficina.registrar(ferramenta, repo, pedido, repos=repos)
    trabalhador.lancar(t.n)
    if t.ferramenta == "pesquisa":
        return f"Abri a pesquisa {t.n}; aviso quando terminar."
    return f"Disparei a tarefa {t.n} no {oficina.NOMES[t.ferramenta]} ({t.repo}); aviso quando terminar."


@mcp.tool()
@seguro("ver a tarefa")
def status_tarefa(n: int) -> str:
    """Diz como está a tarefa n: rodando, esperando resposta, terminou ou travou."""
    t = tarefas.obter(n)
    if t is None:
        return f"Não existe tarefa {n}."
    if t.ferramenta in tarefas.AGENTES and t.terminal and t.estado in ("rodando", "esperando", "travou"):
        t = oficina.atualizar_estado(t, orca=_orca(t), conf=oficina.carregar_conf())
    if t.estado in tarefas.AVISAVEIS and t.avisado != t.estado:
        t = tarefas.atualizar(t.n, avisado=t.estado)       # o usuário ouve agora; a vigia não repete
    return oficina.frase_tarefa(t, _agora())


@mcp.tool()
@seguro("pegar o resultado")
def resultado_tarefa(n: int) -> str:
    """Resultado da tarefa n: commits e arquivos mudados (código) ou a resposta (agente remoto, pesquisa, manhã)."""
    return oficina.resultado(n, repos=oficina.carregar_repos())


@mcp.tool()
@seguro("responder à tarefa")
def responder_tarefa(n: int, texto: str) -> str:
    """Manda uma resposta ao agente da tarefa n, quando ele perguntou algo."""
    return oficina.responder(n, texto, orca=_orca(tarefas.obter(n)))


@mcp.tool()
@seguro("aprovar a tarefa")
def aprovar_tarefa(n: int) -> str:
    """Marca a tarefa n de código como aprovada; o merge fica com o usuário."""
    return oficina.aprovar(n)


@mcp.tool()
@seguro("descartar a tarefa")
def descartar_tarefa(n: int, confirmado: bool = False) -> str:
    """Fecha a tarefa n e remove o worktree. confirmado=true só depois de o usuário dizer sim."""
    return oficina.descartar(n, confirmado, orca=_orca(tarefas.obter(n)), repos=oficina.carregar_repos())


@mcp.tool()
@seguro("listar as tarefas")
def listar_tarefas() -> str:
    """Lista as tarefas abertas e as 10 últimas fechadas."""
    return oficina.frase_lista(tarefas.listar(), _agora())


if __name__ == "__main__":
    vigia.iniciar()      # um processo vigia; os outros esperam a trava e assumem se o dono morrer
    try:
        mcp.run()
    finally:
        vigia.parar()
