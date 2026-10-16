"""Pesquisa pelo OpenJarvis: agente gerenciado `vard-pesquisa` (deep_research com web_search e think).

T10: com `consulta = "delegada"` no pesquisa.toml, a pesquisa roda pelo agente de código do delegada.toml,
sem `/v1/managed-agents`; o caminho do OpenJarvis continua o padrão até o corte da T11.

Fluxo (OpenJarvis ccf02ec, server/agent_manager_routes.py; formatos reais em tests/fixtures/openjarvis/):
POST /v1/managed-agents cria o agente uma vez; POST /{id}/messages com mode=immediate dispara o trabalho em
segundo plano e responde na hora; a resposta aparece em GET /{id}/messages (da mais nova para a mais velha,
direction=agent_to_user, created_at em segundos float). Roda no trabalhador.
"""
from __future__ import annotations

import time
import tomllib
from pathlib import Path
from typing import Callable

import httpx

from vard import config, tarefas
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


def carregar_conf(caminho: Path | None = None) -> dict:
    alvo = Path(caminho) if caminho else config.arquivo_config("pesquisa.toml")
    if not alvo.exists():
        return {}
    with alvo.open("rb") as f:
        return tomllib.load(f)


def usa_consulta_delegada(conf: dict) -> bool:
    """Caminho novo (T10): só quando `consulta = "delegada"` está explícito no pesquisa.toml."""
    return str(conf.get("consulta", "")).strip().lower() == "delegada"


def consulta_delegada(n: int, arq: Path | None, t: tarefas.Tarefa, conf: dict, *, consultar=None) -> tarefas.Tarefa:
    """Pesquisa pelo agente de código do delegada.toml, sem `/v1/managed-agents` do OpenJarvis."""
    from vard import delegada
    try:
        conf_d = delegada.carregar()
        agente = delegada.normalizar_agente(str(conf.get("agente") or conf_d.padrao)) or conf_d.padrao
        s = (consultar or delegada.consultar)(agente, t.pedido, conf_d)
    except Exception as exc:  # noqa: BLE001 — agente desconhecido ou consulta indisponível: falha declarada
        frase = str(exc).strip() or type(exc).__name__
        return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou",
                                 resumo=frase[:200], erro=f"{type(exc).__name__}: {exc}"[:300])
    if s.estado != "terminou" or not s.texto.strip():
        return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou",
                                 resumo=(s.resumo or s.motivo or "a consulta delegada não respondeu")[:200],
                                 erro=(s.motivo or s.estado)[:300])
    arq_res = tarefas.arquivo_resultado(n)
    arq_res.write_text(s.texto, encoding="utf-8")
    return tarefas.atualizar(n, arq, se_estado="rodando", estado="terminou", resultado=str(arq_res),
                             resumo=s.resumo or tarefas.resumir(s.texto))


def executar(n: int, *, arq: Path | None = None, base: str = OPENJARVIS, dormir: Callable[[float], None] = time.sleep,
             espera_s: float = ESPERA_S, conf: dict | None = None, consultar=None) -> tarefas.Tarefa:
    t = tarefas.obter(n, arq)
    if t is None:
        raise KeyError(f"tarefa {n} não existe")
    if not tarefas.reivindicar(n, arq, se_estado="preparando", se_versao=t.versao):
        raise JaReivindicada(f"A pesquisa {n} já foi pega por outro trabalhador.")
    tarefas.atualizar(n, arq, se_estado="preparando", estado="rodando")
    conf = carregar_conf() if conf is None else conf
    if usa_consulta_delegada(conf):
        return consulta_delegada(n, arq, t, conf, consultar=consultar)
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
