"""MCP de consulta: GitHub, deploys, relatórios e agente remoto. Só leitura; transporte stdio.

Toda ferramenta devolve uma frase em português e nunca levanta (mesmo contrato da mesa). O agente remoto é uma
tarefa assíncrona (trabalhador + vigia), como a pesquisa; a vigia sobe no __main__.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

import datetime as dt

from vard import config, consulta, delegada, manha, oficina, remoto, segredos, tarefas, trabalhador, vigia
from vard.seguro import seguro

mcp = MCPServer("consulta")


def _pedir_remoto(pedido: str, origem: str = "voz") -> tarefas.Tarefa:
    remoto.carregar_conf()
    t = tarefas.nova("agente_remoto", "", " ".join(pedido.split()), origem=origem)
    trabalhador.lancar(t.n)
    return t


@mcp.tool()
@seguro("ver os PRs")
def github_prs(repo: str = "") -> str:
    """PRs abertos no GitHub; repo vazio = os projetos da oficina."""
    repos = oficina.carregar_repos()
    if not repos:
        return "A consulta do GitHub não está configurada; cadastre os projetos em repos.toml."
    return consulta.github("pr", repo, repos=repos, dono=oficina.dono_github())


@mcp.tool()
@seguro("ver as issues")
def github_issues(repo: str = "") -> str:
    """Issues abertas no GitHub; repo vazio = os projetos da oficina."""
    repos = oficina.carregar_repos()
    if not repos:
        return "A consulta do GitHub não está configurada; cadastre os projetos em repos.toml."
    return consulta.github("issue", repo, repos=repos, dono=oficina.dono_github())


@mcp.tool()
@seguro("ver os deploys")
def deploys() -> str:
    """Estado dos apps nos painéis Coolify configurados e deploys em andamento."""
    arq = config.arquivo_segredos()
    paineis = segredos.coolify(segredos.carregar(arq) if arq.exists() else {})
    return consulta.deploys(paineis)   # vazio: a própria consulta avisa e ainda consulta a Vercel


@mcp.tool()
@seguro("pegar o relatório")
def relatorio(nome: str) -> str:
    """Gera ou pede um relatório pelo nome (ex.: uso de IA)."""
    relatorios = consulta.carregar_relatorios()
    if not relatorios:
        return "A consulta de relatórios não está configurada."
    nome_ok, rel = consulta.achar_relatorio(nome, relatorios)
    # Adaptador legado, somente leitura: tipo liv também solicita o agente remoto.
    if rel.get("tipo") in ("agente_remoto", "liv"):
        t = _pedir_remoto(str(rel["pedido"]))
        return f"Pedi para {remoto.nome()} o relatório {nome_ok} (pedido {t.n}); aviso quando chegar."
    return consulta.gerar_local(nome_ok, rel)


@mcp.tool()
@seguro("falar com o agente remoto")
def agente_remoto(pedido: str) -> str:
    """Pergunta ao agente remoto; a resposta chega depois pela central de avisos e canais configurados."""
    if not pedido.strip():
        return f"Diga o que perguntar para {remoto.nome()}."
    t = _pedir_remoto(pedido)
    return f"Perguntei para {remoto.nome()} (pedido {t.n}); aviso quando responder."


@mcp.tool()
@seguro("perguntar ao agente")
def delegar(agente: str = "", pergunta: str = "", modelo: str = "") -> str:
    """Pergunta a claude, codex, agy ou opencode (Linear, agenda); modelo só do Claude: sonnet, opus, fable. Resposta vem depois."""
    try:
        conf = delegada.carregar()          # só quando usada: um TOML ruim não derruba as outras ferramentas
    except ValueError:
        return "A configuração da consulta delegada está com erro; veja config/delegada.toml."
    t, repetida = delegada.registrar(agente, pergunta, conf=conf, agora=dt.datetime.now().astimezone(),
                                     modelo=modelo)
    if not repetida:
        trabalhador.lancar(t.n)
    return delegada.frase_registro(t, repetida)


@mcp.tool()
@seguro("começar a rotina da manhã")
def rotina_manha() -> str:
    """Monta o resumo do dia (agenda, notícias, agente remoto). Use no bom dia, vamos começar o dia."""
    manha.marcar_hoje()                  # a agenda das 8h não repete hoje
    t = tarefas.nova("manha", "", "rotina da manhã (voz)")
    trabalhador.lancar(t.n)
    return "Montando o resumo do dia; leio assim que ficar pronto."


if __name__ == "__main__":
    from vard.instalaveis import limpar_ambiente_mcp
    limpar_ambiente_mcp()
    vigia.iniciar()      # a vigia é única (trava); quem sobe primeiro cuida dos avisos
    try:
        mcp.run()
    finally:
        vigia.parar()
