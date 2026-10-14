"""Consultas só de leitura: GitHub (gh), deploys (Coolify e Vercel) e relatórios do relatorios.toml."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import httpx

from vard import config
from vard.oficina import Repo, resolver_repo, simples
from vard.seguro import Frase

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CAMPOS_PR = "number,title,isDraft,updatedAt,url"
CAMPOS_ISSUE = "number,title,updatedAt,url"
PALAVRAS = {"pr": ("PR", "Nenhum PR aberto", "PR(s) aberto(s)"),
            "issue": ("issue", "Nenhuma issue aberta", "issue(s) aberta(s)")}


class ErroConsulta(Frase):
    """Falha que vira frase para o usuário."""


def _motivo(args: list[str], saida: str) -> str:
    """Frase curta para o erro de um comando; nunca devolve a saída crua inteira."""
    baixo = saida.lower()
    if args and args[0] == "gh":
        if any(k in baixo for k in ("auth login", "bad credentials", "http 401", "not logged", "gh_token")):
            return "O gh não está logado (rode gh auth login)."
        if "could not resolve host" in baixo or "timeout" in baixo or "dial tcp" in baixo:
            return "O gh não conseguiu falar com o GitHub (rede)."
        if "not found" in baixo or "http 404" in baixo:
            return "O GitHub não achou esse repositório."
        if "rate limit" in baixo:
            return "O GitHub limitou as consultas; tente daqui a pouco."
    return f"O {args[0]} falhou: {' '.join(saida.split())[:120]}"


def rodar(args: list[str], timeout: float = 30) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
    except FileNotFoundError:
        raise ErroConsulta(f"O {args[0]} não está instalado neste PC.") from None
    except subprocess.TimeoutExpired:
        raise ErroConsulta(f"O {args[0]} demorou mais de {timeout:.0f} s.") from None
    if p.returncode != 0:
        raise ErroConsulta(_motivo(args, p.stderr or p.stdout or ""))
    return p.stdout


def _repo_github(falado: str, repos: dict[str, Repo]) -> Repo | None:
    if not falado.strip():
        return None
    r = resolver_repo(falado, repos)
    if not r:
        raise ErroConsulta(f"Não conheço o projeto '{falado}'. Conheço: {', '.join(sorted(repos))}.")
    if not r.github:
        raise ErroConsulta(f"O {r.apelido} não está no GitHub.")
    return r


def comando_gh(tipo: str, repo: Repo) -> list[str]:
    """tipo 'pr' ou 'issue'. Sempre de UM repositório do repos.toml: nada de `gh search` pelo dono inteiro, que
    pegaria repositórios públicos onde qualquer pessoa abre issue (texto de terceiro entrando no modelo)."""
    campos = CAMPOS_PR if tipo == "pr" else CAMPOS_ISSUE
    return ["gh", tipo, "list", "-R", repo.github, "--state", "open", "--limit", "10", "--json", campos]


def frase_itens(itens: list[dict], tipo: str, onde: str) -> str:
    _, nenhum, plural = PALAVRAS[tipo]
    if not itens:
        return f"{nenhum} {onde}."
    linhas = []
    for i in itens[:10]:
        repo = (i.get("repository") or {}).get("name", "")
        rascunho = " (rascunho)" if i.get("isDraft") else ""
        linhas.append(f"- {repo + ' ' if repo else ''}#{i.get('number')} {i.get('title', '')}{rascunho}")
    return f"{len(itens)} {plural} {onde}:\n" + "\n".join(linhas)


def _itens(tipo: str, r: Repo, rodar_fn) -> list[dict]:
    bruto = rodar_fn(comando_gh(tipo, r)) or "[]"
    try:
        itens = json.loads(bruto)
    except ValueError:
        raise ErroConsulta("O gh devolveu uma resposta estranha; não consegui ler.") from None
    return itens if isinstance(itens, list) else []


def github(tipo: str, falado: str, *, repos: dict[str, Repo], dono: str = "", rodar_fn=None) -> str:
    """Um projeto, ou (vazio) todos os do repos.toml que estão no GitHub, um `gh <tipo> list -R` por projeto."""
    rodar_fn = rodar_fn or rodar
    r = _repo_github(falado, repos)
    if r:
        return frase_itens(_itens(tipo, r, rodar_fn), tipo, f"no {r.apelido}")
    todos: list[dict] = []
    for alvo in repos.values():
        if alvo.github:
            todos += [{**i, "repository": {"name": alvo.apelido}} for i in _itens(tipo, alvo, rodar_fn)]
    return frase_itens(todos, tipo, "nos projetos da oficina")


def coolify_get(url: str, token: str, rota: str) -> list[dict]:
    """GET /api/v1/<rota> (applications, services, deployments). Campos a conferir com o token real (passo P2)."""
    with httpx.Client(timeout=15, trust_env=False) as c:
        r = c.get(f"{url}/api/v1/{rota}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise ErroConsulta("o token do Coolify foi recusado")
    r.raise_for_status()
    dados = r.json()
    return dados if isinstance(dados, list) else list(dados.get("data", []))


def saudavel(status: str) -> bool:
    s = str(status).lower()
    return s.startswith("running") and "unhealthy" not in s


def resumir_coolify(nome: str, itens: list[dict], em_andamento: list[dict]) -> str:
    fora = [f"{i.get('name', '?')} ({i.get('status', '?')})" for i in itens if not saudavel(i.get("status", ""))]
    partes = [f"Coolify {nome}: {len(itens)} apps e serviços",
              "todos no ar" if not fora else f"{len(fora)} fora do normal: " + ", ".join(fora[:6])]
    if em_andamento:
        nomes = ", ".join(str(d.get("application_name") or d.get("name") or "?") for d in em_andamento[:5])
        partes.append(f"{len(em_andamento)} deploy(s) em andamento: {nomes}")
    return "; ".join(partes) + "."


def vercel_resumo(exe: str) -> str:
    if not exe:
        return "Vercel: a CLI não está instalada neste PC."
    linhas = [l for l in rodar([exe, "ls"], timeout=60).splitlines() if l.strip()]   # conferir `vercel ls --help` ao instalar
    return "Vercel:\n" + "\n".join(linhas[:6])


def deploys(paineis: dict[str, dict], *, vercel: str | None = None, get=None) -> str:
    get = get or coolify_get
    frases = []
    if not paineis:
        frases.append("Coolify: sem a seção [coolify] no segredos.toml (precisa de url e token por painel: "
                      "deploy\\gravar-segredo.ps1 -Secao coolify.exemplo -Chave url -Visivel, depois -Chave token).")
    for nome, p in paineis.items():
        falta = [c for c in ("url", "token") if not p.get(c)]
        if falta:
            frases.append(f"Coolify {nome}: falta {' e '.join(falta)} em [coolify.{nome}] no segredos.toml "
                          f"(deploy\\gravar-segredo.ps1 -Secao coolify.{nome} -Chave {falta[0]}).")
            continue
        try:
            itens = get(p["url"], p["token"], "applications") + get(p["url"], p["token"], "services")
            frases.append(resumir_coolify(nome, itens, get(p["url"], p["token"], "deployments")))
        except ErroConsulta as exc:
            frases.append(f"Coolify {nome}: {exc}.")
        except (httpx.HTTPError, ValueError) as exc:
            frases.append(f"Coolify {nome}: não respondeu ({type(exc).__name__}).")
    try:
        frases.append(vercel_resumo((shutil.which("vercel") or "") if vercel is None else vercel))
    except ErroConsulta as exc:
        frases.append(f"Vercel: {exc}")
    return "\n".join(frases)


def carregar_relatorios(caminho: Path | None = None) -> dict[str, dict]:
    alvo = Path(caminho) if caminho else config.arquivo_config("relatorios.toml")
    if not alvo.exists():
        return {}
    with alvo.open("rb") as f:
        return tomllib.load(f)


def achar_relatorio(falado: str, relatorios: dict[str, dict]) -> tuple[str, dict]:
    alvo = simples(falado)
    for nome, rel in relatorios.items():
        if alvo in {simples(nome), *(simples(a) for a in rel.get("apelidos", []))}:
            return nome, rel
    if not relatorios:
        raise ErroConsulta(f"Ainda não conheço esse relatório ('{falado}'): nenhum está cadastrado em relatorios.toml.")
    raise ErroConsulta(f"Não conheço esse relatório ('{falado}'). Conheço: {', '.join(sorted(relatorios))}.")


def gerar_local(nome: str, rel: dict, *, rodar_fn=None, abrir=None) -> str:
    (rodar_fn or rodar)([str(a) for a in rel["comando"]], timeout=120)
    pdf = Path(rel["pdf"])
    if not pdf.exists():
        raise ErroConsulta(f"O relatório {nome} rodou, mas o PDF não apareceu em {pdf}.")
    (abrir or os.startfile)(str(pdf))
    return f"Abri o relatório {nome}."



def relatorio(falado: str, *, relatorios: dict[str, dict] | None = None) -> str:
    """Consulta um relatório cadastrado, com integração remota opcional."""
    relatorios = carregar_relatorios() if relatorios is None else relatorios
    if not relatorios:
        return "A consulta de relatórios não está configurada."
    nome, rel = achar_relatorio(falado, relatorios)
    # Adaptador legado, somente leitura: tipo liv equivale a agente_remoto.
    if rel.get("tipo") in ("agente_remoto", "liv"):
        from vard import remoto
        try:
            return remoto.perguntar_com_trava(str(rel.get("pedido", "")))
        except ErroConsulta as exc:
            return str(exc)
    if rel.get("tipo") == "comando":
        return gerar_local(nome, rel)
    raise ErroConsulta(f"O tipo do relatório {nome} não está configurado.")
