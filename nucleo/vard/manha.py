"""Rotina opcional da manhã: resumo do dia e consulta ao agente remoto."""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from vard import config, tarefas
from vard.oficina import JaReivindicada
from vard.segredos import PASTA

ULTIMA = PASTA / "manha-ultima.txt"
ESPERA_REMOTO_S = 60
OPENJARVIS = "http://127.0.0.1:8000"
SEM_GOOGLE = "Agenda: ainda não conectada."
log = logging.getLogger("vard.manha")


def carregar_conf(caminho: Path | None = None) -> dict:
    alvo = Path(caminho) if caminho else config.arquivo_config("manha.toml")
    if not alvo.exists():
        return {}
    with alvo.open("rb") as f:
        return tomllib.load(f)


def escrever_feeds(origem: Path | None, destino: Path) -> int:
    """config/noticias.toml -> <OPENJARVIS_HOME>/connectors/news_rss.json (formato do conector news_rss)."""
    with Path(origem or config.arquivo_config("noticias.toml")).open("rb") as f:
        feeds = tomllib.load(f).get("feeds", [])
    saida = []
    for fonte in feeds:
        url = str(fonte.get("url", "")).strip()
        if urlparse(url).scheme != "https" or not urlparse(url).netloc:
            raise ValueError(f"fonte sem https: {url!r}")
        saida.append({"name": str(fonte.get("nome") or urlparse(url).netloc), "url": url})
    if not saida:
        raise ValueError("noticias.toml sem fontes")
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"feeds": saida}, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(saida)


def _hm(texto: str) -> tuple[int, int]:
    h, m = str(texto).split(":")
    return int(h), int(m)


def deve_rodar(agora: dt.datetime, ultima: str, conf: dict) -> bool:
    if not conf or conf.get("ativo") is False:
        return False
    if agora.weekday() not in conf.get("dias", range(7)):
        return False
    if not _hm(conf.get("hora", "08:00")) <= (agora.hour, agora.minute) < _hm(conf.get("ate", "11:00")):
        return False
    return ultima != agora.date().isoformat()


def marcar_hoje(hoje: dt.date | None = None, arq: Path | None = None) -> None:
    alvo = Path(arq or ULTIMA)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text((hoje or dt.date.today()).isoformat(), encoding="ascii")


def agendar_se_preciso(agora: dt.datetime | None = None, *, conf: dict | None = None, ultima_arq: Path | None = None,
                       arq: Path | None = None, lancar=None) -> int | None:
    """Chamada pela vigia a cada volta. Grava o dia ANTES de lançar: nunca duas rotinas no mesmo dia."""
    agora = agora or dt.datetime.now()
    alvo = Path(ultima_arq or ULTIMA)
    try:
        ultima = alvo.read_text(encoding="ascii").strip() if alvo.exists() else ""
    except (OSError, ValueError):   # arquivo corrompido (bytes fora de ASCII): trata como "nunca rodou"
        ultima = ""
    if not deve_rodar(agora, ultima, carregar_conf() if conf is None else conf):
        return None
    marcar_hoje(agora.date(), alvo)
    t = tarefas.nova("manha", "", "rotina da manhã (agenda)", origem="agenda", arq=arq)
    if lancar is None:
        from vard import trabalhador
        lancar = trabalhador.lancar
    lancar(t.n)
    return t.n


def gerar_digest(base: str = OPENJARVIS, timeout: float = 600) -> str:
    r = httpx.post(f"{base}/api/digest/generate", timeout=timeout, trust_env=False)
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()


def google_conectado(home: Path | None = None) -> bool:
    """O `jarvis connect gmail` grava o token em <OPENJARVIS_HOME>/connectors. Sem ele, só notícias e agente remoto."""
    import os
    raiz = Path(home or os.environ.get("OPENJARVIS_HOME", ""))
    return any((raiz / "connectors" / nome).exists() for nome in ("google.json", "gmail.json"))


def montar_texto(digest: str, remoto: str, *, remoto_pedido: bool = False, google: bool = True) -> str:
    partes = [digest.strip() or "Não consegui montar o resumo do dia."]
    if not google:
        partes.append(SEM_GOOGLE)
    if remoto.strip():
        partes.append("Do agente remoto: " + " ".join(remoto.split())[:1200])
    elif remoto_pedido:
        partes.append("Do agente remoto: não consegui falar com ele agora.")
    return "\n\n".join(partes)


def executar(n: int, *, arq: Path | None = None, conf: dict | None = None, gerar=None,
             perguntar_remoto=None) -> tarefas.Tarefa:
    conf = carregar_conf() if conf is None else conf
    t = tarefas.obter(n, arq)
    if t is None:
        raise KeyError(f"tarefa {n} não existe")
    if not tarefas.reivindicar(n, arq, se_estado="preparando", se_versao=t.versao):
        raise JaReivindicada(f"A tarefa da manhã {n} já foi pega por outro trabalhador.")
    tarefas.atualizar(n, arq, se_estado="preparando", estado="rodando")
    if not conf or conf.get("ativo") is False:
        return tarefas.atualizar(n, arq, se_estado="rodando", estado="terminou",
                                 resumo="A rotina da manhã não está configurada.")
    da_remoto: list[str] = []
    fio = None
    if conf.get("perguntar_remoto"):
        if perguntar_remoto is None:
            from vard import remoto
            # Consulta opcional usa a mesma trava exclusiva das demais conversas remotas.
            perguntar_remoto = lambda pedido: remoto.perguntar_com_trava(pedido, espera=ESPERA_REMOTO_S)  # noqa: E731

        def _remoto() -> None:
            try:
                da_remoto.append(perguntar_remoto(str(conf["pedido_remoto"])))
            except Exception as exc:  # noqa: BLE001 — a manhã sai sem o agente remoto, mas sai
                log.warning("manhã sem o agente remoto: %s", type(exc).__name__)

        fio = threading.Thread(target=_remoto, daemon=True)
        fio.start()
    try:
        digest = (gerar or gerar_digest)()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("digest falhou: %s", type(exc).__name__)
        digest = ""
    if fio:
        fio.join(timeout=660)
    res = tarefas.arquivo_resultado(n)
    res.write_text(montar_texto(digest, da_remoto[0] if da_remoto else "", remoto_pedido=bool(conf.get("perguntar_remoto")),
                                google=google_conectado()), encoding="utf-8")
    if not digest and not da_remoto:
        return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou", resultado=str(res),
                                 resumo="nem o resumo do dia nem o agente remoto responderam")
    return tarefas.atualizar(n, arq, se_estado="rodando", estado="terminou", resultado=str(res),
                             resumo="O resumo do dia está pronto.")
