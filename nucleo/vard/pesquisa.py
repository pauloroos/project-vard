"""Pesquisa pelo OpenJarvis: agente gerenciado `vard-pesquisa` (deep_research com web_search e think).

Fluxo (OpenJarvis ccf02ec, server/agent_manager_routes.py; formatos reais em tests/fixtures/openjarvis/):
POST /v1/managed-agents cria o agente uma vez; POST /{id}/messages com mode=immediate dispara o trabalho em
segundo plano e responde na hora; a resposta aparece em GET /{id}/messages (da mais nova para a mais velha,
direction=agent_to_user, created_at em segundos float). Roda no trabalhador.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from vard import tarefas
from vard.oficina import JaReivindicada

OPENJARVIS = "http://127.0.0.1:8000"
NOME_AGENTE = "vard-pesquisa"
TIPO_AGENTE = "deep_research"          # conferido em 12/10 (web_search funcionou); reserva: "orchestrator"
CONFIG_AGENTE = {"tools": "web_search,think", "schedule_type": "manual"}
ESPERA_S = 900
INTERVALO_S = 10


def garantir_agente(c: httpx.Client) -> str:
    r = c.get("/v1/managed-agents")
    r.raise_for_status()
    for a in r.json().get("agents", []):
        if a.get("name") == NOME_AGENTE and a.get("status") != "archived":
            return str(a["id"])
    r = c.post("/v1/managed-agents", json={"name": NOME_AGENTE, "agent_type": TIPO_AGENTE, "config": CONFIG_AGENTE})
    r.raise_for_status()
    return str(r.json()["id"])


def resposta_depois(mensagens: list[dict], desde) -> str | None:
    """A resposta do agente mais antiga criada depois da pergunta (`desde`: o created_at da pergunta, no
    mesmo formato que a API usa; sem ele nada é aceito: uma resposta antiga não pode valer)."""
    if desde is None:
        return None
    candidatas = [m for m in mensagens if m.get("direction") == "agent_to_user"
                  and m.get("created_at") is not None and m["created_at"] > desde
                  and str(m.get("content", "")).strip()]
    return str(min(candidatas, key=lambda m: m["created_at"])["content"]) if candidatas else None


def executar(n: int, *, arq: Path | None = None, base: str = OPENJARVIS, dormir: Callable[[float], None] = time.sleep,
             espera_s: float = ESPERA_S) -> tarefas.Tarefa:
    t = tarefas.obter(n, arq)
    if t is None:
        raise KeyError(f"tarefa {n} não existe")
    if not tarefas.reivindicar(n, arq, se_estado="preparando", se_versao=t.versao):
        raise JaReivindicada(f"A pesquisa {n} já foi pega por outro trabalhador.")
    tarefas.atualizar(n, arq, se_estado="preparando", estado="rodando")
    with httpx.Client(base_url=base, timeout=30, trust_env=False) as c:
        aid = garantir_agente(c)
        r = c.post(f"/v1/managed-agents/{aid}/messages", json={"content": t.pedido, "mode": "immediate"})
        r.raise_for_status()
        desde = r.json().get("created_at")
        if desde is None:
            raise RuntimeError("o OpenJarvis não devolveu created_at da pergunta")
        fim = time.monotonic() + espera_s
        while time.monotonic() < fim:
            dormir(INTERVALO_S)
            resp = c.get(f"/v1/managed-agents/{aid}/messages")
            resp.raise_for_status()
            texto = resposta_depois(resp.json().get("messages", []), desde)
            if texto:
                arq_res = tarefas.arquivo_resultado(n)
                arq_res.write_text(texto, encoding="utf-8")
                return tarefas.atualizar(n, arq, se_estado="rodando", estado="terminou", resultado=str(arq_res),
                                         resumo=tarefas.resumir(texto))
    return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou", resumo="a pesquisa passou de 15 minutos sem resposta",
                             erro="timeout")
