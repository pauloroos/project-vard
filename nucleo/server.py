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
import time
import uuid
from pathlib import Path

import anyio.from_thread
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from vard import avisos as vavisos, central, config, modelos, modo, oficina, perfil, reuniao, segredos, tarefas
from vard import config
from vard.cerebro import cli_capacidade, cli_deteccao, contratos as cerebro_contratos, pedidos as cerebro_pedidos
from vard.primeiro_uso import deteccao as primeiro_uso_deteccao, estado as primeiro_uso_estado
from vard.seguro import Frase
from vard import telegram as telegram_mod
from vard import sondas
from vard import aceite_windows

# Cliente que desiste antes do aceite não pode fechar a escuta do núcleo (ver vard/aceite_windows.py).
aceite_windows.instalar()
from vard.instalaveis import GerenciadorInstalaveis

_instalaveis = GerenciadorInstalaveis()

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
MODELO_NUVEM = "combo/equipe"
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
_supervisor_cli = None
_ferramentas_cerebro = None


def _obter_supervisor_cli():
    """Lazy import do SupervisorCli para evitar dependência circular no arranque."""
    global _supervisor_cli
    if _supervisor_cli is None:
        from vard.cerebro.cli_processos import SupervisorCli
        _supervisor_cli = SupervisorCli()
    return _supervisor_cli


class _ErroCerebro(Exception):
    """Erro estruturado do executor do cérebro próprio.

    O código é gravado no estado do pedido (campo erro) e emitido via SSE.
    """

    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


def _ler_provedor_ativo() -> dict:
    """Lê o provedor ativo de paineis.json. Devolve dict com tipo/modelo/url_base/credencial_ref/yolo/enxuto.

    Contratos:
      - TS (paineis.ts): ativo é id em provedores[]; provedor tem credencial_ref opcional.
      - Fallback legado: agentes[nome].ativo=True com tipo cli-*.
    Devolve dict vazio quando não há provedor ativo.
    """
    try:
        import json as _json
        cfg_paineis = config.arquivo_config("paineis.json")
        if not cfg_paineis.exists():
            return {}
        dados = _json.loads(cfg_paineis.read_text(encoding="utf-8-sig"))  # aceita BOM (D4)
        ativo_id = dados.get("ativo")
        provedores = dados.get("provedores", [])
        if isinstance(ativo_id, str) and ativo_id and isinstance(provedores, list):
            for p in provedores:
                if isinstance(p, dict) and str(p.get("id", "")) == ativo_id:
                    return {
                        "tipo": str(p.get("tipo", "")),
                        "modelo": str(p.get("modelo", "") or ""),
                        "url_base": str(p.get("url_base", "") or ""),
                        "credencial_ref": str(p.get("credencial_ref", "") or ""),
                        "yolo": bool(p.get("yolo", True)),
                        "enxuto": bool(p.get("enxuto", False)),
                    }
        # Fallback legado: agentes com ativo=True e tipo cli-*
        agentes = dados.get("agentes", {})
        if isinstance(agentes, dict):
            for _nome_ag, ag in agentes.items():
                if not isinstance(ag, dict):
                    continue
                t = str(ag.get("tipo", ""))
                if t.startswith("cli-") and ag.get("ativo", False):
                    return {
                        "tipo": t,
                        "modelo": str(ag.get("modelo", "") or ""),
                        "url_base": "",
                        "credencial_ref": "",
                        "yolo": bool(ag.get("yolo", True)),
                        "enxuto": bool(ag.get("enxuto", False)),
                    }
    except Exception:  # noqa: BLE001
        pass
    return {}


def _resolver_credencial_cofre(credencial_ref: str, tipo: str) -> str:
    """Resolve credencial via cofre (credenciais.ler_para_uso_interno).

    - Se credencial_ref está presente: lê do cofre como tipo='provedor'.
    - Se ausente e tipo é lmstudio/local: tenta segredos.chave_lmstudio() (token opcional).
    - Demais casos sem credencial_ref: retorna string vazia (alguns provedores locais não exigem).
    Levanta _ErroCerebro('cerebro_sem_credencial') se o cofre falhar ou a ref existir mas estiver vazia.
    """
    if credencial_ref:
        try:
            from vard import credenciais
            valor = credenciais.ler_para_uso_interno(*credenciais.separar_referencia(credencial_ref, "provedor"))
        except Exception as exc:  # noqa: BLE001
            raise _ErroCerebro("cerebro_sem_credencial") from exc
        if not valor:
            raise _ErroCerebro("cerebro_sem_credencial")
        return valor
    # lmstudio/local podem funcionar sem credencial; tenta token opcional do segredos.toml
    if tipo in ("lmstudio", "local"):
        try:
            from vard import segredos
            return segredos.chave_lmstudio() or ""
        except Exception:  # noqa: BLE001
            return ""
    return ""


