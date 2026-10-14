"""Leitura de segredos e geração do mcp.json do OpenJarvis.

Os segredos ficam fora do repositório, em %LOCALAPPDATA%\\rdl-vard\\segredos.toml.
Nada aqui imprime valores.
"""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

import tomli_w

from vard import config as _config

PASTA = _config.pasta_dados()
ARQUIVO: Path | None = None  # Sobrescrita explícita; padrão resolvido na chamada.

def carregar(caminho: Path | None = None) -> dict:
    arq = caminho or ARQUIVO or _config.arquivo_segredos()
    if not arq.exists():
        raise FileNotFoundError(
            f"segredos.toml não encontrado em {arq}. Copie segredos.example.toml para lá."
        )
    with arq.open("rb") as f:
        return tomllib.load(f)


def chave_omniroute(segredos: dict | None = None) -> str:
    dados = segredos or carregar()
    return str(dados.get("omniroute", {}).get("chave", ""))


def url_omniroute(segredos: dict | None = None) -> str:
    """URL do roteador em [omniroute] url; segredos.toml ausente = integração não configurada."""
    if segredos is None:
        arq = _config.arquivo_segredos()
        dados = carregar(arq) if arq.exists() else {}
    else:
        dados = segredos
    return str(dados.get("omniroute", {}).get("url", ""))


def chave_lmstudio(segredos: dict | None = None) -> str:
    dados = segredos or carregar()
    return str(dados.get("lmstudio", {}).get("chave", ""))


def chave_telegram(segredos: dict | None = None) -> str:
    dados = segredos or carregar()
    return str(dados.get("telegram", {}).get("token", ""))


def chat_id_telegram(segredos: dict | None = None) -> str:
    dados = carregar() if segredos is None else segredos
    return str(dados.get("telegram", {}).get("chat_id", ""))


def huggingface(segredos: dict | None = None) -> str:
    dados = carregar() if segredos is None else segredos
    return str(dados.get("huggingface", {}).get("token", ""))


def gravar(secao: str, chave: str, valor: str, arq: Path | None = None) -> None:
    """Grava ou troca uma chave sem apagar o resto (seção com ponto: 'coolify.exemplo'). Nunca imprime."""
    alvo = Path(arq) if arq else ARQUIVO or _config.arquivo_segredos()
    dados = carregar(alvo) if alvo.exists() else {}
    no = dados
    for parte in secao.split("."):
        no = no.setdefault(parte, {})
        if not isinstance(no, dict):
            raise ValueError(f"{secao} não é uma seção")
    no[chave] = valor
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(tomli_w.dumps(dados), encoding="utf-8")
    os.replace(tmp, alvo)


def _dados(segredos: dict | None) -> dict:
    return carregar() if segredos is None else segredos


def coolify(segredos: dict | None = None) -> dict[str, dict]:
    return {nome: {"url": str(c.get("url", "")).rstrip("/"), "token": str(c.get("token", ""))}
            for nome, c in _dados(segredos).get("coolify", {}).items() if isinstance(c, dict)}


def remoto_ssh(segredos: dict | None = None) -> tuple[str, str]:
    if segredos is None:
        arq = _config.arquivo_segredos()
        dados = carregar(arq) if arq.exists() else {}
    else:
        dados = segredos
    # Adaptador legado, somente leitura: [liv] apenas quando [remoto] não existe.
    remoto = dados["remoto"] if "remoto" in dados else dados.get("liv", {})
    return str(remoto.get("ssh_chave", "")), str(remoto.get("ssh_destino", ""))


def ai_memory(segredos: dict | None = None) -> tuple[str, str]:
    mem = _dados(segredos).get("ai_memory", {})
    return str(mem.get("url", "")), str(mem.get("token", ""))


def google(segredos: dict | None = None) -> tuple[str, str]:
    g = _dados(segredos).get("google", {})
    return str(g.get("client_id", "")), str(g.get("client_secret", ""))


# MCPs locais (stdio) que o OpenJarvis sobe.
SERVIDORES_LOCAIS = ("mesa", "oficina", "consulta", "memoria", "reuniao")


def escrever_mcp_json(segredos: dict, repo: Path, destino: Path) -> Path:
    """Gera a lista de servidores MCP que o OpenJarvis vai carregar.

    Só os servidores locais; o mcp.json nunca leva token (o memoria_mcp lê o ai-memory do segredos.toml).
    Caminhos são absolutos porque o stdio do OpenJarvis não define pasta de trabalho.
    """
    repo = Path(repo)
    servidores: list[dict] = [
        {"name": nome, "command": "uv", "args": ["run", "--project", str(repo), "python", str(repo / f"{nome}_mcp.py")]}
        for nome in SERVIDORES_LOCAIS
    ]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(servidores, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino
