"""Avisos da oficina: evento na ponte (o widget fala) e mensagem no Telegram (direto pela API do bot).

O POST /v1/channels/send do OpenJarvis está quebrado (passa "telegram" como destino), por isso o
Telegram vai direto. O token fica na URL da API: nenhuma exceção ou log daqui carrega a URL.
Nada aqui levanta para quem chama (a vigia segue mesmo com a ponte ou o Telegram fora).
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

import httpx

from vard import oficina, segredos, tarefas
from vard.oficina import NOMES

PONTE = "http://127.0.0.1:4700"
LMSTUDIO = "http://127.0.0.1:1234"
MODELO = "gemma-4-12b-it-qat@q4_k_xl"
LEMBRETE_ATA = "A ata contém fala de terceiros; avise os participantes que a reunião foi transcrita."
FALA = {"esperando": "está esperando sua resposta", "travou": "está parada há mais de 10 minutos",
        "terminou": "terminou", "falhou": "falhou"}
log = logging.getLogger("vard.avisos")
for _nome in ("httpx", "httpcore"):          # em INFO eles registram a URL do Telegram, que traz o token
    logging.getLogger(_nome).setLevel(logging.WARNING)
LIMITE_DOCUMENTO = 50 * 1024 * 1024          # teto do sendDocument do bot


def limpar_markdown(texto: str) -> str:
    """Tira a marcação para fala e Telegram em texto puro: negrito, itálico, código, títulos, listas e links."""
    t = str(texto)
    t = re.sub(r"```[a-zA-Z0-9_+-]*\n?", "", t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t, flags=re.S)
    t = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", t)
    t = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)", r"\1", t)
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", t)
    t = re.sub(r"(?m)^\s*(?:[-*+]|\d+\.)\s+", "", t)
    t = re.sub(r"(?m)^\s*>\s?", "", t)
    return t.replace("**", "").replace("`", "").strip()


def _com_resumo(base: str, resumo: str) -> str:
    r = " ".join(limpar_markdown(resumo).split())
    if not r:
        return f"{base}."
    return f"{base}: {r}" if r[-1] in ".!?" else f"{base}: {r}."


def _pasta_da_ata(t: tarefas.Tarefa) -> str:
    return re.split(r"[\\/]", t.repo.rstrip("\\/"))[-1]


def _data_da_pasta(t: tarefas.Tarefa) -> str:
    m = re.match(r"\d{4}-(\d{2})-(\d{2})", _pasta_da_ata(t))
    return f"{m.group(2)}/{m.group(1)}" if m else "?"


def _frase_delegada(t: tarefas.Tarefa) -> str:
    quem = NOMES.get(t.agente, "agente")
    if t.estado == "terminou":
        return _com_resumo(f"O {quem} respondeu", t.resumo)
    if t.estado == "esperando" and t.bloqueio == "login":
        if t.terminal:
            return f"A consulta {t.n} precisa que você entre no {quem}: responda no terminal, aba Vard #{t.n} no Orca."
        return f"A consulta {t.n} precisa que você entre no {quem}: abra um terminal e faça o login."
    if t.estado == "esperando":
        from vard import delegada           # tardio: ciclo de imports
        link = "; mandei o link no Telegram" if delegada.so_https(t.link) else ""
        return (f"O {quem} precisa que você {t.resumo or 'autorize o serviço'}{link}. "
                f"Depois diga: tenta de novo a consulta {t.n}.")
    return _com_resumo(f"Não consegui perguntar ao {quem}", t.resumo)


def frase(t: tarefas.Tarefa) -> str:
    if t.ferramenta == "delegada":
        return _frase_delegada(t)
    if t.ferramenta == "agente_remoto":
        from vard import remoto
        quem = remoto.nome()
        return _com_resumo(f"{quem.capitalize()} respondeu" if t.estado == "terminou" else f"Não consegui falar com {quem}", t.resumo)
    if t.ferramenta == "manha":
        if t.resumo == "A rotina da manhã não está configurada.":
            return t.resumo
        return "O resumo do dia está pronto." if t.estado == "terminou" else \
            _com_resumo("Não consegui montar o resumo do dia", t.resumo)
    if t.ferramenta == "ata":
        relatorio = t.pedido == "relatorio"
        if t.estado == "terminou":
            return (f"O relatório da reunião de {_data_da_pasta(t)} está pronto." if relatorio
                    else f"A ata da reunião de {_data_da_pasta(t)} está pronta.")
        return _com_resumo("Não consegui gerar o relatório" if relatorio else "Não consegui gerar a ata", t.resumo)
    if t.ferramenta == "pesquisa":
        return _com_resumo(f"A pesquisa {t.n} {FALA[t.estado]}", t.resumo)
    if t.estado == "esperando" and t.bloqueio:
        return f"A tarefa {t.n} no {NOMES[t.ferramenta]} precisa que você responda no Orca."
    return _com_resumo(f"A tarefa {t.n} no {NOMES[t.ferramenta]} {FALA[t.estado]}", t.resumo)


def _resultado(t: tarefas.Tarefa, limite: int) -> str:
    try:
        return limpar_markdown(Path(t.resultado).read_text(encoding="utf-8"))[:limite] if t.resultado else ""
    except OSError:
        return ""


def evento(t: tarefas.Tarefa) -> dict:
    if t.ferramenta == "ata":
        return {"tipo": "reuniao", "estado": "ata_pronta" if t.estado == "terminou" else "erro", "duracao_s": 0,
                "pasta": _pasta_da_ata(t), "resumo": frase(t)[:300]}
    ev = {"tipo": "tarefa", "n": t.n, "estado": t.estado, "resumo": frase(t)[:300], "ferramenta": t.ferramenta}
    if t.ferramenta == "manha" and t.estado == "terminou":
        ev["texto"] = _resultado(t, 3000)
    if t.ferramenta == "delegada":
        ev["agente"] = t.agente
    return ev


def _telegram_delegada(t: tarefas.Tarefa) -> str:
    from vard import delegada                   # tardio: a delegada importa a oficina, e esta importa avisos
    partes = [frase(t)]
    if t.estado == "terminou":
        limite = delegada.carregar().telegram_max
        linhas = _resultado(t, 10**6).splitlines()
        if linhas and linhas[0].lstrip().startswith("RESUMO:"):
            linhas = linhas[1:]
        corpo = "\n".join(linhas).strip()
        if corpo:
            partes.append(corpo[:limite])
            if len(corpo) > limite:
                partes.append(f'Texto completo: diga "resultado da tarefa {t.n}".')
    elif t.estado == "esperando" and delegada.so_https(t.link):
        partes.append(t.link)
    return "\n\n".join(partes)


def texto_telegram(t: tarefas.Tarefa) -> str:
    if t.ferramenta == "delegada":
        return _telegram_delegada(t)
    partes = [frase(t)]
    if t.ferramenta in ("agente_remoto", "pesquisa", "manha") and t.estado == "terminou":
        completo = _resultado(t, 3500)
        if completo:
            partes.append(completo)
    elif t.ferramenta in tarefas.AGENTES:
        partes.append(f"Detalhes: \"resultado da tarefa {t.n}\" ou a aba \"Vard #{t.n}\" no Orca.")
    return "\n\n".join(partes)


def publicar(ev: dict, *, base: str = PONTE) -> bool:
    try:
        return httpx.post(f"{base}/events/publicar", json=ev, timeout=3, trust_env=False).status_code == 200
    except httpx.HTTPError as exc:
        log.warning("ponte fora: %s", type(exc).__name__)
        return False


def telegram(texto: str, *, token: str, chat_id: str) -> bool:
    if not token or not chat_id:
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15, trust_env=False,
                       json={"chat_id": chat_id, "text": texto[:4000], "disable_web_page_preview": True})
        return r.status_code == 200 and r.json().get("ok") is True
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("telegram falhou: %s", type(exc).__name__)    # nunca a mensagem: ela traz a URL com o token
        return False


def telegram_documento(caminho: Path, legenda: str, *, token: str, chat_id: str) -> bool:
    if not token or not chat_id:
        return False
    try:
        if Path(caminho).stat().st_size > LIMITE_DOCUMENTO:
            return False
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendDocument", timeout=60, trust_env=False,
                       data={"chat_id": chat_id, "caption": legenda[:1000]},
                       files={"document": (Path(caminho).name, Path(caminho).read_bytes(), "application/pdf")})
        return r.status_code == 200 and r.json().get("ok") is True
    except (httpx.HTTPError, OSError, ValueError) as exc:
        log.warning("telegram documento falhou: %s", type(exc).__name__)    # nunca a mensagem: ela traz a URL com o token
        return False


def _enviar_ata(t: tarefas.Tarefa, token: str, chat_id: str) -> bool:
    """Ata pronta: o PDF vai como documento, com a frase e o lembrete na legenda. Sem PDF, cai na mensagem de texto."""
    legenda = f"{frase(t)}\n\n{LEMBRETE_ATA}"
    if t.estado == "terminou" and t.resultado and Path(t.resultado).is_file():
        if telegram_documento(Path(t.resultado), legenda, token=token, chat_id=chat_id):
            return True
        return telegram(f"{legenda} O PDF está em {t.resultado}.", token=token, chat_id=chat_id)
    return telegram(legenda if t.estado == "terminou" else frase(t), token=token, chat_id=chat_id)


def _conf_oficina() -> dict:
    """Seção [oficina] de config/oficina.toml; config ausente ou ilegível vira padrão."""
    try:
        c = oficina.carregar_conf().get("oficina", {})
        return c if isinstance(c, dict) else {}
    except Exception:  # noqa: BLE001 — não derruba o aviso
        return {}


def _telegram_permitido(t: tarefas.Tarefa, conf: dict) -> bool:
    modo = str(conf.get("telegram", "auto")).strip().lower()
    if modo == "nunca":
        return False
    if modo == "sempre" or t.origem == "telegram":
        return True
    if t.estado in ("esperando", "travou"):
        return True                      # precisam de gente: vão ao Telegram independentemente da duração
    try:
        duracao_s = (tarefas.hora(t.atualizada_em) - tarefas.hora(t.criada_em)).total_seconds()
    except (TypeError, ValueError):
        duracao_s = 0
    try:
        apos_min = int(conf.get("telegram_apos_min", 3))
    except (TypeError, ValueError):
        apos_min = 3
    return duracao_s > apos_min * 60


def avisar(t: tarefas.Tarefa) -> bool:
    ok_ponte = ok_tg = False
    try:
        ok_ponte = publicar(evento(t))
        dados = segredos.carregar()
        token, chat_id = segredos.chave_telegram(dados), segredos.chat_id_telegram(dados)
        conf = _conf_oficina()
        if _telegram_permitido(t, conf):
            if t.ferramenta == "ata":
                ok_tg = _enviar_ata(t, token, chat_id)
            else:
                ok_tg = telegram(texto_telegram(t), token=token, chat_id=chat_id)
    except Exception as exc:  # noqa: BLE001 — aviso que falha não derruba a vigia
        log.warning("aviso da tarefa %s falhou: %s", t.n, type(exc).__name__)
    log.info("aviso n=%s estado=%s ponte=%s telegram=%s", t.n, t.estado, ok_ponte, ok_tg)
    return ok_ponte or ok_tg      # False = não chegou a lugar nenhum: a vigia tenta de novo


def resumo_curto(texto: str, *, chave: str | None = None) -> str:
    """Uma frase falável. Tenta o Gemma local (sem raciocínio, 20 s); sem ele, a primeira frase."""
    if not str(texto).strip():
        return ""
    if chave is None:
        try:
            chave = segredos.chave_lmstudio()
        except FileNotFoundError:
            chave = ""
    try:
        r = httpx.post(f"{LMSTUDIO}/v1/chat/completions", timeout=20, trust_env=False,
                       headers={"Authorization": f"Bearer {chave}"} if chave else {},
                       json={"model": MODELO, "max_tokens": 80, "reasoning_effort": "none", "stream": False,
                             "messages": [{"role": "system", "content": "Resuma em UMA frase curta em português do "
                                                                        "Brasil, para ser falada. Sem markdown."},
                                          {"role": "user", "content": str(texto)[:6000]}]})
        frase_modelo = (r.json()["choices"][0]["message"].get("content") or "").strip()
        if r.status_code == 200 and frase_modelo:
            return tarefas.resumir(limpar_markdown(frase_modelo), 300)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        pass
    return tarefas.resumir(limpar_markdown(texto), 200)


carregar_conf = oficina.carregar_conf