async def _executar_pedido_cerebro(pedido, emitir):
    """Executor do cérebro próprio: seleciona adaptador conforme provedor ativo.

    T16: CLI (cli-claude/cli-agy) → SupervisorCli + AdaptadorCli.
    T16d: API (openai_compat/anthropic/google/lmstudio/openai_nativo) → adaptador real
          com credencial via cofre. Falhas levantam _ErroCerebro (gravado no estado do pedido).
    """
    from vard.cerebro import laco as cerebro_laco
    from vard.cerebro.cli import AdaptadorCli
    from vard.cerebro.cli_processos import ProvedorCli
    from vard.cerebro.montador import montar_adaptador

    prov = _ler_provedor_ativo()
    tipo_provedor = prov.get("tipo", "")

    if not tipo_provedor:
        raise _ErroCerebro("cerebro_sem_provedor")

    if tipo_provedor in ("cli-claude", "cli-agy"):
        supervisor = _obter_supervisor_cli()
        provedor_cli = ProvedorCli(
            id=tipo_provedor.replace("-", "_"),
            tipo=tipo_provedor,
            modelo=prov.get("modelo", ""),
            yolo=prov.get("yolo", True),
            enxuto=prov.get("enxuto", False),
        )
        canal = await supervisor.canal(provedor_cli, pedido.sessao_id)
        dialeto = "claude" if tipo_provedor == "cli-claude" else "agy"
        adaptador = AdaptadorCli(canal, dialeto)
    elif tipo_provedor in ("openai_compat", "lmstudio", "local", "anthropic", "google", "openai_nativo"):
        url_base = prov.get("url_base", "")
        modelo = prov.get("modelo", "")
        if not url_base:
            raise _ErroCerebro("cerebro_sem_url_base")
        if not modelo:
            raise _ErroCerebro("cerebro_sem_modelo")
        chave = _resolver_credencial_cofre(prov.get("credencial_ref", ""), tipo_provedor)
        try:
            adaptador = montar_adaptador(tipo_provedor, url_base, modelo, chave)
        except ValueError as exc:
            raise _ErroCerebro("cerebro_tipo_desconhecido") from exc
    else:
        raise _ErroCerebro("cerebro_tipo_desconhecido")

    await cerebro_laco.executar_pedido(pedido, adaptador, emitir,
        gerenciador_ferramentas=_ferramentas_cerebro if not tipo_provedor.startswith("cli-") else None)


# Poller do Telegram: um por núcleo, religado quando a configuração muda (tela, assistente, migração).
_telegram: dict = {"tarefa": None, "chave": None}


async def _parar_telegram() -> None:
    tarefa, _telegram["tarefa"], _telegram["chave"] = _telegram["tarefa"], None, None
    if tarefa is None:
        return
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass
    log.info("telegram poller parado")


async def _sincronizar_telegram() -> bool:
    """Liga, religa ou desliga o poller conforme telegram.toml e o cofre. True = poller rodando."""
    cfg = telegram_mod._ler_config_telegram()
    token = telegram_mod._token_seguro(cfg) if telegram_mod.deve_iniciar_poller() else ""
    chats = telegram_mod._chats_permitidos(cfg)
    base_url = str(cfg.get("base_url", "https://api.telegram.org"))
    chave = (token, frozenset(chats), base_url) if token and chats else None
    tarefa = _telegram["tarefa"]
    if chave is not None and chave == _telegram["chave"] and tarefa is not None and not tarefa.done():
        return True
    await _parar_telegram()
    if chave is None:
        log.info("telegram sem ligar/token/chat; poller nao iniciado")
        return False
    poller = telegram_mod.TelegramPoller(token=token, chats_permitidos=chats, base_url=base_url)

    async def _loop():
        while True:
            try:
                await poller.processar_updates()
            except Exception:  # noqa: BLE001
                log.warning("erro no loop do telegram poller")
            await asyncio.sleep(telegram_mod.ESPERA_CONFLITO_S if poller.conflito else telegram_mod.POLL_INTERVAL_PADRAO)

    _telegram["tarefa"], _telegram["chave"] = asyncio.create_task(_loop()), chave
    log.info("telegram poller iniciado (chats=%d)", len(chats))
    return True


