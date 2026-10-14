"""Memória longa do Vard no ai-memory (VPS, pelo Tailscale), por um MCP fino (decisão D1).

Workspace e projeto vêm de memoria.toml na pasta de configuração do usuário, lidos na chamada: sem
projeto configurado nada é buscado nem gravado. A busca procura em todos os projetos (global=true;
os resultados vêm em `global_hits`).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import tomllib
from pathlib import Path

from vard import config, segredos
from vard.mcp_http import ClienteMCP, ErroMCP
from vard.oficina import simples, slug
from vard.seguro import Frase

SEM_CONFIG = "A memória não está configurada: falta o projeto em memoria.toml."
SEM_TOKEN = "A memória ainda não está ligada: falta o token do ai-memory no segredos.toml."
MAX_TITULO = 120
MAX_TEXTO = 4000
MARCA = re.compile(r"</?mark>")
VAZIAS = {"que", "sobre", "para", "por", "com", "como", "qual", "quais", "quando", "onde", "isso", "esse", "essa",
          "dos", "das", "nos", "nas", "uma", "foi", "vard", "voce", "lembra", "the", "and"}


def configurar(caminho: Path | None = None) -> tuple[str, str]:
    """(workspace, projeto) lidos de memoria.toml na chamada; sem o arquivo ou sem o projeto, a frase."""
    alvo = Path(caminho) if caminho else config.arquivo_config("memoria.toml")
    try:
        with alvo.open("rb") as f:
            dados = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        raise Frase(SEM_CONFIG) from None
    secao = dados.get("memoria")
    projeto = str(secao.get("projeto", "")).strip() if isinstance(secao, dict) else ""
    if not projeto:
        raise Frase(SEM_CONFIG)
    return str(secao.get("workspace", "")).strip() or "default", projeto


def consulta_fts(pergunta: str) -> str:
    """Pergunta falada -> expressão FTS5: palavras de 3+ letras com OR (sem aspas nem pontuação)."""
    palavras = [p for p in re.findall(r"[0-9A-Za-zÀ-ÿ]+", pergunta) if len(p) >= 3 and simples(p) not in VAZIAS]
    unicas = list(dict.fromkeys(palavras))[:8]
    return " OR ".join(unicas) if unicas else pergunta.strip()


def _json(texto: str) -> dict:
    try:
        dados = json.loads(texto)
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


def formatar_busca(dados: dict, limite: int = 5, projeto: str = "") -> str:
    hits = dados.get("global_hits") or dados.get("hits") or []
    if not hits:
        return "Não achei nada na memória sobre isso."
    linhas = []
    for h in hits[:limite]:
        trecho = " ".join(MARCA.sub("", str(h.get("snippet", ""))).split())[:240]
        onde = f"{h.get('project_name') or projeto}: {h.get('path', '')}"
        linhas.append(f"- {h.get('title') or h.get('path', '?')} [{onde}]: {trecho}")
    return "\n".join(linhas)


def cliente() -> ClienteMCP:
    configurar()                       # sem projeto configurado não há busca nem gravação (e nada de rede)
    url, token = segredos.ai_memory()
    if not url or not token:
        raise Frase(SEM_TOKEN)
    c = ClienteMCP(url, token)
    c.iniciar()
    return c


def buscar(c, pergunta: str) -> str:
    texto = c.chamar("memory_query", {"query": consulta_fts(pergunta), "global": True, "limit": 5})
    dados = _json(texto)
    return formatar_busca(dados) if dados else texto[:1500]


def ler(c, caminho: str, projeto: str = "") -> str:
    workspace, padrao = configurar()
    texto = c.chamar("memory_read_page", {"workspace": workspace, "project": projeto or padrao, "path": caminho})
    dados = _json(texto)
    if not dados:
        return texto[:3000]
    return f"{dados.get('title', caminho)}\n{str(dados.get('body', ''))[:3000]}"


def argumentos_gravacao(titulo: str, texto: str, hoje: dt.date, sufixo: int = 1, tags: list[str] | None = None) -> dict:
    workspace, projeto = configurar()
    fim = "" if sufixo <= 1 else f"-{sufixo}"
    return {"workspace": workspace, "project": projeto, "path": f"notes/{hoje:%Y-%m-%d}-{slug(titulo)}{fim}.md",
            "body": f"# {' '.join(titulo.split())}\n\n{texto.strip()}\n", "tags": list(tags) if tags else ["vard"]}


def _existe(c, caminho: str, workspace: str, projeto: str) -> bool:
    try:
        dados = _json(c.chamar("memory_read_page", {"workspace": workspace, "project": projeto, "path": caminho}))
    except ErroMCP:
        return False          # página inexistente (ou ai-memory fora: aí a gravação também falha e vira frase)
    return bool(dados.get("body") or dados.get("title"))


def gravar(c, titulo: str, texto: str, hoje: dt.date | None = None, tags: list[str] | None = None) -> str:
    workspace, projeto = configurar()   # sem projeto configurado, a frase — e nada é gravado
    if not titulo.strip() or not texto.strip():
        raise Frase("Diga o que anotar.")
    if len(titulo.strip()) > MAX_TITULO:
        raise Frase(f"O título está grande demais (máximo {MAX_TITULO} letras).")
    if len(texto.strip()) > MAX_TEXTO:
        raise Frase(f"O texto está grande demais (máximo {MAX_TEXTO} letras).")
    hoje = hoje or dt.date.today()
    for sufixo in range(1, 10):           # mesmo título no mesmo dia: -2, -3... nunca sobrescreve em silêncio
        args = argumentos_gravacao(titulo, texto, hoje, sufixo, tags)
        if not _existe(c, args["path"], workspace, projeto):
            break
    else:
        raise Frase("Já há muitas notas com esse título hoje; use outro título.")
    c.chamar("memory_write_page", args)
    return f"Anotei na memória: {' '.join(titulo.split())}."
