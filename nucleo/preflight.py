"""Preflight do Vard: cadeias vivas, sem mocks. 'Pronto' só com isto limpo.

Uso: uv run python preflight.py
"""
from __future__ import annotations

import array
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import tomllib
import unicodedata
import uuid
import wave
from pathlib import Path
from typing import Callable

import httpx
import psutil

from vard import consulta, delegada, mesa_cliente, modo, remoto, segredos
from vard import config as vard_config
from vard import instalacao
from vard import oficina as oficina_mod
from vard import reuniao as reuniao_mod
from vard import vigia
from vard.mcp_http import ClienteMCP, ErroMCP
from vard import orca_cli
from vard.orca_cli import Orca

# Chamadas locais com trust_env=False: o ambiente do PC faz o httpx tentar um proxy e
# dar timeout em 127.0.0.1 (achado na Task 8). OmniRouter usa o padrão.

RAIZ = Path(__file__).resolve().parent          # pasta nucleo/ (viewer e ativos de teste)
RAIZ_REPO = RAIZ.parent                         # raiz do repositório (scripts/)
SCRIPT_MODO = RAIZ_REPO / "scripts" / "windows" / "vard-modo.ps1"
PONTE = "http://127.0.0.1:4700"
VOZ = "http://127.0.0.1:4710"
REUNIAO = "http://127.0.0.1:4720"
OPENJARVIS = "http://127.0.0.1:8000"
LMSTUDIO = "http://127.0.0.1:1234"
MODELO = "gemma-4-12b-it-qat@q4_k_xl"
PORTAS = (1234, 8000, 4700)
PORTAS_NOSSAS = (8000, 4700)   # têm de ficar em loopback. A 1234 (LM Studio) é decisão do usuário: só aviso.
FERRAMENTAS_MESA = ("abrir_url", "abrir_programa", "listar_janelas", "focar_janela", "fechar_janela", "print_da_tela",
                    "hora_atual")
FERRAMENTAS_OFICINA = ("disparar_tarefa", "status_tarefa", "resultado_tarefa", "responder_tarefa", "aprovar_tarefa",
                       "descartar_tarefa", "listar_tarefas")
FERRAMENTAS_CONSULTA = ("github_prs", "github_issues", "deploys", "relatorio", "agente_remoto", "rotina_manha", "delegar")
FERRAMENTAS_MEMORIA = ("memoria_buscar", "memoria_ler", "memoria_gravar")
FERRAMENTAS_REUNIAO = ("reuniao_iniciar", "reuniao_encerrar", "reuniao_status", "reuniao_ata", "reuniao_falante",
                       "reuniao_guardar")
SECOES_ATA = ("Resumo", "Decisões", "Pendências", "Pontos abertos", "Próximos passos")
# Ativos da prova de reunião ficam nos dados do usuário (gravados pela instalação), nunca no repositório.
PASTA_ATIVOS = vard_config.pasta_dados() / "preflight"
WAV_REUNIAO = PASTA_ATIVOS / "preflight-reuniao.wav"
TXT_REUNIAO = PASTA_ATIVOS / "preflight-reuniao.txt"
MSG_ATIVO_AUSENTE = "AVISO: ativo de teste ausente em {pasta}; checagem pulada"
FIXTURE_ATA = RAIZ / "tests" / "fixtures" / "reuniao" / "transcricao-40min.jsonl"
SEM_MEMORIA = "A memória ainda não está ligada"

Check = tuple[bool, str]


def _chave_lm() -> str:
    try:
        return segredos.chave_lmstudio()
    except FileNotFoundError:
        return ""


CHAVE_LM = _chave_lm()


def _cab_lm() -> dict:
    return {"Authorization": f"Bearer {CHAVE_LM}"} if CHAVE_LM else {}


def _jpeg_com_texto() -> bytes:
    """JPEG fixo com a palavra PREFLIGHT em letras grandes (tests/preflight.jpg, gerado uma vez
    no passo 2 da Tarefa 9). Evita depender de Pillow só para desenhar texto."""
    return (RAIZ / "tests" / "preflight.jpg").read_bytes()


def avaliar_portas(escutando: list[tuple[int, str]]) -> Check:
    """Puro: `escutando` = [(porta, ip)] em LISTEN. 8000 e 4700 só em loopback; a 1234 exposta vira aviso
    (o usuário mantém o LM Studio na rede para usar de outras máquinas; decisão de 12/10)."""
    achadas = sorted({(p, ip) for p, ip in escutando if p in PORTAS})
    abertas = [(p, ip) for p, ip in achadas if ip not in ("127.0.0.1", "::1")]
    graves = [(p, ip) for p, ip in abertas if p in PORTAS_NOSSAS]
    avisos = [(p, ip) for p, ip in abertas if p not in PORTAS_NOSSAS]
    detalhe = ", ".join(f"{ip}:{p}" for p, ip in achadas) or "nenhuma porta do Vard escutando"
    if graves:
        detalhe += " | EXPOSTA: " + ", ".join(f"{ip}:{p}" for p, ip in graves)
    if avisos:
        detalhe += " | AVISO: LM Studio aberto na rede (" + ", ".join(f"{ip}:{p}" for p, ip in avisos) + ")"
    return (not graves, detalhe)


def portas_so_loopback() -> Check:
    escutando = [(c.laddr.port, c.laddr.ip) for c in psutil.net_connections("tcp") if c.status == psutil.CONN_LISTEN and c.laddr]
    return avaliar_portas(escutando)


def lmstudio_no_ar() -> Check:
    r = httpx.get(f"{LMSTUDIO}/v1/models", headers=_cab_lm(), timeout=3, trust_env=False)
    ids = [m["id"] for m in r.json()["data"]]
    return (MODELO in ids, f"modelos: {len(ids)}; {MODELO} {'presente' if MODELO in ids else 'AUSENTE (lms load ...)'}")


def avaliar_token(status: int) -> Check:
    """Puro: sem Authorization o LM Studio tem de responder 401."""
    if status == 401:
        return (True, "401 sem token")
    if status == 200:
        return (False, "LM Studio aceita chamadas sem token")
    return (False, f"HTTP {status} inesperado sem token")


def lmstudio_exige_token() -> Check:
    return avaliar_token(httpx.get(f"{LMSTUDIO}/v1/models", timeout=3, trust_env=False).status_code)


# Modelo com raciocínio gasta o orçamento de tokens em reasoning_content; por isso 256 e o fallback.
def gemma_gera() -> Check:
    r = httpx.post(f"{LMSTUDIO}/v1/chat/completions", json={"model": MODELO, "messages": [{"role": "user", "content": "Responda só: pong"}], "max_tokens": 256}, headers=_cab_lm(), timeout=60, trust_env=False)
    msg = r.json()["choices"][0]["message"]
    txt = msg.get("content") or msg.get("reasoning_content") or ""
    return ("pong" in txt.lower(), txt.strip()[:40])


def omniroute_responde() -> Check:
    url = segredos.url_omniroute()
    if not url:
        return (True, "AVISO: OmniRouter não configurado ([omniroute] url no segredos.toml)")
    chave = segredos.chave_omniroute()
    r = httpx.post(f"{url}/v1/chat/completions", headers={"Authorization": f"Bearer {chave}", "User-Agent": "curl/8.0"},
                   json={"model": "combo/equipe", "messages": [{"role": "user", "content": "Responda só: pong"}], "max_tokens": 64}, timeout=60)
    msg = r.json()["choices"][0]["message"] if r.status_code == 200 else {}
    txt = msg.get("content") or msg.get("reasoning_content") or ""
    return (r.status_code == 200 and bool(txt.strip()), f"HTTP {r.status_code}; {txt.strip()[:30]}")


def openjarvis_no_ar() -> Check:
    r = httpx.get(f"{OPENJARVIS}/health", timeout=3, trust_env=False)
    return (r.status_code == 200, r.text[:60])