@asynccontextmanager
async def lifespan(app):
    """Ciclo de vida: inicia/para o TelegramPoller condicional (T11) e o SupervisorCli (T16)."""
    global _ferramentas_cerebro
    from vard.cerebro.ferramentas import GerenciadorFerramentas
    from vard.segredos import servidores_locais
    _ferramentas_cerebro = GerenciadorFerramentas()
    for nome, servidor in servidores_locais().items():
        try:
            await _ferramentas_cerebro.adicionar_stdio(nome, servidor["command"], servidor["args"])
        except Exception:
            log.warning("MCP local indisponível: %s", nome)
    # Configura o executor do cérebro próprio (T16: ligação no despachante)
    cerebro_pedidos.configurar_executor(_executar_pedido_cerebro)
    # D2: encaminha eventos do cérebro próprio para o SSE /events
    def _emissor_sse(ev):
        try:
            publicar_evento_pedido(
                pedido_id=ev.pedido_id,
                sessao_id=ev.sessao_id,
                seq=ev.seq,
                tipo=ev.tipo.value if hasattr(ev.tipo, "value") else str(ev.tipo),
                dados=ev.dados or {},
            )
        except Exception:  # noqa: BLE001
            pass
    cerebro_pedidos.configurar_emissor(_emissor_sse)

    # Telegram próprio: sobe com o núcleo pelo telegram.toml + cofre, sem depender do OpenJarvis.
    await _sincronizar_telegram()
    try:
        yield
    finally:
        await _ferramentas_cerebro.fechar_tudo()
        _ferramentas_cerebro = None
        await asyncio.to_thread(_instalaveis.encerrar)
        # T16: encerra todos os processos vivos de CLI também quando a saída tem erro.
        if _supervisor_cli is not None:
            try:
                await _supervisor_cli.encerrar_tudo()
                log.info("SupervisorCli: processos encerrados na saída")
            except Exception:  # noqa: BLE001
                log.warning("SupervisorCli: erro ao encerrar processos na saída")
        await _parar_telegram()


app = FastAPI(title="Vard", lifespan=lifespan)


@app.get("/saude")
async def saude_supervisor():
    # Assíncrona de propósito: responde no laço de eventos, sem esperar vaga no pool de threads
    # que as rotas síncronas lentas (/recursos, /cli/detectar) ocupam.
    from vard import __version__
    return {"ok": True, "versao": __version__, "pid": os.getpid()}


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


def _acao_instalavel(acao, ident, **opcoes):
    try:
        return acao(ident, **opcoes)
    except KeyError:
        raise HTTPException(404, "Instalável não encontrado.") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    except OSError:
        raise HTTPException(503, "Não foi possível abrir o terminal de login.") from None


@app.get("/instalaveis")
def instalaveis_listar():
    return {"itens": _instalaveis.listar()}


@app.post("/instalaveis/{ident}/instalar")
def instalaveis_instalar(ident: str, corpo: dict):
    return _acao_instalavel(_instalaveis.instalar, ident, confirmado=corpo.get("confirmado") is True)


@app.get("/instalaveis/{ident}/andamento")
def instalaveis_andamento(ident: str):
    return _acao_instalavel(_instalaveis.andamento, ident)


@app.post("/instalaveis/{ident}/cancelar")
def instalaveis_cancelar(ident: str):
    return _acao_instalavel(_instalaveis.cancelar, ident)


@app.post("/instalaveis/{ident}/login")
def instalaveis_login(ident: str, corpo: dict | None = None):
    if not corpo or corpo.get("confirmado") is not True:
        raise HTTPException(400, "É necessária a confirmação para entrar na conta.")
    return _acao_instalavel(_instalaveis.login, ident)


