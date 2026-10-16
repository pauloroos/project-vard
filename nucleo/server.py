"""Ponte do Vard: serve a aba e encaminha texto ao OpenJarvis e imagens ao LM Studio.

Só 127.0.0.1:4700. Persona num bloco só. Histórico curto aqui; memória longa no OpenJarvis.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import logging
import os
import re
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from vard import avisos as vavisos, central, config, modelos, modo, oficina, perfil, reuniao, segredos, tarefas
from vard.cerebro import contratos as cerebro_contratos, pedidos as cerebro_pedidos
from vard.primeiro_uso import deteccao as primeiro_uso_deteccao, estado as primeiro_uso_estado
from vard.seguro import Frase
from vard import telegram as telegram_mod

# ----------------------------------------------------------------------------- PERSONA
# Único lugar da personalidade: config/persona.md do usuário (a ponte e o OpenJarvis/Telegram
# leem o mesmo arquivo). Sem o arquivo, o exemplo do repositório serve de base.
# Reescreva lá, nunca aqui.
RAIZ = Path(__file__).resolve().parent
EXEMPLO_PERSONA = RAIZ.parent / "config" / "examples" / "persona.example.md"


def _persona() -> str:
    try:
        return config.arquivo_config("persona.md").read_text(encoding="utf-8")
    except OSError:
        return EXEMPLO_PERSONA.read_text(encoding="utf-8")
# -------------------------------------------------------------------------------------

INSTRUCAO_VISAO = """Você vê UM quadro da tela do usuário, capturado agora. Responda em
português, manchete primeiro, em até três frases, sobre o que está na tela. Se o quadro
estiver pequeno ou ilegível, diga isso em vez de chutar."""

MODELO_LOCAL = "gemma-4-12b-it-qat@q4_k_xl"
MODELO_NUVEM = "combo/t1-work"
OPENJARVIS = os.environ.get("VARD_OPENJARVIS_URL", "http://127.0.0.1:8000")
LMSTUDIO = os.environ.get("VARD_LMSTUDIO_URL", "http://127.0.0.1:1234")
REUNIAO = "http://127.0.0.1:4720"
HISTORICO_MAX = 10
HISTORICO: list[dict] = []

VIEWER = RAIZ / "viewer"

log = logging.getLogger("vard")


def _chave_lmstudio() -> str:
    try:
        return segredos.chave_lmstudio()
    except FileNotFoundError:
        return ""


CHAVE_LMSTUDIO = _chave_lmstudio()
@asynccontextmanager
async def lifespan(app):
    """Ciclo de vida: inicia/para o TelegramPoller condicional (T11)."""
    poller = None
    tarefa_poller = None
    if telegram_mod.deve_iniciar_poller():
        cfg = telegram_mod._ler_config_telegram()
        token = telegram_mod._token_seguro(cfg)
        chats = telegram_mod._chats_permitidos(cfg)
        if token and chats:
            poller = telegram_mod.TelegramPoller(token=token, chats_permitidos=chats)
            async def _loop():
                while True:
                    try:
                        await poller.processar_updates()
                    except Exception:  # noqa: BLE001
                        log.warning("erro no loop do telegram poller")
                    await asyncio.sleep(telegram_mod.POLL_INTERVAL_PADRAO)
            tarefa_poller = asyncio.create_task(_loop())
            log.info("telegram poller iniciado (chats=%d)", len(chats))
        else:
            log.info("telegram habilitado mas sem token/chats; poller nao iniciado")
    else:
        log.info("telegram desabilitado; poller nao iniciado")
    yield
    if tarefa_poller is not None:
        tarefa_poller.cancel()
        try:
            await tarefa_poller
        except asyncio.CancelledError:
            pass
        log.info("telegram poller parado")


app = FastAPI(title="Vard", lifespan=lifespan)


def _erro(exc: modelos.ErroModelo) -> JSONResponse:
    # O detalhe técnico fica no log da ponte; a aba recebe só o código curto.
    log.warning("erro de modelo %s: %s", exc.codigo, exc.detalhe)
    return JSONResponse({"erro": exc.codigo}, status_code=503)


# 4700: a aba do navegador. tauri.localhost / localhost:1420: o webview do vard (produção / dev).
ORIGENS_OK = {
    "http://127.0.0.1:4700", "http://localhost:4700",
    "http://tauri.localhost", "http://localhost:1420",
}


@app.middleware("http")
async def so_localhost(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    if host not in {"127.0.0.1", "localhost"}:
        return JSONResponse({"erro": "Só localhost."}, status_code=421)
    origem = request.headers.get("origin")
    if origem and origem not in ORIGENS_OK:
        return JSONResponse({"erro": "origem_recusada"}, status_code=403)
    return await call_next(request)


# Por último = camada de fora: responde o preflight e põe o ACAO até na 403, para o webview ler a resposta.
app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGENS_OK), allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/")
def raiz():
    return FileResponse(VIEWER / "index.html")


@app.get("/segredos.toml")
def segredos_bloqueado():
    raise HTTPException(404)


@app.post("/ask")
def ask(corpo: dict):
    texto = str(corpo.get("texto", "")).strip()
    if not texto:
        raise HTTPException(422, "texto vazio")
    if _reuniao_ativa() and not reuniao.e_encerramento(texto):
        return {"resposta": "", "muda": True}      # reunião em andamento: a Vard fica muda (só o encerramento passa)
    mensagens = [{"role": "system", "content": _persona()}, *HISTORICO, {"role": "user", "content": texto}]
    try:
        resposta = modelos.perguntar_openjarvis(mensagens, base=OPENJARVIS, modelo=MODELO_LOCAL)
    except modelos.ErroModelo as exc:
        return _erro(exc)
    HISTORICO.extend([{"role": "user", "content": texto}, {"role": "assistant", "content": resposta}])
    del HISTORICO[: max(0, len(HISTORICO) - HISTORICO_MAX * 2)]
    return {"resposta": resposta}


@app.post("/see")
def see(imagem: UploadFile = File(...), pergunta: str = Form("O que está na tela?")):
    if imagem.content_type != "image/jpeg":
        raise HTTPException(422, "mande image/jpeg")
    b64 = base64.b64encode(imagem.file.read()).decode()
    cuidado = "com mais cuidado" in pergunta.lower()
    try:
        if cuidado:
            url = segredos.url_omniroute()
            if not url:
                return _erro(modelos.ErroModelo("segredos", "visão em nuvem não configurada"))
            resposta = modelos.ver_imagem(
                b64, pergunta, base=url, modelo=MODELO_NUVEM, instrucao=INSTRUCAO_VISAO,
                chave=segredos.chave_omniroute(),
            )
        else:
            resposta = modelos.ver_imagem(
                b64, pergunta, base=LMSTUDIO, modelo=MODELO_LOCAL, instrucao=INSTRUCAO_VISAO,
                chave=CHAVE_LMSTUDIO,
            )
    except FileNotFoundError:
        return _erro(modelos.ErroModelo("segredos", "segredos.toml não encontrado"))
    except modelos.ErroModelo as exc:
        return _erro(exc)
    return {"resposta": resposta, "nuvem": cuidado}


def _tarefas_abertas() -> int:
    try:
        return sum(1 for t in tarefas.listar() if t.aberta)
    except (OSError, ValueError, TimeoutError):
        return 0


def _reuniao_ativa() -> bool:
    """GET /status do 4720 (1 s). Qualquer falha conta como não ativa: a ponte segue normal."""
    try:
        return bool(httpx.get(f"{REUNIAO}/status", timeout=1, trust_env=False).json().get("ativa"))
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


async def _sondar_reuniao() -> str:
    """Sonda assíncrona ao serviço de reunião com timeout de 2 s."""
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            r = await client.get(f"{REUNIAO}/status")
            return "ativa" if r.json().get("ativa") else "inativa"
    except (httpx.HTTPError, ValueError, AttributeError):
        return "ausente"


async def _sondar_openjarvis() -> bool:
    """Sonda assíncrona ao OpenJarvis com timeout de 2 s."""
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            r = await client.get(f"{OPENJARVIS}/health")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def _sondar_lmstudio() -> tuple[bool, list[str], str]:
    """Sonda assíncrona ao LM Studio com timeout de 2 s; devolve (ok, ids, modelo)."""
    try:
        cab = {"Authorization": f"Bearer {CHAVE_LMSTUDIO}"} if CHAVE_LMSTUDIO else {}
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            r = await client.get(f"{LMSTUDIO}/v1/models", headers=cab)
            if r.status_code != 200:
                return False, [], ""
            dados = r.json().get("data", [])
            ids = [m["id"] for m in dados]
            modelo = MODELO_LOCAL if MODELO_LOCAL in ids else (ids[0] if ids else "")
            return True, ids, modelo
    except (httpx.HTTPError, ValueError, AttributeError, KeyError, TypeError):
        return False, [], ""


@app.get("/status")
async def status():
    ok_oj, (ok_lm, ids, modelo), reuniao = await asyncio.gather(
        _sondar_openjarvis(), _sondar_lmstudio(), _sondar_reuniao()
    )
    return {"openjarvis": ok_oj, "lmstudio": ok_lm, "modelo": modelo, "modo": modo.ler_estado()["modo"],
            "modelos_lmstudio": ids, "tarefas_abertas": _tarefas_abertas(), "reuniao": reuniao,
            "cerebro": {"ativo": False, "provedor": "", "sessoes": 0}}


# ----------------------------------------------------------------------------- PRIMEIRO USO (T1)
# Detecção local somente-leitura: reconhece ferramentas já instaladas sem iniciar serviço,
# fazer login ou carregar modelo. `item`+`caminho` permitem apontar o executável no painel.
@app.get("/primeiro-uso/deteccao")
def primeiro_uso_deteccao_rota(item: str = "", caminho: str = ""):
    caminhos = {item: caminho} if item and caminho and item in primeiro_uso_deteccao.IDS else None
    return primeiro_uso_deteccao.detectar(caminhos=caminhos).como_dict()


# ----------------------------------------------------------------------------- PEDIDOS (T6)
# Rotas do cérebro próprio: admissão, consulta, cancelamento e listagem por sessão.
# O cérebro só atende quando explicitamente escolhido; /ask continua via OpenJarvis.

@app.post("/pedidos", status_code=202)
async def pedidos_admitir(corpo: dict):
    """Admite um pedido no cérebro próprio. Devolve 202 antes da conclusão."""
    try:
        pedido = cerebro_contratos.Pedido(
            pedido_id=str(corpo["pedido_id"]),
            sessao_id=str(corpo["sessao_id"]),
            origem=cerebro_contratos.Origem(str(corpo.get("origem", "painel"))),
            texto=str(corpo.get("texto", "")).strip(),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    if not pedido.texto:
        raise HTTPException(422, "texto vazio")
    try:
        info, criado = cerebro_pedidos.admitir(pedido)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {
        "pedido_id": info.pedido_id,
        "sessao_id": info.sessao_id,
        "estado": info.estado.value,
        "criado": criado,
    }


@app.get("/pedidos/{pedido_id}")
def pedidos_consultar(pedido_id: str):
    """Consulta estado de um pedido por ID."""
    info = cerebro_pedidos.consultar(pedido_id)
    if info is None:
        raise HTTPException(404, "pedido não encontrado")
    return {
        "pedido_id": info.pedido_id,
        "sessao_id": info.sessao_id,
        "estado": info.estado.value,
        "resposta": info.resposta,
        "erro": info.erro,
        "ultimo_seq": info.ultimo_seq,
    }


@app.post("/pedidos/{pedido_id}/cancelar")
def pedidos_cancelar(pedido_id: str):
    """Cancela um pedido existente."""
    info = cerebro_pedidos.cancelar(pedido_id)
    if info is None:
        raise HTTPException(404, "pedido não encontrado")
    return {
        "pedido_id": info.pedido_id,
        "estado": info.estado.value,
    }


@app.get("/pedidos")
def pedidos_listar(sessao_id: str = ""):
    """Lista pedidos; filtro opcional por sessao_id."""
    base = cerebro_pedidos._base()
    itens = []
    if base.exists():
        for arq in sorted(base.glob("*.json")):
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if sessao_id and dados.get("sessao_id") != sessao_id:
                continue
            itens.append({
                "pedido_id": dados.get("pedido_id", ""),
                "sessao_id": dados.get("sessao_id", ""),
                "estado": dados.get("estado", ""),
            })
    return {"pedidos": itens}


@app.get("/perfil/persona")
def persona_montada(nome: str = "", usuario: str = ""):
    """Persona pronta do perfil.json: prévia da aba do perfil e fonte do laço."""
    return {"texto": perfil.montar_persona(perfil.ler(), nome, usuario)}


# ----------------------------------------------------------------------------- PRIMEIRO USO: IMPORTAÇÃO (T7 0.9)
# Prévia/aplicar/reverter da instalação anterior. Respostas nunca trazem chaves;
# a origem é só lida. Erros usam código curto (origem_invalida, previa_obsoleta...).

@app.post("/primeiro-uso/importacao/previa")
def importacao_previa(corpo: dict):
    from vard.primeiro_uso import importacao as pu_importacao
    if not isinstance(corpo.get("origem"), str) or not corpo["origem"].strip():
        return JSONResponse({"erro": "origem_invalida"}, status_code=422)
    hud = corpo.get("hud_atual")
    try:
        return pu_importacao.previa(corpo["origem"], hud if isinstance(hud, dict) else None)
    except pu_importacao.OrigemInvalida:
        return JSONResponse({"erro": "origem_invalida"}, status_code=422)


@app.post("/primeiro-uso/importacao/aplicar")
def importacao_aplicar(corpo: dict):
    from vard.primeiro_uso import importacao as pu_importacao
    if not isinstance(corpo.get("previa_id"), str) or not corpo["previa_id"]:
        return JSONResponse({"erro": "previa_invalida"}, status_code=422)
    escolhas = corpo.get("escolhas")
    hud = corpo.get("hud_atual")
    try:
        return pu_importacao.aplicar(corpo["previa_id"], escolhas if isinstance(escolhas, dict) else {},
                                     hud if isinstance(hud, dict) else None)
    except pu_importacao.PreviaDesconhecida:
        return JSONResponse({"erro": "previa_desconhecida"}, status_code=404)
    except pu_importacao.PreviaObsoleta:
        return JSONResponse({"erro": "previa_obsoleta"}, status_code=409)
    except pu_importacao.EscolhaInvalida:
        return JSONResponse({"erro": "escolha_invalida"}, status_code=422)
    except pu_importacao.FalhaAplicacao:
        return JSONResponse({"erro": "aplicacao_falhou"}, status_code=500)


@app.post("/primeiro-uso/importacao/reverter")
def importacao_reverter(corpo: dict):
    from vard.primeiro_uso import importacao as pu_importacao
    if not isinstance(corpo.get("operacao_id"), str) or not corpo["operacao_id"]:
        return JSONResponse({"erro": "operacao_invalida"}, status_code=422)
    try:
        return pu_importacao.reverter(corpo["operacao_id"])
    except pu_importacao.OperacaoDesconhecida:
        return JSONResponse({"erro": "operacao_desconhecida"}, status_code=404)


@app.post("/modo")
def mudar_modo(corpo: dict):
    verbo = str(corpo.get("modo", "")).strip().lower()
    if verbo not in modo.VERBOS:
        raise HTTPException(422, f"modo inválido: {verbo}")
    try:
        resultado = modo.disparar(verbo)
    except FileNotFoundError as exc:
        return _erro(modelos.ErroModelo("modo_script", str(exc)))
    except OSError as exc:
        return _erro(modelos.ErroModelo("modo_falhou", str(exc)))
    except RuntimeError as exc:
        # App novo indisponível ou supervisor desabilitado; fallback legado falhou.
        return _erro(modelos.ErroModelo("modo_indisponivel", str(exc)))
    # disparar devolve dict {"ok": True, "id": uuid} (caixa IPC) ou int (PID legado).
    if isinstance(resultado, dict):
        return resultado
    return {"ok": True, "pid": resultado}


# ----------------------------------------------------------------------------- EVENTOS
# A oficina (outro processo) publica em POST /events/publicar; cada aba ou widget conectado em
# GET /events recebe. Uma fila por assinante; sem histórico (quem conecta depois não recebe o passado).
ESTADOS_AVISO = {"esperando", "travou", "terminou", "falhou"}
FERRAMENTAS_AVISO = {"claude", "codex", "opencode", "agy", "pesquisa", "agente_remoto", "manha", "delegada"}
AGENTES_DELEGADA = {"claude", "codex", "agy", "opencode"}
LIMITE_EVENTO = 32_768    # bytes: o maior evento legítimo (manhã, texto de 3000) cabe com folga, mesmo com \u escapes
ESTADOS_REUNIAO = {"iniciou", "encerrou", "diarizando", "ata_pronta", "erro"}
PASTA_REUNIAO = re.compile(r"[0-9_-]{1,40}")
ASSINANTES: set[asyncio.Queue] = set()


def validar_evento(ev) -> dict:
    if not isinstance(ev, dict):
        raise ValueError("evento não é objeto")
    if ev.get("tipo") == "preflight":
        return {"tipo": "preflight", "marca": str(ev.get("marca", ""))[:40]}
    if ev.get("tipo") == "reuniao":
        dur, pasta = ev.get("duracao_s"), ev.get("pasta", "")
        estado = ev.get("estado")
        ok = (
            isinstance(estado, str) and estado in ESTADOS_REUNIAO
            and isinstance(dur, int) and not isinstance(dur, bool) and dur >= 0
            and isinstance(pasta, str) and PASTA_REUNIAO.fullmatch(pasta) is not None
        )
        if not ok:
            raise ValueError("evento inválido")
        return {"tipo": "reuniao", "estado": ev["estado"], "duracao_s": dur, "pasta": pasta,
                "resumo": str(ev.get("resumo", ""))[:300]}
    n = ev.get("n")
    if ev.get("tipo") != "tarefa" or not isinstance(n, int) or isinstance(n, bool) or n < 1 \
            or ev.get("estado") not in ESTADOS_AVISO:
        raise ValueError("evento inválido")
    limpo = {"tipo": "tarefa", "n": n, "estado": ev["estado"], "resumo": str(ev.get("resumo", ""))[:300]}
    if ev.get("ferramenta") in FERRAMENTAS_AVISO:
        limpo["ferramenta"] = ev["ferramenta"]
    if limpo.get("ferramenta") == "delegada" and ev.get("agente") in AGENTES_DELEGADA:
        limpo["agente"] = ev["agente"]
    if limpo.get("ferramenta") == "manha" and ev.get("texto"):
        limpo["texto"] = str(ev["texto"])[:3000]
    return limpo


def formatar_sse(ev: dict) -> str:
    nome = {"tarefa": "oficina", "reuniao": "reuniao", "pedido": "pedido"}.get(ev.get("tipo", ""), "preflight")
    return f"event: {nome}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"


def publicar_evento(ev: dict) -> int:
    for fila in list(ASSINANTES):
        try:
            fila.put_nowait(ev)
        except asyncio.QueueFull:
            pass  # aba lenta perde aviso; não trava a oficina
    return len(ASSINANTES)


def publicar_evento_pedido(pedido_id: str, sessao_id: str, seq: int, tipo: str, dados: dict) -> None:
    """Publica um EventoPedido do cérebro próprio via SSE (tipo 'pedido')."""
    ev = {
        "tipo": "pedido",
        "pedido_id": pedido_id,
        "sessao_id": sessao_id,
        "seq": seq,
        "evento_tipo": tipo,
        "dados": dados,
    }
    publicar_evento(ev)


@app.post("/events/publicar")
async def events_publicar(request: Request):
    # Só processo local, nunca página: navegador sempre manda Origin num POST.
    if request.headers.get("origin"):
        return JSONResponse({"erro": "origem_recusada"}, status_code=403)
    corpo = await request.body()
    if len(corpo) > LIMITE_EVENTO:
        return JSONResponse({"erro": "corpo_grande_demais"}, status_code=413)
    try:
        ev = validar_evento(json.loads(corpo))
    except ValueError:
        raise HTTPException(422, "evento inválido")
    aviso = central.registrar(ev)
    if aviso:
        ev = {**ev, "id": aviso["id"], "hora": aviso["hora"]}
    return {"ok": True, "assinantes": publicar_evento(ev)}


@app.get("/avisos")
def avisos_lista():
    lista = central.listar()
    return {"avisos": lista, "nao_lidos": sum(1 for a in lista if not a.get("lido"))}


@app.post("/avisos/lidos")
def avisos_lidos(corpo: dict | None = None):
    ids = (corpo or {}).get("ids")
    if ids is not None and not isinstance(ids, list):
        raise HTTPException(422, "ids inválidos")
    return {"ok": True, "nao_lidos": central.marcar_lidos(ids)}


@app.get("/tarefas/andamento")
def tarefas_andamento():
    """Tarefas assíncronas rodando agora (preparando, rodando, esperando); as que aguardam aprovação não entram."""
    agora = dt.datetime.now().astimezone()
    lista = []
    try:
        todas = tarefas.listar()
    except (OSError, ValueError, TimeoutError):
        todas = []
    for t in todas:
        if t.estado not in ("preparando", "rodando", "esperando"):
            continue
        quem = oficina.NOMES.get(t.agente or t.ferramenta, t.ferramenta)
        try:
            seg = max(0, int((agora - tarefas.hora(t.criada_em)).total_seconds()))
        except (TypeError, ValueError):
            seg = 0
        lista.append({"n": t.n, "ferramenta": t.ferramenta, "quem": quem, "estado": t.estado,
                      "resumo": tarefas.resumir(" ".join(t.pedido.split()), 60), "segundos": seg})
    return {"total": len(lista), "tarefas": lista}


@app.get("/tarefas/{n}/resultado")
def tarefa_resultado(n: int):
    t = tarefas.obter(n)
    if t is None:
        raise HTTPException(404, "tarefa não existe")
    texto = ""
    try:
        if t.resultado:
            texto = vavisos.limpar_markdown(Path(t.resultado).read_text(encoding="utf-8"))[:20000]
    except (OSError, UnicodeDecodeError):      # resultado binário (ata em PDF): cai no resumo
        pass
    return {"n": n, "estado": t.estado, "resumo": t.resumo, "texto": texto or t.resumo}


@app.get("/events")
async def events():
    fila: asyncio.Queue = asyncio.Queue(maxsize=50)
    ASSINANTES.add(fila)

    async def gerar():
        try:
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    yield formatar_sse(await asyncio.wait_for(fila.get(), timeout=15))
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            ASSINANTES.discard(fila)

    return StreamingResponse(gerar(), media_type="text/event-stream")


# ----------------------------------------------------------------------------- REUNIÃO
# Proxy fino do vard-reuniao (4720): o widget e o MCP falam só com a ponte. 409 passa como 409; 4720 fora = 503.
def _proxy_reuniao(metodo: str, caminho: str, params: dict | None = None) -> JSONResponse:
    try:
        r = httpx.request(metodo, f"{REUNIAO}{caminho}", params=params, timeout=45, trust_env=False)
        return JSONResponse(r.json(), status_code=r.status_code)
    except httpx.ConnectError:
        return JSONResponse({"erro": "reuniao_ausente"}, status_code=503)
    except httpx.TimeoutException:
        return JSONResponse({"erro": "reuniao_lenta"}, status_code=504)
    except (httpx.HTTPError, ValueError):
        return JSONResponse({"erro": "reuniao_ausente"}, status_code=503)


@app.post("/reuniao/iniciar")
def reuniao_iniciar():
    return _proxy_reuniao("POST", "/iniciar")


@app.post("/reuniao/encerrar")
def reuniao_encerrar():
    return _proxy_reuniao("POST", "/encerrar")


@app.get("/reuniao/status")
def reuniao_status():
    return _proxy_reuniao("GET", "/status")


@app.get("/reuniao/lista")
def reuniao_lista(n: int = 10):
    return _proxy_reuniao("GET", "/lista", {"n": n})


@app.get("/reuniao/dispositivos")
def reuniao_dispositivos():
    """Lê a preferência de dispositivos salva pela ponte/widget."""
    try:
        from vard_reuniao import preferencia as pref_mod
        p = pref_mod.ler_preferencia()
        return JSONResponse(p.como_dict())
    except Exception:  # noqa: BLE001
        return JSONResponse({"microfone_id": "", "microfone_rotulo": "", "saida_id": "", "saida_rotulo": ""})


@app.post("/reuniao/dispositivos")
async def reuniao_dispositivos_gravar(request: Request):
    """Grava a preferência de dispositivos atomicamente."""
    try:
        corpo = await request.json()
    except ValueError:
        return JSONResponse({"erro": "json_invalido"}, status_code=422)
    if not isinstance(corpo, dict):
        return JSONResponse({"erro": "corpo_invalido"}, status_code=422)
    try:
        from vard_reuniao import preferencia as pref_mod
        p = pref_mod.PreferenciaDispositivos(
            microfone_id=str(corpo.get("microfone_id", "")),
            microfone_rotulo=str(corpo.get("microfone_rotulo", "")),
            saida_id=str(corpo.get("saida_id", "")),
            saida_rotulo=str(corpo.get("saida_rotulo", "")),
        )
        pref_mod.gravar_preferencia(p)
        return JSONResponse({"ok": True})
    except OSError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=500)


@app.post("/reuniao/ata")
async def reuniao_ata(request: Request):
    try:
        corpo = await request.json()
    except ValueError:
        corpo = None
    tipo, qual = (corpo.get("tipo"), corpo.get("qual", "ultima")) if isinstance(corpo, dict) else (None, None)
    if tipo not in ("ata", "relatorio") or not isinstance(qual, str) or not qual.strip():
        return JSONResponse({"erro": "pedido_invalido"}, status_code=422)
    try:
        n, frase = await asyncio.to_thread(reuniao.criar_ata, qual.strip(), tipo)
    except Frase as exc:
        return JSONResponse({"ok": False, "frase": str(exc)}, status_code=404 if str(exc) == reuniao.NAO_ACHEI else 409)
    return {"ok": True, "n": n, "frase": frase}


# --------------------------------------------------------------------------- PRIMEIRO USO (T2)
@app.get("/primeiro-uso")
def primeiro_uso_ler():
    """Estado atual do assistente; instalação preexistente devolve concluido=True."""
    return JSONResponse(primeiro_uso_estado.ler())


@app.put("/primeiro-uso")
async def primeiro_uso_atualizar(request: Request):
    """Aplica patch de campos conhecidos ao estado do assistente."""
    try:
        corpo = await request.json()
    except ValueError:
        return JSONResponse({"erro": "json_invalido"}, status_code=422)
    if not isinstance(corpo, dict):
        return JSONResponse({"erro": "corpo_invalido"}, status_code=422)
    nome = corpo.get("nome_chamada")
    if isinstance(nome, str):
        try:
            primeiro_uso_estado.validar_nome(nome)
        except ValueError:
            return JSONResponse({"erro": "nome_vazio"}, status_code=422)
    estado = primeiro_uso_estado.atualizar(corpo)
    return JSONResponse(estado)


@app.post("/primeiro-uso/reabrir")
def primeiro_uso_reabrir():
    """Reabre o assistente sem apagar escolhas salvas."""
    return JSONResponse(primeiro_uso_estado.reabrir())


async def _corpo_cerebro(request: Request, campos: tuple[str, ...]):
    try:
        corpo = await request.json()
    except ValueError:
        raise HTTPException(422, "json_invalido") from None
    if not isinstance(corpo, dict):
        raise HTTPException(422, "corpo_invalido")
    if any(not isinstance(corpo.get(c), str) or not corpo[c].strip() for c in campos):
        raise HTTPException(422, "campos_obrigatorios")
    if not isinstance(corpo.get("chave", ""), str):
        raise HTTPException(422, "credencial_invalida")
    return corpo


@app.post("/primeiro-uso/cerebro/testar")
async def primeiro_uso_cerebro_testar(request: Request):
    """Teste isolado da escolha expl?cita; n?o troca modelo nem persiste segredo."""
    from vard.primeiro_uso import cerebro
    corpo = await _corpo_cerebro(request, ("tipo", "base_url", "modelo"))
    return JSONResponse(await cerebro.testar_cerebro(
        tipo=corpo["tipo"].strip(), base_url=corpo["base_url"].strip(),
        modelo=corpo["modelo"].strip(), chave=corpo.get("chave", "")))


@app.post("/primeiro-uso/cerebro/modelos")
async def primeiro_uso_cerebro_modelos(request: Request):
    from vard.primeiro_uso import cerebro
    from vard.cerebro.provedores import ErroProvedor
    corpo = await _corpo_cerebro(request, ("tipo", "base_url"))
    try:
        async with asyncio.timeout(30):
            modelos = await cerebro.listar_modelos(corpo["tipo"], corpo["base_url"], corpo.get("chave", ""))
        return {"ok": True, "modelos": modelos}
    except ErroProvedor as exc:
        return {"ok": False, "detalhe": exc.codigo}
    except (ValueError, TimeoutError):
        return {"ok": False, "detalhe": "listagem_indisponivel"}


@app.post("/primeiro-uso/cerebro/trocar")
async def primeiro_uso_cerebro_trocar(request: Request):
    from vard.primeiro_uso import cerebro
    corpo = await _corpo_cerebro(request, ("tipo", "base_url", "modelo"))
    if corpo["tipo"] != "lmstudio":
        return JSONResponse({"erro": "controle_requer_lmstudio"}, status_code=422)
    return await cerebro.trocar_modelo(corpo["base_url"], corpo["modelo"], corpo.get("chave", ""))


# --------------------------------------------------------------------------- PACOTES OPCIONAIS (T5)
from vard.pacotes import carregar_manifesto, InstaladorPacotes

_instalador_pacotes = InstaladorPacotes()


@app.get("/pacotes")
def pacotes_listar():
    """Lista pacotes opcionais disponíveis no manifesto + estado de instalação."""
    try:
        manifesto = carregar_manifesto()
    except (FileNotFoundError, ValueError) as exc:
        return JSONResponse({"erro": str(exc)}, status_code=500)
    estado = _instalador_pacotes.ler_estado()
    lista = []
    for pid, pkg in manifesto.items():
        info = {
            "id": pkg.id,
            "nome": pkg.nome,
            "versao": pkg.versao,
            "tipo": pkg.tipo,
            "descricao": pkg.descricao,
            "bytes_download": pkg.bytes_download,
            "bytes_instalado": pkg.bytes_instalado,
            "licenca_url": pkg.licenca_url,
            "licenca_nome": pkg.licenca_nome,
            "indisponivel": pkg.indisponivel,
            "motivo_indisponivel": pkg.motivo_indisponivel,
            "instalado": pid in estado,
            "instalavel": pkg.instalavel(),
        }
        if pkg.voz_id:
            info["voz_id"] = pkg.voz_id
        lista.append(info)
    return {"pacotes": lista}


@app.post("/pacotes/{pacote_id}/instalar")
async def pacote_instalar(pacote_id: str):
    """Inicia instalação de um pacote opcional. Devolve 404 se não existir no manifesto."""
    try:
        manifesto = carregar_manifesto()
    except (FileNotFoundError, ValueError) as exc:
        return JSONResponse({"erro": str(exc)}, status_code=500)
    pkg = manifesto.get(pacote_id)
    if pkg is None:
        return JSONResponse({"erro": "pacote_nao_encontrado"}, status_code=404)
    if not pkg.instalavel():
        return JSONResponse(
            {"erro": "pacote_nao_instalavel", "motivo": pkg.motivo_indisponivel or "hash/url ausente"},
            status_code=409,
        )
    # Instalação síncrona para simplificar a primeira versão; SSE pode ser adicionado depois.
    resultado = await _instalador_pacotes.instalar(pkg)
    if resultado.estado == "concluido":
        return {"estado": "concluido", "pacote_id": pacote_id}
    return JSONResponse(
        {"estado": resultado.estado, "erro": resultado.erro},
        status_code=500 if resultado.estado == "falhou" else 202,
    )


@app.post("/pacotes/{pacote_id}/remover")
async def pacote_remover(pacote_id: str):
    """Remove um pacote instalado."""
    ok, erro = await _instalador_pacotes.remover(pacote_id)
    if ok:
        return {"estado": "removido", "pacote_id": pacote_id}
    return JSONResponse({"erro": erro}, status_code=500)


app.mount("/viewer", StaticFiles(directory=VIEWER), name="viewer")