def openjarvis_lista_modelo() -> Check:
    ids = [m["id"] for m in httpx.get(f"{OPENJARVIS}/v1/models", timeout=5, trust_env=False).json()["data"]]
    return (MODELO in ids, f"{len(ids)} modelos")


def ponte_ask() -> Check:
    r = httpx.post(f"{PONTE}/ask", json={"texto": "diga apenas: olá"}, timeout=90, trust_env=False)
    return (r.status_code == 200 and bool(r.json().get("resposta")), r.json().get("resposta", r.text)[:60])


def ponte_see() -> Check:
    r = httpx.post(f"{PONTE}/see", files={"imagem": ("p.jpg", _jpeg_com_texto(), "image/jpeg")}, data={"pergunta": "Que palavra está escrita?"}, timeout=90, trust_env=False)
    txt = r.json().get("resposta", "")
    return (r.status_code == 200 and "preflight" in txt.lower(), txt[:60])


def mesa_lista_janelas() -> Check:
    r = httpx.post(f"{PONTE}/ask", json={"texto": "Use a ferramenta listar_janelas e responda só com o número de janelas."}, timeout=90, trust_env=False)
    resposta = r.json().get("resposta", "")
    return (r.status_code == 200 and re.search(r"\d", resposta) is not None, resposta[:60])


def mesa_responde_por_mcp() -> Check:
    # Mesmo caminho do OpenJarvis (stdio, leitor cp1252/UTF-8): prova a mesa sem passar pelo modelo.
    texto = mesa_cliente.chamar_ferramenta("listar_janelas")
    linhas = [l for l in texto.splitlines() if l.startswith("- ")]
    return (bool(linhas), f"{len(linhas)} janelas listadas")


def _openjarvis_enxerga(nomes) -> Check:
    tools = httpx.get(f"{OPENJARVIS}/v1/tools", timeout=5, trust_env=False).json().get("tools", [])
    vistos = {t["name"] for t in tools if t.get("source") == "mcp"}
    faltam = [n for n in nomes if n not in vistos]
    return (not faltam, f"{len(nomes)} ferramentas visíveis" if not faltam else f"faltam: {faltam}")


def openjarvis_enxerga_a_mesa() -> Check:
    return _openjarvis_enxerga(FERRAMENTAS_MESA)


def openjarvis_enxerga_a_oficina() -> Check:
    return _openjarvis_enxerga(FERRAMENTAS_OFICINA)


def openjarvis_enxerga_a_consulta() -> Check:
    return _openjarvis_enxerga(FERRAMENTAS_CONSULTA)


def avaliar_mcp_list(saida: str) -> Check:
    """Puro: lê `claude mcp list`; só interessa o Linear (D2) e quais outros conectores do claude.ai pedem autorização."""
    conectados: set[str] = set()
    pendentes: list[str] = []
    for linha in saida.splitlines():
        m = re.match(r"\s*claude\.ai\s+(.+?):\s", linha)
        if not m:
            continue
        nome = m.group(1).strip()
        if "needs authentication" in linha.lower():
            pendentes.append(nome)
        elif re.search(r"(?<!not )(?<!dis)connected", linha.lower()) and "failed" not in linha.lower():
            conectados.add(nome)
    if "Linear" not in conectados:
        return (True, "AVISO o Linear não está conectado no Claude (claude.ai > Conectores)")
    outros = [n for n in pendentes if n != "Linear"]
    return (True, "Linear conectado" + (f"; precisam de autorização: {', '.join(outros)}" if outros else ""))


def avaliar_respostas_delegada(saidas: dict) -> Check:
    """Puro: falha ou agente faltando derruba; sem login é só aviso (o usuário entra na aba do Orca)."""
    falhas = []
    for agente in delegada.AGENTES:
        s = saidas.get(agente)
        if s is None:
            falhas.append(f"{agente}: não respondeu")
        elif s.estado == "falhou":
            falhas.append(f"{agente}: {s.motivo}")
    if falhas:
        return (False, "; ".join(falhas))
    esperando = [a for a in delegada.AGENTES if saidas[a].estado == "esperando"]
    if esperando:
        return (True, "AVISO " + ", ".join(f"{a} sem login" if saidas[a].bloqueio == "login" else f"{a} esperando"
                                           for a in esperando))
    return (True, "os 4 responderam")


def delegada_config_valida() -> Check:
    """D1: o config carrega e os quatro .exe existem (nunca .cmd)."""
    conf = delegada.carregar()
    exes = {a: Path(delegada.resolver_exe(a, conf)).name for a in delegada.AGENTES}
    return (True, ", ".join(exes.values()))


def delegada_travas() -> Check:
    """D2: as travas de só leitura passam em `montar` dos quatro (o código recusa se uma sumir)."""
    conf = delegada.carregar()
    with tempfile.TemporaryDirectory() as tmp:
        for a in delegada.AGENTES:
            delegada.montar(a, "teste", conf, Path(tmp), instrucoes="")
    return (True, "travas presentes nos 4")


def delegada_responde() -> Check:
    """D3: os quatro respondem juntos a uma pergunta mínima (4 chamadas reais; gasta cota)."""
    conf = delegada.carregar()
    saidas: dict = {}

    def um(agente: str) -> None:
        saidas[agente] = delegada.consultar(agente, "Responda só: ok", conf)

    ths = [threading.Thread(target=um, args=(a,), daemon=True) for a in delegada.AGENTES]
    for t in ths:
        t.start()
    for t in ths:
        t.join(conf.timeout_s + 30)
    return avaliar_respostas_delegada(saidas)