@app.post("/configuracoes/provedores/{ident}/testar")
async def configuracoes_testar_provedor(ident: str):
    from vard import ajustes
    from vard.primeiro_uso import cerebro
    try:
        prov = next(p for p in ajustes.ler_documento("paineis")["provedores"] if p["id"] == ident)
    except (StopIteration, ValueError, OSError):
        raise HTTPException(404, "Provedor não encontrado.") from None
    if prov["tipo"].startswith("cli-"):
        return await _testar_cli(prov["tipo"], prov["modelo"])
    try:
        chave = _resolver_credencial_cofre(prov.get("credencial_ref", ""), prov["tipo"])
    except _ErroCerebro:
        return {"ok": False, "detalhe": "Cadastre a chave na tela de Configurações."}
    if not chave and prov["tipo"] not in ("lmstudio", "local", "ollama", "openai_compat"):
        return {"ok": False, "detalhe": "Cadastre a chave na tela de Configurações."}
    resultado = await cerebro.testar_cerebro(tipo=prov["tipo"], base_url=prov["url_base"], modelo=prov["modelo"], chave=chave)
    return {"ok": resultado.get("ok", False), "detalhe": "Conexão OK." if resultado.get("ok") else "Não foi possível conectar ao provedor."}


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


def _visao_local() -> tuple[str, str]:
    """Endereço e modelo da visão local: VARD_LMSTUDIO_URL manda; senão o LM Studio cadastrado no Núcleo; senão o padrão."""
    if os.environ.get("VARD_LMSTUDIO_URL"):
        return LMSTUDIO, MODELO_LOCAL
    try:
        dados = json.loads(config.arquivo_config("paineis.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return LMSTUDIO, MODELO_LOCAL
    for p in dados.get("provedores", []) if isinstance(dados, dict) else []:
        if isinstance(p, dict) and p.get("tipo") == "lmstudio" and str(p.get("url_base") or "").strip():
            base = str(p["url_base"]).strip().rstrip("/").removesuffix("/v1")
            return base, str(p.get("modelo") or "").strip() or MODELO_LOCAL
    return LMSTUDIO, MODELO_LOCAL


PRAZO_VER_CEREBRO = 85.0  # o widget desiste do /see em 90 s


async def _perguntar_cerebro(texto: str, sessao_id: str) -> str:
    """Admite um pedido no cérebro próprio e espera a resposta final (para quem precisa dela de uma vez, como o /see)."""
    pedido = cerebro_contratos.Pedido(
        pedido_id=f"ver-{uuid.uuid4().hex}", sessao_id=sessao_id, origem=cerebro_contratos.Origem.VOZ, texto=texto,
    )
    cerebro_pedidos.admitir(pedido)
    limite = time.monotonic() + PRAZO_VER_CEREBRO
    while time.monotonic() < limite:
        await asyncio.sleep(0.3)
        info = cerebro_pedidos.consultar(pedido.pedido_id)
        if info is None:
            continue
        estado = info.estado.value
        if estado == "concluido":
            return (info.resposta or "").strip()
        if estado in ("falhou", "cancelado"):
            raise _ErroCerebro(info.erro or "cerebro_erro")
    cerebro_pedidos.cancelar(pedido.pedido_id)
    raise _ErroCerebro("cli_tempo")


# Sessão da visão quando o widget não manda a da voz: estável, para não abrir uma CLI por pedido.
SESSAO_VISAO_PADRAO = "voz"


def _ver_pela_cli(jpeg: bytes, pergunta: str, sessao_id: str = SESSAO_VISAO_PADRAO) -> JSONResponse | dict:
    """Núcleo numa CLI: a captura vai para ela num arquivo temporário (a CLI abre a imagem); o arquivo some ao fim."""
    pasta = config.pasta_dados() / "capturas"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"tela-{uuid.uuid4().hex}.jpg"
    arquivo.write_bytes(jpeg)
    texto = (
        f"{pergunta}\n\nA captura da minha tela está no arquivo: {arquivo}\n"
        "Abra essa imagem e responda olhando para ela, em poucas frases faladas."
    )
    try:
        # Mesma sessão da conversa por voz: a visão não abre um segundo processo de CLI.
        resposta = anyio.from_thread.run(_perguntar_cerebro, texto, sessao_id)
    except _ErroCerebro as exc:
        log.warning("visão pela CLI falhou: %s", exc.codigo)
        return JSONResponse({"erro": exc.codigo}, status_code=503)
    finally:
        arquivo.unlink(missing_ok=True)
    if not resposta:
        return JSONResponse({"erro": "modelo_vazio"}, status_code=503)
    return {"resposta": resposta, "nuvem": False}


@app.post("/see")
def see(imagem: UploadFile = File(...), pergunta: str = Form("O que está na tela?"), sessao_id: str = Form("")):
    if imagem.content_type != "image/jpeg":
        raise HTTPException(422, "mande image/jpeg")
    jpeg = imagem.file.read()
    cuidado = "com mais cuidado" in pergunta.lower()
    if not cuidado and _ler_provedor_ativo().get("tipo", "").startswith("cli-"):
        return _ver_pela_cli(jpeg, pergunta, sessao_id.strip()[:128] or SESSAO_VISAO_PADRAO)
    b64 = base64.b64encode(jpeg).decode()
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
            base, modelo = _visao_local()
            resposta = modelos.ver_imagem(
                b64, pergunta, base=base, modelo=modelo, instrucao=INSTRUCAO_VISAO,
                chave=CHAVE_LMSTUDIO,
            )
    except FileNotFoundError:
        return _erro(modelos.ErroModelo("segredos", "segredos.toml não encontrado"))
    except modelos.ErroModelo as exc:
        # Servidor de visão fora: código próprio, para a fala não dizer que o núcleo caiu.
        if exc.codigo == "modelo_fora":
            exc = modelos.ErroModelo("visao_fora", exc.detalhe)
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


def _prazo_sonda(url: str) -> httpx.Timeout:
    """Porta fechada no loopback do Windows leva ~2 s para recusar: conexão curta, leitura de 2 s."""
    return sondas.prazo(url)


async def _sondar_reuniao() -> str:
    """Sonda assíncrona ao serviço de reunião (leitura 2 s, conexão curta)."""
    try:
        async with httpx.AsyncClient(timeout=_prazo_sonda(REUNIAO), trust_env=False) as client:
            r = await client.get(f"{REUNIAO}/status")
            return "ativa" if r.json().get("ativa") else "inativa"
    except (httpx.HTTPError, ValueError, AttributeError):
        return "ausente"


async def _sondar_openjarvis() -> bool:
    """Sonda assíncrona ao OpenJarvis (leitura 2 s, conexão curta)."""
    try:
        async with httpx.AsyncClient(timeout=_prazo_sonda(OPENJARVIS), trust_env=False) as client:
            r = await client.get(f"{OPENJARVIS}/health")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def _sondar_lmstudio() -> tuple[bool, list[str], str]:
    """Sonda assíncrona ao LM Studio (leitura 2 s, conexão curta); devolve (ok, ids, modelo)."""
    try:
        cab = {"Authorization": f"Bearer {CHAVE_LMSTUDIO}"} if CHAVE_LMSTUDIO else {}
        async with httpx.AsyncClient(timeout=_prazo_sonda(LMSTUDIO), trust_env=False) as client:
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
    # D3/0.9.3: campo cerebro reflete o provedor ativo e as sessões vivas do supervisor.
    prov_ativo = _ler_provedor_ativo()
    supervisor = _obter_supervisor_cli() if _supervisor_cli is not None else None
    sessoes_vivas = len(supervisor.pids()) if supervisor is not None else 0
    cerebro_status = {
        "ativo": bool(prov_ativo.get("tipo")),
        "provedor": str(prov_ativo.get("tipo", "")),
        "sessoes": sessoes_vivas,
    }
    return {"openjarvis": ok_oj, "lmstudio": ok_lm, "modelo": modelo, "modo": modo.ler_estado()["modo"],
            "modelos_lmstudio": ids, "tarefas_abertas": _tarefas_abertas(), "reuniao": reuniao,
            "cerebro": cerebro_status,
            "cli_enxuto": {"avisos": cli_capacidade.avisos()}}


# ----------------------------------------------------------------------------- PRIMEIRO USO (T1)
# Detecção local somente-leitura: reconhece ferramentas já instaladas sem iniciar serviço,
# fazer login ou carregar modelo. `item`+`caminho` permitem apontar o executável no painel.
@app.get("/primeiro-uso/deteccao")
def primeiro_uso_deteccao_rota(item: str = "", caminho: str = ""):
    caminhos = {item: caminho} if item and caminho and item in primeiro_uso_deteccao.IDS else None
    return primeiro_uso_deteccao.detectar(caminhos=caminhos).como_dict()


@app.get("/primeiro-uso/recomendacao")
def primeiro_uso_recomendacao_rota():
    """Recomenda a configuração mais leve para o primeiro uso (0.9.4 rodada 2)."""
    resultado = primeiro_uso_deteccao.detectar()
    rec = primeiro_uso_deteccao.recomendar_configuracao_leve(resultado)
    return {"voz": rec.voz, "cerebro": rec.cerebro, "motivo": rec.motivo}


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


@app.get("/cli/detectar")
def detectar_clis():
    """CLIs de agente no PATH (C11): só --version e `agy models`, sem caminho na resposta."""
    return cli_deteccao.detectar()


@app.post("/modo")
def mudar_modo(corpo: dict):
    verbo = str(corpo.get("modo", "")).strip().lower()
    if verbo == "jogo":
        return JSONResponse({"ok": False, "erro": "modo jogo indisponível nesta versão"}, status_code=503)
    if verbo == "voltar":
        return {"ok": True, "mensagem": "restauração pendente para próxima versão"}
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
    corpo = await _corpo_cerebro(request, ("tipo",))
    tipo = corpo["tipo"].strip()
    if tipo.startswith("cli-"):
        return JSONResponse(await _testar_cli(tipo, str(corpo.get("modelo", "") or "").strip()))
    corpo = await _corpo_cerebro(request, ("tipo", "base_url", "modelo"))
    return JSONResponse(await cerebro.testar_cerebro(
        tipo=tipo, base_url=corpo["base_url"].strip(),
        modelo=corpo["modelo"].strip(), chave=_chave_do_teste(corpo)))


def _sem_v1(url: str) -> str:
    u = url.strip().rstrip("/")
    return u[:-3] if u.endswith("/v1") else u


def _chave_do_teste(corpo: dict) -> str:
    """Chave digitada; sem ela, a do cofre do provedor salvo, só se tipo e endereço forem os mesmos dele.

    Assim um endereço digitado no campo nunca recebe a chave de outro provedor.
    """
    chave = str(corpo.get("chave", "") or "").strip()
    pid = corpo.get("provedor_id")
    if chave or not isinstance(pid, str) or not pid.strip():
        return chave
    try:
        dados = json.loads(config.arquivo_config("paineis.json").read_text(encoding="utf-8-sig"))
        prov = next(p for p in dados.get("provedores", []) if isinstance(p, dict) and p.get("id") == pid.strip())
    except (OSError, ValueError, StopIteration, AttributeError):
        return ""
    tipo = str(corpo.get("tipo", "")).strip()
    if str(prov.get("tipo", "")) != tipo or _sem_v1(str(prov.get("url_base", ""))) != _sem_v1(str(corpo.get("base_url", ""))):
        return ""
    try:
        return _resolver_credencial_cofre(str(prov.get("credencial_ref", "") or ""), tipo)
    except _ErroCerebro:
        return ""


async def _testar_cli(tipo: str, modelo: str) -> dict:
    """Testa uma CLI de verdade numa sessão descartável; Codex/OpenCode só servem a tarefas delegadas."""
    import uuid
    from vard.primeiro_uso import cerebro
    from vard.cerebro import cli_deteccao
    from vard.cerebro.cli import AdaptadorCli
    from vard.cerebro.cli_processos import ProvedorCli
    det =next((d for d in cli_deteccao.detectar() if d.get("tipo") == tipo), None)
    if det is None or not det.get("instalada"):
        return {"ok": False, "detalhe": "cli_nao_encontrada", "primeiro_token_ms": None}
    if tipo not in ("cli-claude", "cli-agy"):
        return {"ok": True, "detalhe": f"instalada {det.get('versao', '')}".strip(), "primeiro_token_ms": None}
    supervisor = _obter_supervisor_cli()
    sessao = f"teste-{uuid.uuid4().hex[:8]}"
    provedor_cli = ProvedorCli(id=tipo.replace("-", "_"), tipo=tipo, modelo=modelo, yolo=False, enxuto=False)
    try:
        canal = await supervisor.canal(provedor_cli, sessao)
        return await cerebro.consumir_teste(AdaptadorCli(canal, "claude" if tipo == "cli-claude" else "agy"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detalhe": f"cli_falhou: {type(exc).__name__}", "primeiro_token_ms": None}
    finally:
        await supervisor.nova_conversa(sessao)   # encerra o processo do teste


@app.post("/primeiro-uso/cerebro/modelos")
async def primeiro_uso_cerebro_modelos(request: Request):
    from vard.primeiro_uso import cerebro
    from vard.cerebro.provedores import ErroProvedor
    corpo = await _corpo_cerebro(request, ("tipo", "base_url"))
    try:
        async with asyncio.timeout(30):
            modelos = await cerebro.listar_modelos(corpo["tipo"], corpo["base_url"], _chave_do_teste(corpo))
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
from vard.pacotes import carregar_manifesto, carregar_todos_manifestos, InstaladorPacotes

_instalador_pacotes = InstaladorPacotes()


@app.get("/pacotes")
def pacotes_listar():
    """Lista pacotes opcionais disponíveis no manifesto + estado de instalação."""
    try:
        manifesto = carregar_todos_manifestos()
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
async def pacote_instalar_sse(pacote_id: str, request: Request):
    """Inicia instalação de um pacote opcional com progresso via SSE."""
    try:
        manifesto = carregar_todos_manifestos()
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

    import asyncio
    import json as _json

    fila: asyncio.Queue[dict | None] = asyncio.Queue()

    def _on_progress(p):
        try:
            fila.put_nowait({
                "estado": p.estado,
                "bytes_baixados": p.bytes_baixados,
                "bytes_total": p.bytes_total,
                "erro": p.erro,
            })
        except asyncio.QueueFull:
            pass

    async def _gerar_eventos():
        tarefa = asyncio.create_task(_instalador_pacotes.instalar(pkg, on_progress=_on_progress))
        while True:
            if await request.is_disconnected():
                _instalador_pacotes.cancelar(pacote_id)
                tarefa.cancel()
                break
            try:
                evento = await asyncio.wait_for(fila.get(), timeout=1.0)
            except asyncio.TimeoutError:
                yield f"data: {_json.dumps({'estado': 'aguardando'})}\n\n"
                continue
            if evento is None:
                break
            yield f"data: {_json.dumps(evento)}\n\n"
            if evento["estado"] in ("concluido", "falhou", "cancelado"):
                break
        if not tarefa.done():
            try:
                await tarefa
            except Exception:
                pass

    from starlette.responses import StreamingResponse as _StreamingSSE
    return _StreamingSSE(_gerar_eventos(), media_type="text/event-stream")


@app.post("/pacotes/{pacote_id}/cancelar")
async def pacote_cancelar(pacote_id: str):
    """Cancela uma instalação em andamento."""
    _instalador_pacotes.cancelar(pacote_id)
    return {"estado": "cancelado", "pacote_id": pacote_id}


@app.post("/pacotes/{pacote_id}/remover")
async def pacote_remover(pacote_id: str):
    """Remove um pacote instalado."""
    ok, erro = await _instalador_pacotes.remover(pacote_id)
    if ok:
        return {"estado": "removido", "pacote_id": pacote_id}
    return JSONResponse({"erro": erro}, status_code=500)


@app.get("/recursos")
def recursos():
    """Monitor de recursos do Vard (0.9.4 leve): memória e CPU por componente."""
    from vard import recursos as mod_recursos
    supervisor = _supervisor_cli
    try:
        cli_pids = list(supervisor.pids()) if supervisor is not None else []
    except Exception:  # noqa: BLE001
        cli_pids = []
    return mod_recursos.coletar_recursos(cli_pids=cli_pids)


# --------------------------------------------------------------------------- TELEGRAM (T9 tela)
# Endpoints para a seção Telegram da aba Sistema. Token nunca passa por aqui: a tela grava
# no cofre do Windows (cofre_gravar canal/telegram) e a migração do OpenJarvis grava direto no cofre.

@app.get("/telegram")
async def telegram_estado():
    """Estado da seção Telegram e o que há para trazer do OpenJarvis; nunca o token."""
    from vard import telegram_migracao
    return {**telegram_mod.estado(), "rodando": _telegram["tarefa"] is not None,
            "openjarvis": telegram_migracao.previa()}


@app.post("/telegram/configurar")
async def telegram_configurar(request: Request):
    """Liga/desliga e define o chat permitido; o token vai pelo cofre (tela) ou pela migração."""
    try:
        corpo = await request.json()
    except ValueError:
        corpo = None
    if not isinstance(corpo, dict) or not isinstance(corpo.get("ligado"), bool):
        raise HTTPException(422, "ligado precisa ser verdadeiro ou falso")
    telegram_mod.configurar(corpo["ligado"], str(corpo.get("chat", "") or ""))
    return {"ok": True, "rodando": await _sincronizar_telegram()}


@app.post("/telegram/sincronizar")
async def telegram_sincronizar():
    """Relê telegram.toml e o cofre (depois de gravar o token pela tela ou pelo assistente)."""
    return {"ok": True, "rodando": await _sincronizar_telegram()}


@app.post("/telegram/trazer_openjarvis")
async def telegram_trazer_openjarvis(request: Request):
    """Traz token (cofre) e chats do OpenJarvis; um Telegram já configurado só sai com substituir=true."""
    from vard import telegram_migracao
    try:
        corpo = await request.json()
    except ValueError:
        corpo = {}
    substituir = isinstance(corpo, dict) and corpo.get("substituir") is True
    resultado = await asyncio.to_thread(telegram_migracao.trazer, substituir)
    if resultado.get("ok"):
        resultado["rodando"] = await _sincronizar_telegram()
    return resultado


@app.get("/telegram/descobrir_chat")
async def telegram_descobrir_chat():
    """Lê o último update pendente do bot e retorna o chat_id do /start mais recente."""
    cfg = telegram_mod._ler_config_telegram()
    token = telegram_mod._token_seguro(cfg)
    if not token:
        return {"ok": False, "detalhe": "Token não configurado."}
    base_url = str(cfg.get("base_url", "https://api.telegram.org")).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            r = await client.get(f"{base_url}/bot{token}/getUpdates", params={"limit": 5})
            if r.status_code != 200 or not r.json().get("ok"):
                return {"ok": False, "detalhe": "Falha ao consultar updates."}
            results = r.json().get("result", [])
            # Busca o último update com /start
            for update in reversed(results):
                msg = update.get("message")
                if not isinstance(msg, dict):
                    continue
                texto = str(msg.get("text", "")).strip()
                if texto.startswith("/start"):
                    chat = msg.get("chat")
                    if isinstance(chat, dict):
                        return {"ok": True, "chat_id": str(chat.get("id", ""))}
            return {"ok": False, "detalhe": "Nenhum /start pendente."}
    except httpx.HTTPError:
        return {"ok": False, "detalhe": "Erro de rede."}


@app.post("/telegram/testar")
async def telegram_testar():
    """Envia mensagem de teste ao primeiro chat permitido configurado."""
    cfg = telegram_mod._ler_config_telegram()
    token = telegram_mod._token_seguro(cfg)
    chats = telegram_mod._chats_permitidos(cfg)
    if not token:
        return {"ok": False, "detalhe": "Token não configurado."}
    if not chats:
        return {"ok": False, "detalhe": "Nenhum chat permitido configurado."}
    chat_id = next(iter(chats))
    base_url = str(cfg.get("base_url", "https://api.telegram.org")).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            r = await client.post(
                f"{base_url}/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "Teste do Vard: conexão OK."},
            )
            if r.status_code == 200 and r.json().get("ok"):
                return {"ok": True}
            return {"ok": False, "detalhe": f"Falha ao enviar: HTTP {r.status_code}"}
    except httpx.HTTPError:
        return {"ok": False, "detalhe": "Erro de rede."}


app.mount("/viewer", StaticFiles(directory=VIEWER), name="viewer")