def claude_linear_conectado() -> Check:
    """D4: `claude mcp list` mostra o Linear do claude.ai conectado (conta e não pede autorização)."""
    conf = delegada.carregar()
    pasta = delegada.PASTA_NEUTRA / "claude"
    pasta.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([delegada.resolver_exe("claude", conf), "mcp", "list"], cwd=str(pasta), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return avaliar_mcp_list(r.stdout)


def consulta_github_por_mcp() -> Check:
    texto = mesa_cliente.chamar_ferramenta("github_prs", script="consulta_mcp.py")
    ok = bool(texto) and not texto.startswith(("Não consegui", "O gh"))
    return (ok, (texto.splitlines() or ["vazio"])[0][:70])


def avaliar_paineis(paineis: dict[str, dict]) -> Check | None:
    """Puro: sem painel completo (url e token) = aviso (passo P2 do usuário) dizendo o que falta; None = há o que testar."""
    if any(p.get("url") and p.get("token") for p in paineis.values()):
        return None
    if not paineis:
        return (True, "AVISO: sem [coolify.<painel>] no segredos.toml (url e token; scripts\\windows\\gravar-segredo.ps1 -Secao coolify.exemplo)")
    faltas = [f"{n}: falta {' e '.join(c for c in ('url', 'token') if not p.get(c))}" for n, p in paineis.items()]
    return (True, "AVISO: Coolify incompleto (" + "; ".join(faltas) + ")")


def coolify_responde() -> Check:
    paineis = segredos.coolify()
    aviso = avaliar_paineis(paineis)
    if aviso:
        return aviso
    partes, ok = [], True
    for nome, p in paineis.items():
        faltas = [c for c in ("url", "token") if not p.get(c)]
        if faltas:                       # painel pela metade: não é falha, mas aparece (não some em silêncio)
            partes.append(f"{nome}: falta {' e '.join(faltas)}")
            continue
        try:
            partes.append(f"{nome}: {len(consulta.coolify_get(p['url'], p['token'], 'applications'))} apps")
        except (httpx.HTTPError, ValueError, consulta.ErroConsulta) as exc:
            ok = False
            partes.append(f"{nome}: {type(exc).__name__}")
    return (ok, "; ".join(partes))


def agente_remoto_acessivel() -> Check:
    try:
        conf = remoto.carregar_conf()
    except (consulta.ErroConsulta, ValueError):
        return (True, "AVISO: agente remoto não configurado (remoto.toml; integração não configurada)")
    p = subprocess.run(remoto.comando_ssh(conf["chave"], conf["destino"], remoto.LISTAR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
                       stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        return (False, f"ssh falhou: {' '.join(p.stderr.split())[:80]}")
    if conf["container_prefixo"]:
        return (True, f"container {remoto.achar_container(p.stdout, conf['container_prefixo'], conf['nome'])}"
                      " (o agente remoto não foi chamado)")
    return (True, f"{conf['nome']} respondeu por ssh ({len(p.stdout.splitlines())} containers; o agente remoto não foi chamado)")


def orca_no_ar() -> Check:
    ok = orca_cli.achar(Orca().status(), "reachable") is True
    return (ok, "runtime do Orca alcançável" if ok else "runtime do Orca fora (abra o Orca ou rode orca open)")


def avaliar_repos_orca(config: dict[str, str], no_orca: list[str]) -> Check:
    """Puro: cada repo de repos.toml está registrado no Orca (comparação sem caixa e com barra normal)."""
    norma = lambda p: p.replace("\\", "/").rstrip("/").lower()  # noqa: E731
    registrados = {norma(p) for p in no_orca}
    faltam = [a for a, c in config.items() if norma(c) not in registrados]
    return (not faltam, "todos registrados no Orca" if not faltam else f"fora do Orca: {faltam} (orca repo add --path)")


def repos_da_oficina_no_orca() -> Check:
    repos = oficina_mod.carregar_repos()
    sumidos = [a for a, r in repos.items() if not Path(r.caminho).exists()]
    if sumidos:
        return (False, f"pasta não existe: {sumidos}")
    return avaliar_repos_orca({a: r.caminho for a, r in repos.items()}, Orca().repos())


def oficina_responde_por_mcp() -> Check:
    texto = mesa_cliente.chamar_ferramenta("listar_tarefas", script="oficina_mcp.py")
    return (bool(texto) and not texto.startswith("Não consegui"), (texto.splitlines() or ["vazio"])[0][:60])


def segredos_fora_do_alcance() -> Check:
    r = httpx.get(f"{PONTE}/segredos.toml", timeout=3, trust_env=False)
    return (r.status_code == 404, f"HTTP {r.status_code}")


def arquivos_servidos_batem() -> Check:
    diferentes = []
    for nome in ("index.html", "app.js", "rotas.js", "falas.js"):
        disco = hashlib.sha256((RAIZ / "viewer" / nome).read_bytes()).hexdigest()
        rede = hashlib.sha256(httpx.get(f"{PONTE}/viewer/{nome}", timeout=3, trust_env=False).content).hexdigest()
        if disco != rede:
            diferentes.append(nome)
    return (not diferentes, "iguais" if not diferentes else f"diferentes: {diferentes}")


def mute_respeitado() -> Check:
    html = httpx.get(f"{PONTE}/viewer/app.js", timeout=3, trust_env=False).text
    return ("if (mudo) return;" in html, "checagem dentro de falar()")


def _patch_oj() -> Path | None:
    """_channel_kwargs.py dentro do openjarvis_src do instalacao.json; None = OpenJarvis não configurado."""
    src = str(instalacao.ler().get("openjarvis_src", "")).strip()
    return (Path(src) / "src" / "openjarvis" / "system" / "_channel_kwargs.py") if src else None


def avaliar_status_ciclo(dados: dict) -> Check:
    """Puro: `vard-modo.ps1 status` já resolvido em dict (PIDs None = morto)."""
    faltam = [n for n in ("openjarvis", "ponte", "bandeja") if not dados.get(n)]
    problemas = []
    if dados.get("modo") != "ligado":
        problemas.append(f"modo {dados.get('modo')}")
    if faltam:
        problemas.append("sem PID: " + ", ".join(faltam))
    if not dados.get("variaveis_ok"):
        problemas.append("variáveis de usuário ausentes")
    if problemas:
        return (False, "; ".join(problemas))
    return (True, f"modo ligado; 3 processos vivos; {dados.get('lmstudio_modelos')} modelo(s) no LM Studio")


def avaliar_canal_telegram(enabled: bool, chat_ids: str) -> Check:
    """Puro: config viva do `[channel]`."""
    if not enabled:
        return (True, "AVISO: canal desligado (mande /start ao bot e rode telegram-chat-id.ps1)")
    if not str(chat_ids).strip():
        return (False, "canal ligado sem allowed_chat_ids: o bot atenderia qualquer chat")
    return (True, "canal ligado com allowed_chat_ids preenchido")


def _home_openjarvis() -> str:
    """Casa do OpenJarvis: OPENJARVIS_HOME no ambiente, depois openjarvis_home do instalacao.json."""
    valor = os.environ.get("OPENJARVIS_HOME", "").strip()
    if valor:
        return valor
    casa = str(instalacao.ler().get("openjarvis_home", "")).strip()
    if casa:
        return casa
    raise FileNotFoundError("OpenJarvis não configurado (OPENJARVIS_HOME ou instalacao.json openjarvis_home)")


def _openjarvis_configurado() -> bool:
    try:
        _home_openjarvis()
        return True
    except FileNotFoundError:
        return False


def _sem_openjarvis() -> Check:
    return (True, "AVISO: OpenJarvis não configurado (OPENJARVIS_HOME ou instalacao.json openjarvis_home)")


def _config_viva() -> dict:
    with open(Path(_home_openjarvis()) / "config.toml", "rb") as f:
        return tomllib.load(f)


def ciclo_de_vida_ligado() -> Check:
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT_MODO), "status"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    linhas = [l for l in r.stdout.splitlines() if l.strip().startswith("{")]
    if not linhas:
        return (False, f"status sem JSON (código {r.returncode})")
    dados = json.loads(linhas[-1])
    for n in ("openjarvis", "ponte", "bandeja"):
        if dados.get(n) and not psutil.pid_exists(int(dados[n])):
            dados[n] = None
    return avaliar_status_ciclo(dados)


def inicio_no_logon_registrado() -> Check:
    lnk = os.path.join(os.environ["APPDATA"], "Microsoft/Windows/Start Menu/Programs/Startup/Vard.lnk")
    if os.path.exists(lnk):
        return (True, "Vard.lnk na pasta Startup")
    return (True, "AVISO: Vard.lnk ausente na pasta Startup (rode scripts\\windows\\tarefa-logon.ps1)")


def avaliar_origin(status: int) -> Check:
    """Puro: POST /modo com Origin estranho e verbo inválido. 403 = a guarda barrou antes da rota;
    422 = o pedido chegou à rota (guarda sumiu). O verbo inválido garante que nada é disparado."""
    if status == 403:
        return (True, "HTTP 403: guarda de Origin ativa")
    if status == 422:
        return (False, "HTTP 422: a guarda de Origin sumiu (o pedido chegou ao /modo)")
    return (False, f"HTTP {status} inesperado")


def origin_recusada() -> Check:
    r = httpx.post(f"{PONTE}/modo", headers={"Origin": "http://malicioso.exemplo"}, json={"modo": "nada"}, timeout=5, trust_env=False)
    return avaliar_origin(r.status_code)


def avaliar_sonda(conteudo: str | None, desde_ms: int) -> Check:
    """Puro: conteúdo de sonda.txt (ms Unix gravado pelo script) contra a hora do disparo."""
    if conteudo is None:
        return (False, "sonda.txt não apareceu: o disparo não roda o script")
    try:
        valor = int(conteudo.strip())
    except ValueError:
        return (False, "sonda.txt ilegível")
    if valor < desde_ms:
        return (False, "sonda.txt antigo em 10 s: o disparo não roda o script")
    return (True, f"script rodou {valor - desde_ms} ms depois do disparo")


def modo_dispara_de_verdade() -> Check:
    # Mesmo caminho da ponte e da bandeja (modo.disparar), com o verbo inofensivo 'sonda'.
    desde = int(time.time() * 1000)
    modo.disparar("sonda")
    conteudo = None
    fim = time.monotonic() + 10
    while time.monotonic() < fim:
        try:
            conteudo = modo.ARQUIVO_SONDA.read_text(encoding="ascii")
        except OSError:
            conteudo = None
        if avaliar_sonda(conteudo, desde)[0]:
            break
        time.sleep(0.25)
    return avaliar_sonda(conteudo, desde)


def telegram_conectado() -> Check:
    if not _openjarvis_configurado():
        return _sem_openjarvis()
    cfg = _config_viva().get("channel", {})
    r = httpx.get(f"{OPENJARVIS}/v1/channels/status", timeout=5, trust_env=False)
    dados = r.json()
    if dados.get("status") == "not_configured" or not cfg.get("enabled"):
        return (True, "AVISO: canal desligado (mande /start ao bot e rode telegram-chat-id.ps1)")
    conectado = dados.get("channels", {}).get("telegram") == "connected" or dados.get("status") == "connected"
    return (conectado, "telegram connected" if conectado else f"telegram não conectado: {str(dados)[:80]}")


def allowed_chat_ids_preenchido() -> Check:
    if not _openjarvis_configurado():
        return _sem_openjarvis()
    cfg = _config_viva().get("channel", {})
    ids = cfg.get("telegram", {}).get("allowed_chat_ids", "")
    return avaliar_canal_telegram(bool(cfg.get("enabled")), str(ids))


def patch_telegram_aplicado() -> Check:
    alvo = _patch_oj()
    if alvo is None:
        return (True, "AVISO: OpenJarvis não configurado (instalacao.json openjarvis_src); patch não verificado")
    achou = 'kw["allowed_chat_ids"]' in alvo.read_text(encoding="utf-8")
    return (achou, "_channel_kwargs.py com allowed_chat_ids" if achou else "patch ausente: o bot atenderia qualquer chat")


def avaliar_transcricao(dados: dict) -> Check:
    texto = str(dados.get("text", ""))
    limpo = re.sub(r"[\s\-]+", "", texto.lower())   # o whisper às vezes escreve "Pre-flight"
    return ("preflight" in limpo, f"ouviu {texto.strip()[:40]!r}, esperava 'preflight'")


def fala_disponivel() -> Check:
    motivos, ok = [], True
    for nome, rota in (("transcrição", "/v1/speech/health"), ("síntese", "/v1/speech/tts/health")):
        d = httpx.get(f"{OPENJARVIS}{rota}", timeout=60, trust_env=False).json()
        if d.get("available") is not True:
            ok = False
        motivos.append(f"{nome}: {'ok' if d.get('available') is True else d.get('reason', d)}")
    return (ok, "; ".join(str(m) for m in motivos)[:160])


def transcreve_wav_fixo() -> Check:
    wav = (RAIZ / "tests" / "preflight-fala.wav").read_bytes()
    r = httpx.post(f"{OPENJARVIS}/v1/speech/transcribe", files={"file": ("preflight-fala.wav", wav, "audio/wav")},
                   data={"language": "pt"}, timeout=60, trust_env=False)
    if r.status_code != 200:
        return (False, f"HTTP {r.status_code}: {r.text[:80]}")
    return avaliar_transcricao(r.json())


def sintetiza_curto() -> Check:
    if not _openjarvis_configurado():
        return _sem_openjarvis()
    fala = _config_viva()["speech"]
    r = httpx.post(f"{OPENJARVIS}/v1/speech/synthesize",
                   json={"text": "Preflight ok, senhor.", "voice_id": fala["voice_id"], "speed": fala["voice_speed"]},
                   timeout=180, trust_env=False)
    tipo = r.headers.get("content-type", "")
    return (r.status_code == 200 and tipo.startswith("audio/wav") and len(r.content) > 10_000,
            f"HTTP {r.status_code}; {tipo}; {len(r.content)} bytes")


def voz_responde() -> Check:
    """vard-voz (XTTS) em :4710: /saude responde; aquecendo ainda conta como no ar."""
    d = httpx.get(f"{VOZ}/saude", timeout=5, trust_env=False).json()
    return (d.get("voz") == "Suad Qasim", f"pronta={d.get('pronta')} aquecida={d.get('aquecida')} device={d.get('device')}")


def avaliar_hora_rapida(resposta: str, segundos: float) -> Check:
    tem_hora = re.search(r"\d{1,2}\s*(?::|h|horas?)\s*\d{0,2}", resposta) is not None
    return (segundos < 4 and tem_hora, f"{segundos:.1f} s; {resposta.strip()[:50]}")


def hora_sem_raciocinio() -> Check:
    """Pelo OpenJarvis (:8000), com raciocínio desligado, a hora_atual ainda é chamada e a resposta vem em < 4 s."""
    ini = time.monotonic()
    r = httpx.post(f"{OPENJARVIS}/v1/chat/completions", json={"model": MODELO, "stream": False,
                   "messages": [{"role": "user", "content": "Que horas são?"}]}, timeout=30, trust_env=False)
    seg = time.monotonic() - ini
    return avaliar_hora_rapida(r.json()["choices"][0]["message"].get("content") or "", seg)


def avaliar_trava_vigia(fd: int | None) -> Check:
    """Puro (quase): fd None = outro processo segura a trava = há vigia. fd válido = ninguém vigiando."""
    if fd is None:
        return (True, "trava ocupada: um processo da oficina está vigiando")
    os.close(fd)
    return (False, "ninguém vigiando: o OpenJarvis subiu a oficina? (scripts\\windows\\vard-modo.ps1 recarregar)")


def vigia_viva() -> Check:
    return avaliar_trava_vigia(vigia.adquirir_trava())


def ponte_entrega_evento() -> Check:
    marca = uuid.uuid4().hex[:12]
    pronto, chegou = threading.Event(), threading.Event()

    def ouvir():
        try:
            with httpx.stream("GET", f"{PONTE}/events", timeout=httpx.Timeout(10, read=10), trust_env=False) as r:
                pronto.set()
                for linha in r.iter_lines():
                    if marca in linha:
                        chegou.set()
                        return
        except httpx.HTTPError:
            pronto.set()

    threading.Thread(target=ouvir, daemon=True).start()
    pronto.wait(5)
    time.sleep(0.3)
    r = httpx.post(f"{PONTE}/events/publicar", json={"tipo": "preflight", "marca": marca}, timeout=5, trust_env=False)
    ok = chegou.wait(5)
    return (r.status_code == 200 and ok, f"HTTP {r.status_code}; evento {'chegou' if ok else 'NÃO chegou'} no SSE")


def telegram_bot_responde() -> Check:
    token = segredos.chave_telegram()
    if not token:
        return (True, "AVISO: sem token do bot no segredos.toml")
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10, trust_env=False)
        ok = r.status_code == 200 and r.json().get("ok") is True
    except (httpx.HTTPError, ValueError) as exc:
        return (False, f"{type(exc).__name__} (detalhe omitido: a URL leva o token)")
    return (ok, "getMe ok (nenhuma mensagem enviada)" if ok else f"HTTP {r.status_code}")


def avaliar_ai_memory(url: str, token: str, listar=None) -> Check:
    """Sem token é aviso (passo P1), não falha. Com token: tools/list de verdade pelo Tailscale (5 s)."""
    if not token:
        return (True, "AVISO: sem token do ai-memory (scripts\\windows\\gravar-segredo.ps1 -Secao ai_memory -Chave token)")
    if listar is None:
        def listar():
            c = ClienteMCP(url, token, timeout=5)
            c.iniciar()
            return c.listar_ferramentas()
    try:
        nomes = {f.get("name") for f in listar()}
    except ErroMCP as exc:
        return (False, str(exc)[:80])
    ok = "memory_query" in nomes and "memory_write_page" in nomes
    return (ok, f"{len(nomes)} ferramentas no ai-memory" if ok else "ai-memory sem memory_query/memory_write_page")


def ai_memory_pelo_tailscale() -> Check:
    url, token = segredos.ai_memory()
    return avaliar_ai_memory(url, token)


def memoria_por_mcp() -> Check:
    texto = mesa_cliente.chamar_ferramenta("memoria_buscar", {"pergunta": "combos do OmniRouter"}, script="memoria_mcp.py")
    if texto.startswith(SEM_MEMORIA):
        return (True, "AVISO: memória sem token (passo P1)")
    return (not texto.startswith("Não consegui"), (texto.splitlines() or ["vazio"])[0][:70])


def openjarvis_enxerga_a_memoria() -> Check:
    return _openjarvis_enxerga(FERRAMENTAS_MEMORIA)


def avaliar_digest(d: dict, persona_existe: bool) -> Check:
    """Puro: [digest] da config viva + arquivo de persona instalado."""
    problemas = []
    if d.get("enabled"):
        problemas.append("enabled=true (a vigia é quem agenda)")
    if d.get("persona") != "vard" or not persona_existe:
        problemas.append("persona vard ausente")
    if "news_rss" not in d.get("world", {}).get("sources", []):
        problemas.append("world sem news_rss")
    return (not problemas, "digest pronto (persona vard, notícias por RSS)" if not problemas else "; ".join(problemas))


def manha_config_viva() -> Check:
    if not _openjarvis_configurado():
        return _sem_openjarvis()
    persona = Path(_home_openjarvis()) / "prompts" / "personas" / "vard.md"
    return avaliar_digest(_config_viva().get("digest", {}), persona.exists())


def avaliar_feed(status: int, corpo: str) -> bool:
    inicio = corpo[:2000].lower()
    return status == 200 and ("<rss" in inicio or "<feed" in inicio)


def feeds_respondem() -> Check:
    if not _openjarvis_configurado():
        return _sem_openjarvis()
    arq = Path(_home_openjarvis()) / "connectors" / "news_rss.json"
    try:
        feeds = json.loads(arq.read_text(encoding="utf-8"))["feeds"]
    except (OSError, ValueError, KeyError, TypeError):
        return (False, "news_rss.json ausente ou inválido (scripts/windows/aplicar-config.ps1)")
    ruins = []
    for f in feeds:
        try:
            r = httpx.get(f["url"], timeout=10, follow_redirects=True, trust_env=False, headers={"User-Agent": "Mozilla/5.0"})
            if not avaliar_feed(r.status_code, r.text[:200_000]):
                ruins.append(f"{f['name']} (HTTP {r.status_code})")
        except httpx.HTTPError as exc:
            ruins.append(f"{f['name']} ({type(exc).__name__})")
    return (not ruins, f"{len(feeds)} fontes ok" if not ruins else f"fora: {', '.join(ruins)}")


def avaliar_contexto(prompt_tokens: int | None, limite: int = 9000) -> Check:
    """Puro: tokens de prompt de um 'oi' pelo agente (persona + ferramentas). O Gemma roda com 16k."""
    if prompt_tokens is None:
        return (True, "AVISO: o OpenJarvis não devolveu usage; medir no log do LM Studio")
    return (prompt_tokens <= limite, f"{prompt_tokens} tokens de prompt para um 'oi' (limite {limite} de 16k)")


def contexto_cabe() -> Check:
    r = httpx.post(f"{OPENJARVIS}/v1/chat/completions", timeout=60, trust_env=False,
                   json={"model": MODELO, "stream": False, "messages": [{"role": "user", "content": "oi"}]})
    try:
        uso = (r.json().get("usage") or {}).get("prompt_tokens")
    except ValueError:
        uso = None
    return avaliar_contexto(int(uso) if uso else None)   # 0 = metadata ausente, não "0 tokens"


def google_conectado() -> Check:
    if not _openjarvis_configurado():
        return _sem_openjarvis()
    pasta = Path(_home_openjarvis()) / "connectors"
    if any((pasta / n).exists() for n in ("google.json", "gmail.json")):
        return (True, "Google conectado (e-mail, agenda e tarefas entram na manhã)")
    return (True, "AVISO: Google não conectado (passo P3: jarvis connect gmail); a manhã sai só com notícias e Liv")


# ---------------------------------------------------------------- modo reunião (R1 a R7)
# O preflight nunca sobe o serviço 4720: sem ele, R1/R2/R6 viram aviso. Sem teclado, sem mouse.

AVISO_SEM_REUNIAO = "AVISO: modo reunião não instalado/ligado (porta 4720 não responde; vard-modo sobe o serviço)"


def _reuniao_no_ar() -> dict | None:
    """GET /status do 4720, ou None se a porta não responde."""
    try:
        r = httpx.get(f"{REUNIAO}/status", timeout=5, trust_env=False)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def avaliar_servico_reuniao(get: int, host: int, origin: int) -> Check:
    """Puro: GET /status 200; Host estranho 421; Origin em POST 403."""
    problemas = []
    if get != 200:
        problemas.append(f"GET /status HTTP {get}")
    if host != 421:
        problemas.append(f"Host externo HTTP {host} (esperava 421)")
    if origin != 403:
        problemas.append(f"Origin em POST HTTP {origin} (esperava 403)")
    if problemas:
        return (False, "; ".join(problemas))
    return (True, "GET /status 200; Host externo 421; Origin 403")


def reuniao_servico_no_ar() -> Check:
    if _reuniao_no_ar() is None:
        return (True, AVISO_SEM_REUNIAO)
    get = httpx.get(f"{REUNIAO}/status", timeout=5, trust_env=False).status_code
    host = httpx.get(f"{REUNIAO}/status", headers={"Host": "evil"}, timeout=5, trust_env=False).status_code
    origin = httpx.post(f"{REUNIAO}/falante", headers={"Origin": "http://malicioso.exemplo"}, timeout=5,
                        trust_env=False).status_code        # corpo vazio: a guarda barra antes da rota, sem efeito
    return avaliar_servico_reuniao(get, host, origin)


def _simples(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def avaliar_transcricao_reuniao(falas: list[dict], referencia: str, minimo: float = 0.8) -> Check:
    """Puro: a trilha `outros` (loopback) tem de bater com o texto do WAV tocado (>= 0,8)."""
    outros = " ".join(str(f.get("texto", "")) for f in falas if f.get("trilha") == "outros").strip()
    if not outros:
        trilhas = sorted({str(f.get("trilha")) for f in falas if f.get("trilha") != "sistema"})
        return (False, f"nenhuma fala na trilha outros (trilhas com texto: {trilhas or 'nenhuma'})")
    sim = difflib.SequenceMatcher(None, _simples(outros), _simples(referencia)).ratio()
    txt = f"similaridade {sim:.2f}".replace(".", ",")
    if sim >= minimo:
        return (True, f"{txt} na trilha outros")
    return (False, f"{txt} < 0,8; ouviu {outros[:60]!r}")


def _tocar_wav(caminho: Path) -> subprocess.Popen:
    """Toca o WAV na saída padrão (o loopback do serviço o captura). Só áudio: nada de teclado ou mouse."""
    return subprocess.Popen(
        ["powershell", "-NoProfile", "-Command",
         f"(New-Object System.Media.SoundPlayer '{caminho}').PlaySync()"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


MSG_ATIVA = "reunião de teste ficou ativa: encerre no 4720 (POST /encerrar)"
MSG_SALVAR = "o 4720 encerrou sem salvar reuniao.json; pasta de teste mantida para conferir"


def encerrar_reuniao_de_teste(url: str) -> tuple[str, str | None]:
    """POST no encerramento (4720 direto ou pela ponte). Devolve ("ok"|"salvar"|"ativa", nome da pasta ou None).
    200 e 409 "inativa" = encerrada; 409 "salvar" = encerrada sem salvar; resto (inclui exceção) = pode estar ativa."""
    try:
        e = httpx.post(url, timeout=60, trust_env=False)
        try:
            corpo = e.json()
        except ValueError:
            corpo = {}
        corpo = corpo if isinstance(corpo, dict) else {}
        if e.status_code == 200:
            return "ok", corpo.get("pasta")
        if e.status_code == 409:
            return ("salvar" if corpo.get("erro") == "salvar" else "ok"), corpo.get("pasta")
    except Exception:  # noqa: BLE001
        pass
    return "ativa", None


LOOPBACK: dict = {"pasta": None, "salvar_falhou": False}  # pasta da reunião de teste em curso (quem chama a apaga
#                                                        se sobrar) e se o encerramento não salvou (aí a pasta fica)


def executar_loopback(esperar_s: float = 15, apagar: bool = True) -> dict:
    """Roda a reunião de teste (iniciar, tocar o WAV, encerrar) e devolve as medições. Apaga só a própria pasta.
    Com `apagar=False` a pasta fica (quem pediu a apaga). Chaves: `aviso` se pulou; senão `falas`, `pasta`,
    `caminho`, `tocou_s` e, se houve fala, `primeira_fala_s`
    (segundos depois do fim do áudio)."""
    LOOPBACK["salvar_falhou"] = False
    st = _reuniao_no_ar()
    if st is None:
        return {"aviso": AVISO_SEM_REUNIAO}
    if st.get("ativa"):
        return {"aviso": "AVISO: já há uma reunião ativa; a prova do loopback não interfere"}
    r = httpx.post(f"{REUNIAO}/iniciar", timeout=30, trust_env=False)
    if r.status_code != 200:
        raise RuntimeError(f"/iniciar HTTP {r.status_code}: {r.text[:80]}")
    try:
        pasta_nome = str(r.json().get("pasta") or "")      # "pasta": null cai no /status abaixo
    except (ValueError, AttributeError):
        pasta_nome = ""
    if not pasta_nome:                                     # 200 sem JSON útil: o /status sabe qual é a pasta
        pasta_nome = str((_reuniao_no_ar() or {}).get("pasta") or "")
    saida: dict = {"pasta": pasta_nome}
    LOOPBACK["pasta"] = pasta_nome or None                 # visível a quem chama, mesmo se uma exceção sair daqui
    erro: Exception | None = None
    interrompido = True                                    # vira False se o corpo terminou ou deu Exception
    resultado, pasta = "ativa", None
    try:
        time.sleep(1.0)                                    # o stream de loopback precisa estar aberto
        ini = time.monotonic()
        _tocar_wav(WAV_REUNIAO).wait(timeout=60)
        saida["tocou_s"] = time.monotonic() - ini
        fim_audio = time.monotonic()
        while time.monotonic() - fim_audio < esperar_s:
            if int(httpx.get(f"{REUNIAO}/status", timeout=5, trust_env=False).json().get("falas", 0)) >= 1:
                saida["primeira_fala_s"] = time.monotonic() - fim_audio
                break
            time.sleep(0.25)
        interrompido = False
    except Exception as exc:  # noqa: BLE001 — o encerramento abaixo roda sempre; o erro volta depois
        erro, interrompido = exc, False
    finally:                                               # também com Ctrl+C: a reunião de teste nunca fica ativa
        resultado, nome = encerrar_reuniao_de_teste(f"{REUNIAO}/encerrar")
        pasta_nome = nome or pasta_nome
        if resultado == "salvar":
            LOOPBACK["salvar_falhou"] = True               # quem apaga a pasta depois (prova-reuniao) a mantém
        if resultado != "ok" and interrompido:             # o Ctrl+C segue; sem isto o aviso sumiria
            print("AVISO: " + (MSG_ATIVA if resultado == "ativa" else MSG_SALVAR))
        if resultado == "ok" and pasta_nome:
            try:
                pasta = reuniao_mod.caminho_pasta(pasta_nome)
                saida["falas"] = reuniao_mod.carregar_falas(pasta)
            except Exception:  # noqa: BLE001 — sem transcrição: o avaliador acusa
                saida["falas"] = []
            saida["caminho"] = pasta
            if apagar and pasta is not None:
                shutil.rmtree(pasta, ignore_errors=True)
                LOOPBACK["pasta"] = None
    if resultado != "ok":
        msg = MSG_ATIVA if resultado == "ativa" else MSG_SALVAR
        raise RuntimeError(f"{erro}; {msg}" if erro else msg) from erro
    if erro:
        raise erro
    return saida


def reuniao_loopback_transcreve() -> Check:
    if not WAV_REUNIAO.exists() or not TXT_REUNIAO.exists():
        return (True, MSG_ATIVO_AUSENTE.format(pasta=PASTA_ATIVOS))
    try:
        saida = executar_loopback()
    except Exception as exc:  # noqa: BLE001 — a falha sai explícita, sem derrubar o resto do preflight
        return (False, f"{type(exc).__name__}: {exc}"[:200])
    if "aviso" in saida:
        return (True, saida["aviso"])
    ok, detalhe = avaliar_transcricao_reuniao(saida["falas"], TXT_REUNIAO.read_text(encoding="utf-8"))
    if "primeira_fala_s" in saida:
        detalhe += f"; 1ª fala {saida['primeira_fala_s']:.1f} s depois do fim do áudio".replace(".", ",")
        return (ok, detalhe)
    return (False, "nenhuma fala em 15 s depois do áudio; " + detalhe)


def wav_16k_mono(dados: bytes) -> bytes:
    """WAV qualquer (PCM 16 bits) -> 16 kHz mono, interpolação linear (sem numpy)."""
    with wave.open(io.BytesIO(dados)) as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"WAV de {8 * w.getsampwidth()} bits: só PCM de 16 bits")
        canais, taxa, bruto = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
    amostras = array.array("h")
    amostras.frombytes(bruto)
    if canais > 1:
        amostras = array.array("h", [sum(amostras[i:i + canais]) // canais
                                     for i in range(0, len(amostras) - canais + 1, canais)])
    n = int(len(amostras) * 16000 / taxa)
    out = array.array("h")
    for i in range(n):
        pos = i * taxa / 16000
        j = int(pos)
        frac = pos - j
        b = amostras[min(j + 1, len(amostras) - 1)]
        out.append(int(amostras[j] * (1 - frac) + b * frac))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(out.tobytes())
    return buf.getvalue()


def transcrever_wav_reuniao() -> tuple[str, float]:
    """Manda o WAV de teste (16 kHz mono) ao whisper do OpenJarvis como o serviço faz; devolve (texto, segundos)."""
    wav = wav_16k_mono(WAV_REUNIAO.read_bytes())
    ini = time.monotonic()
    r = httpx.post(f"{OPENJARVIS}/v1/speech/transcribe", files={"file": ("segmento.wav", wav, "audio/wav")},
                   data={"language": "pt"}, timeout=60, trust_env=False)
    seg = time.monotonic() - ini
    r.raise_for_status()
    return str(r.json().get("text", "")).strip(), seg


def avaliar_latencia_reuniao(texto: str, segundos: float, limite: float = 5.0) -> Check:
    if not texto.strip():
        return (False, "o whisper devolveu texto vazio")
    tempo = f"{segundos:.1f}".replace(".", ",")
    if segundos < limite:
        return (True, f"{tempo} s para o segmento de ~8 s")
    return (False, f"{tempo} s (limite {limite:.0f} s)")


def reuniao_latencia() -> Check:
    if not WAV_REUNIAO.exists():
        return (True, MSG_ATIVO_AUSENTE.format(pasta=PASTA_ATIVOS))
    texto, seg = transcrever_wav_reuniao()
    return avaliar_latencia_reuniao(texto, seg)


def avaliar_ata_reuniao(md: str, pdf: bytes, segundos: float, limite_s: float = 180) -> Check:
    """Puro: as 5 seções, PDF de verdade (> 10 kB); AVISO (não falha) se o Gemma passou de 3 min."""
    faltam = [s for s in SECOES_ATA if f"## {s}" not in md]
    if faltam:
        return (False, f"ata sem seção: {', '.join(faltam)}")
    if not pdf.startswith(b"%PDF"):
        return (False, "ata.pdf não começa com %PDF")
    if len(pdf) <= 10_000:
        return (False, f"ata.pdf com {len(pdf) / 1000:.1f} kB (esperava > 10 kB)".replace(".", ","))
    detalhe = f"{len(SECOES_ATA)} de {len(SECOES_ATA)} seções; PDF {len(pdf) // 1000} kB; {segundos:.0f} s"
    if segundos > limite_s:
        detalhe += f" | AVISO: o Gemma levou mais de {limite_s / 60:.0f} min"
    return (True, detalhe)


_ESTADO_ATA: dict = {}


def reuniao_ata_fixture() -> Check:
    """gerar_ata real (Gemma já carregado, sem trocar modelo) na fixture de 40 min, em %TEMP% (nunca em reunioes\\)."""
    _ESTADO_ATA.clear()
    pasta = Path(tempfile.mkdtemp(prefix="vard-ata-preflight-"))
    try:
        shutil.copy(FIXTURE_ATA, pasta / "transcricao.jsonl")
        (pasta / "reuniao.json").write_text(json.dumps(
            {"pasta": pasta.name, "inicio": "2026-10-13T15:00:00", "fim": "2026-10-13T15:40:00", "duracao_s": 2400,
             "guardar_audio": False, "trilhas": ["eu", "outros"], "falantes": {}}), encoding="utf-8")
        (pasta / "tmp").mkdir()
        (pasta / "tmp" / "outros.flac").write_bytes(b"fLaC")        # só para provar que a ata o apaga (R5)
        ini = time.monotonic()
        md_arq = reuniao_mod.gerar_ata(pasta, "ata")                 # chamar_gemma real
        seg = time.monotonic() - ini
        _ESTADO_ATA["tmp_existe"] = (pasta / "tmp").exists()
        return avaliar_ata_reuniao(md_arq.read_text(encoding="utf-8"), (pasta / "ata.pdf").read_bytes(), seg)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def avaliar_audio_some(tmp_existe: bool | None) -> Check:
    if tmp_existe is None:
        return (False, "a ata da fixture não rodou (veja a checagem anterior)")
    return (not tmp_existe, "tmp\\ apagada junto com a ata" if not tmp_existe else "tmp\\ (áudio) sobrou depois da ata")


def reuniao_audio_some() -> Check:
    return avaliar_audio_some(_ESTADO_ATA.get("tmp_existe"))


def avaliar_diarizacao_reuniao(status: dict) -> Check:
    """Puro: `/status` do 4720. Offline é obrigatório; modelo não pronto ou só a reserva vira AVISO."""
    est = status.get("diarizacao") or {}
    if not status.get("offline"):
        return (False, "o processo do 4720 não roda com HF_HUB_OFFLINE=1 (ou é uma versão sem o campo offline)")
    if not status.get("telemetria_desligada"):
        return (False, "o processo do 4720 não tem PYANNOTE_METRICS_ENABLED=0 (telemetria do pyannote ligada, ou versão sem o campo telemetria_desligada)")
    if not est.get("pronta"):
        return (True, f"AVISO: diarização não pronta ({est.get('motivo') or 'sem motivo'}); rode scripts\\windows\\instalar-reuniao.ps1")
    modo_diar = est.get("modo")
    if modo_diar != "community-1":
        return (True, f"AVISO: diarização pronta no modo {modo_diar}, não no community-1; processo offline")
    return (True, "community-1 pronto, processo offline (HF_HUB_OFFLINE=1)")


def reuniao_diarizacao_offline() -> Check:
    st = _reuniao_no_ar()
    if st is None:
        return (True, AVISO_SEM_REUNIAO)
    return avaliar_diarizacao_reuniao(st)


def avaliar_jogo(texto: str) -> Check:
    """Puro: texto da função Jogo; EncerrarReuniao tem de vir antes de `InvocarLms unload`."""
    if not texto:
        return (False, "função Jogo não achada em vard-modo.ps1")
    if "EncerrarReuniao" not in texto:
        return (False, "Jogo não chama EncerrarReuniao")
    if "InvocarLms unload" not in texto:
        return (False, "Jogo sem `InvocarLms unload`")
    if texto.index("EncerrarReuniao") > texto.index("InvocarLms unload"):
        return (False, "EncerrarReuniao vem depois do unload (tem de vir antes)")
    return (True, "Jogo: EncerrarReuniao antes do unload do modelo")


def reuniao_jogo_estrutura() -> Check:
    """Lê a função Jogo pelo AST do PowerShell; nunca executa o script."""
    script = SCRIPT_MODO
    cmd = ("$ast = [System.Management.Automation.Language.Parser]::ParseFile('" + str(script).replace("'", "''") +
           "', [ref]$null, [ref]$null); "
           "$d = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] "
           "-and $n.Name -eq 'Jogo' }, $true) | Select-Object -First 1; [Console]::Out.Write($d.Extent.Text)")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    return avaliar_jogo(r.stdout)


def openjarvis_enxerga_a_reuniao() -> Check:
    return _openjarvis_enxerga(FERRAMENTAS_REUNIAO)


def reuniao_por_mcp() -> Check:
    texto = mesa_cliente.chamar_ferramenta("reuniao_status", script="reuniao_mcp.py")
    if texto.startswith(reuniao_mod.AUSENTE):
        return (True, "AVISO: " + texto)
    return (bool(texto) and not texto.startswith("Não consegui"), (texto.splitlines() or ["vazio"])[0][:70])


def normalizar_para_wer(texto: str) -> str:
    """Minúsculas, sem pontuação (acentos ficam)."""
    return " ".join(re.sub(r"[^\w\s]|_", " ", str(texto).lower()).split())


def checagens() -> list[tuple[str, Callable[[], Check]]]:
    return [
        ("Portas do Vard só em loopback", portas_so_loopback),
        ("LM Studio no ar com o Gemma", lmstudio_no_ar),
        ("LM Studio exige token", lmstudio_exige_token),
        ("Gemma gera texto", gemma_gera),
        ("OmniRouter responde com a chave vard-pc", omniroute_responde),
        ("OpenJarvis /health", openjarvis_no_ar),
        ("OpenJarvis lista o Gemma", openjarvis_lista_modelo),
        ("Fala disponível (whisper e Kokoro)", fala_disponivel),
        ("Transcreve o WAV fixo", transcreve_wav_fixo),
        ("Sintetiza uma frase curta", sintetiza_curto),
        ("vard-voz responde (XTTS Suad Qasim)", voz_responde),
        ("Reunião: serviço 4720 responde e recusa Host externo", reuniao_servico_no_ar),
        ("Reunião: loopback → whisper com o WAV fixo", reuniao_loopback_transcreve),
        ("Reunião: latência segmento → texto < 5 s", reuniao_latencia),
        ("Reunião: ata da fixture de 40 min", reuniao_ata_fixture),
        ("Reunião: áudio some depois da ata", reuniao_audio_some),
        ("Reunião: modelo de diarização offline", reuniao_diarizacao_offline),
        ("Reunião: modo jogo encerra a reunião antes do unload", reuniao_jogo_estrutura),
        ("OpenJarvis enxerga as ferramentas da reunião", openjarvis_enxerga_a_reuniao),
        ("Reunião: reuniao_status por MCP", reuniao_por_mcp),
        ("Ponte /ask responde", ponte_ask),
        ("Ponte /see lê um JPEG real", ponte_see),
        ("Mesa responde por MCP", mesa_responde_por_mcp),
        ("OpenJarvis enxerga as ferramentas da mesa", openjarvis_enxerga_a_mesa),
        ("Mesa: listar_janelas pelo agente", mesa_lista_janelas),
        ("Orca no ar", orca_no_ar),
        ("Repositórios da oficina registrados no Orca", repos_da_oficina_no_orca),
        ("Oficina responde por MCP (listar_tarefas)", oficina_responde_por_mcp),
        ("OpenJarvis enxerga as ferramentas da oficina", openjarvis_enxerga_a_oficina),
        ("Consulta: github_prs por MCP (gh autenticado)", consulta_github_por_mcp),
        ("Coolify responde com o token", coolify_responde),
        ("SSH acha o agente remoto", agente_remoto_acessivel),
        ("OpenJarvis enxerga as ferramentas da consulta", openjarvis_enxerga_a_consulta),
        ("Delegada: config e executáveis (.exe)", delegada_config_valida),
        ("Delegada: travas de só leitura nos comandos", delegada_travas),
        ("Delegada: os quatro respondem em modo de uma pergunta", delegada_responde),
        ("Delegada: Linear conectado no Claude", claude_linear_conectado),
        ("ai-memory responde pelo Tailscale com o token", ai_memory_pelo_tailscale),
        ("Memória: memoria_buscar por MCP", memoria_por_mcp),
        ("OpenJarvis enxerga as ferramentas da memória", openjarvis_enxerga_a_memoria),
        ("Rotina da manhã: digest configurado", manha_config_viva),
        ("Fontes de notícias respondem", feeds_respondem),
        ("Google conectado para a manhã", google_conectado),
        ("Vigia viva (trava ocupada)", vigia_viva),
        ("Ponte entrega evento no SSE", ponte_entrega_evento),
        ("Bot do Telegram responde (getMe)", telegram_bot_responde),
        ("Ciclo de vida: modo ligado, 3 processos", ciclo_de_vida_ligado),
        ("Disparo do modo roda o script (sonda)", modo_dispara_de_verdade),
        ("Início no logon registrado", inicio_no_logon_registrado),
        ("POST /modo com Origin estranho é recusado (verbo inválido)", origin_recusada),
        ("Telegram conectado", telegram_conectado),
        ("allowed_chat_ids preenchido", allowed_chat_ids_preenchido),
        ("Patch do OpenJarvis para allowed_chat_ids", patch_telegram_aplicado),
        ("Hora pelo OpenJarvis sem raciocínio (< 4 s)", hora_sem_raciocinio),
        ("Contexto inicial do agente cabe", contexto_cabe),
        ("segredos.toml não é servido", segredos_fora_do_alcance),
        ("Arquivos servidos batem com o disco", arquivos_servidos_batem),
        ("?mute=1 checado dentro de falar()", mute_respeitado),
    ]


def _sanitizar(texto: str) -> str:
    """Remove credenciais, tokens e caminhos pessoais da saída."""
    import re as _re
    # Tokens Bearer / API keys comuns
    texto = _re.sub(r"(Bearer\s+)\S+", r"\1***REDACTED***", texto, flags=_re.IGNORECASE)
    texto = _re.sub(r"(token|chave|secret|password|api[_-]?key)\s*[:=]\s*\S+", r"\1=***REDACTED***", texto, flags=_re.IGNORECASE)
    # Caminhos absolutos Windows com usuário
    texto = _re.sub(r"[A-Za-z]:\\Users\\[^\\]+", r"X:\\Users\\***USER***", texto)
    # UUIDs e hashes longos que podem ser segredos
    texto = _re.sub(r"[0-9a-fA-F]{32,}", "***HASH***", texto)
    return texto


def rodar_como_json() -> dict:
    """Executa todas as checagens e devolve resultado estruturado em JSON.

    Contrato T10c: {checagens: [{grupo, nome, estado, frase}], relatorio, duracao_ms}
    - grupo: derivado do nome da checagem (primeira palavra ou prefixo conhecido)
    - estado: "ok" | "aviso" | "falha"
    - frase: sanitizada (sem credenciais nem caminhos pessoais)
    """
    import time as _time
    inicio = _time.monotonic()
    resultados = []
    ok_count = falhas_count = avisos_count = 0

    # Mapeamento de prefixos para grupos
    def _grupo(nome: str) -> str:
        n = nome.lower()
        if n.startswith(("porta", "loopback")): return "Rede"
        if n.startswith(("lm studio", "gemma", "modelo")): return "Modelo"
        if n.startswith(("omni", "openjarvis", "ponte", "mesa", "oficina", "consulta", "delegada")): return "Integração"
        if n.startswith(("fala", "voz", "transcreve", "sintetiza", "whisper", "kokoro", "xtts")): return "Áudio"
        if n.startswith(("reunião", "reuniao", "ata", "diarização", "latência")): return "Reunião"
        if n.startswith(("orca", "repo", "coolify", "ssh", "agente remoto")): return "Infra"
        if n.startswith(("telegram", "bot")): return "Telegram"
        if n.startswith(("memória", "memoria", "ai-memory")): return "Memória"
        if n.startswith(("manhã", "rotina", "feed", "google", "digest")): return "Rotina"
        if n.startswith(("vigia", "trava")): return "Segurança"
        if n.startswith(("ciclo", "modo", "logon", "início")): return "Ciclo"
        if n.startswith(("segredo", "arquivo servido", "mute", "patch")): return "Configuração"
        if n.startswith(("hora", "contexto", "origin")): return "Runtime"
        return "Geral"

    for nome, fn in checagens():
        try:
            passou, detalhe = fn()
        except Exception as exc:
            passou, detalhe = False, f"{type(exc).__name__}: {_sanitizar(str(exc))}"[:200]

        detalhe_sanitizado = _sanitizar(detalhe)
        aviso = passou and "AVISO" in detalhe_sanitizado

        if aviso:
            estado = "aviso"
            avisos_count += 1
        elif passou:
            estado = "ok"
            ok_count += 1
        else:
            estado = "falha"
            falhas_count += 1

        resultados.append({
            "grupo": _grupo(nome),
            "nome": nome,
            "estado": estado,
            "frase": detalhe_sanitizado[:500],
        })

    duracao_ms = int((_time.monotonic() - inicio) * 1000)
    relatorio = f"{ok_count} ok, {falhas_count} falhas, {avisos_count} avisos ({duracao_ms} ms)"

    return {
        "checagens": resultados,
        "relatorio": relatorio,
        "duracao_ms": duracao_ms,
    }


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8", errors="replace")

    # Modo JSON (--json): saída estruturada para diagnostico.rs
    if "--json" in sys.argv:
        resultado = rodar_como_json()
        print(json.dumps(resultado, ensure_ascii=False))
        return 1 if any(c["estado"] == "falha" for c in resultado["checagens"]) else 0

    # Modo texto original (preservado)
    ok = falhas = avisos = 0
    for nome, fn in checagens():
        try:
            passou, detalhe = fn()
        except Exception as exc:
            passou, detalhe = False, f"{type(exc).__name__}: {exc}"[:120]
        aviso = passou and "AVISO" in detalhe
        marca = "!" if aviso else ("✔" if passou else "✘")
        print(f"{marca} {nome}: {detalhe}")
        ok += passou and not aviso; falhas += not passou; avisos += aviso
    print(f"\n{ok} ok, {falhas} falhas, {avisos} avisos")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
