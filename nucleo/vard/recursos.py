"""Monitor de recursos do Vard (0.9.4 leve; app único 0.9.7): memória e CPU por componente.

Desde o app único, o vard.exe é pai do núcleo, da voz, da reunião e dos MCPs. Por isso a conta
parte das árvores do vard.exe e dos PIDs registrados (pids/), nunca de nome solto, e cada processo
é classificado pelo comando: `uvicorn server:app` é o Núcleo, `*_mcp.py` são MCPs, `vard_voz` é a
Voz, `vard_reuniao` a Reunião, `bandeja.py` a Bandeja e o WebView2/vard.exe o Widget. Quem não se
reconhece (conhost, a CLI do cérebro) herda a categoria do pai. Cada processo conta uma vez só.

A CPU sai de uma amostragem única para todos os processos (uma espera curta, não uma por processo),
dividida pelos núcleos lógicos como no Gerenciador de Tarefas. As sondas HTTP (XTTS e os externos
OpenJarvis/LM Studio) rodam em paralelo durante essa espera, com prazo de conexão curto.
Memória de GPU por processo não entra: o Windows não a expõe de forma simples por aqui.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import psutil

from vard import config, sondas

log = logging.getLogger("vard.recursos")

CEREBRO_CLI = "Cérebro (CLI)"
COMPONENTES = ("Widget", "Núcleo", CEREBRO_CLI, "MCPs", "Voz", "Reunião", "Bandeja")
# CLIs do cérebro abertas pelo núcleo (vard/cerebro/cli_processos.py): elas e os filhos delas.
EXES_CLI = {"claude.exe", "claude", "agy.exe", "agy"}
# Nome do arquivo em pids/ -> componente (o vard-modo grava ponte/voz/reuniao/bandeja).
CATEGORIA_DO_PID = {
    "widget": "Widget", "app": "Widget", "nucleo": "Núcleo", "ponte": "Núcleo",
    "mcp": "MCPs", "mcps": "MCPs", "voz": "Voz", "reuniao": "Reunião", "bandeja": "Bandeja",
}
INTERVALO_CPU_S = 0.3
URL_VOZ = "http://127.0.0.1:4710/saude"
URL_OPENJARVIS = "http://127.0.0.1:8000/health"
URL_LMSTUDIO = "http://127.0.0.1:1234/v1/models"

_MCP = re.compile(r"_mcp\.py\b|windows-mcp")
_esperar = time.sleep  # ponto de troca dos testes


@dataclass
class ComponenteRecursos:
    nome: str
    memoria_mb: float = 0.0
    cpu_percent: float = 0.0
    pids: list[int] = field(default_factory=list)
    detalhes: str = ""


def classificar(nome: str, comando: list[str]) -> str | None:
    """Componente do Vard pelo comando do processo; None = não se reconhece (herda a do pai)."""
    linha = " ".join(comando).lower()
    exe = (nome or "").lower()
    if _MCP.search(linha):
        return "MCPs"
    if "uvicorn" in linha and "server:app" in linha:
        return "Núcleo"
    if "vard_voz" in linha:
        return "Voz"
    if "vard_reuniao" in linha:
        return "Reunião"
    if "bandeja.py" in linha:
        return "Bandeja"
    if exe in EXES_CLI:
        return CEREBRO_CLI
    if exe in ("msedgewebview2.exe", "vard.exe"):
        return "Widget"
    return None


def _ler_pids_registrados() -> dict[str, list[int]]:
    """Lê PIDs gravados na pasta de dados do Vard (pids/)."""
    pasta = config.pasta_dados() / "pids"
    resultado: dict[str, list[int]] = {}
    if not pasta.is_dir():
        return resultado
    for arq in pasta.glob("*.pid"):
        try:
            texto = arq.read_text(encoding="utf-8-sig").strip()
            # O vard-modo grava "PID|início" (o início confere que o PID ainda é o mesmo processo).
            pid = int(texto.splitlines()[0].split("|")[0].strip())
            nome = arq.stem
            resultado.setdefault(nome, []).append(pid)
        except (ValueError, OSError):
            continue
    return resultado


def _vard_ancestral() -> list[int]:
    """vard.exe acima deste núcleo (app único: o vard.exe é o pai do lançador do núcleo)."""
    try:
        return [p.pid for p in psutil.Process().parents() if (p.name() or "").lower() == "vard.exe"]
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return []


def _vard_por_nome() -> list[int]:
    """Instalação antiga (vard-modo): o widget não é pai do núcleo. Varredura lenta na 1ª vez (~segundos)."""
    achados: list[int] = []
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            if (proc.info.get("name") or "").lower() == "vard.exe":
                achados.append(proc.info["pid"])
    except Exception:  # noqa: BLE001
        pass
    return achados


def _processo_seguro(pid: int) -> psutil.Process | None:
    try:
        p = psutil.Process(pid)
        p.status()  # força NoSuchProcess se morreu
        return p
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None


def _nome(proc: psutil.Process) -> str:
    try:
        return proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return ""


def _comando(proc: psutil.Process) -> list[str]:
    try:
        return list(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return []


def _memoria_mb(proc: psutil.Process) -> float:
    try:
        return proc.memory_info().rss / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return 0.0


def _cpu_percent(proc: psutil.Process) -> float:
    """Sem espera: a primeira chamada arma o contador, a segunda mede desde a anterior."""
    try:
        return proc.cpu_percent(None)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return 0.0


def _raizes(pids_reg: dict[str, list[int]]) -> list[tuple[int, str]]:
    """Pontos de partida: o vard.exe (app único) e os PIDs registrados, com a categoria padrão de cada um."""
    widget = _vard_ancestral()
    if not widget and not (pids_reg.get("widget") or pids_reg.get("app")):
        widget = _vard_por_nome()
    raizes = [(pid, "Widget") for pid in widget]
    for arquivo, pids in pids_reg.items():
        categoria = CATEGORIA_DO_PID.get(arquivo)
        if categoria:
            raizes.extend((pid, categoria) for pid in pids)
    return raizes


def _ppid(proc: psutil.Process) -> int:
    try:
        return proc.ppid()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return 0


def _categoria(proc: psutil.Process, herdada: str, cli_pids: set[int]) -> str:
    """Debaixo de uma CLI do cérebro tudo conta para ela (MCPs que ela abriu inclusive)."""
    if herdada == CEREBRO_CLI or proc.pid in cli_pids:
        return CEREBRO_CLI
    return classificar(_nome(proc), _comando(proc)) or herdada


def _coletar_arvores(raizes: list[tuple[int, str]], cli_pids: set[int] | None = None
                     ) -> list[tuple[psutil.Process, str]]:
    """Cada processo das árvores, uma vez: (processo, componente). O filho sem comando reconhecido herda do pai."""
    cli_pids = cli_pids or set()
    vistos: set[int] = set()
    saida: list[tuple[psutil.Process, str]] = []
    for pid_raiz, padrao in raizes:
        if pid_raiz in vistos:
            continue
        raiz = _processo_seguro(pid_raiz)
        if raiz is None:
            continue
        try:
            descendentes = raiz.children(recursive=True)  # uma consulta por raiz (o psutil confere o início)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            descendentes = []
        categoria: dict[int, str] = {pid_raiz: _categoria(raiz, padrao, cli_pids)}
        vistos.add(pid_raiz)
        saida.append((raiz, categoria[pid_raiz]))
        pendentes = [d for d in descendentes if d.pid not in vistos]
        # Pai antes do filho: repete enquanto algum pendente tem o pai já classificado.
        while pendentes:
            resto = []
            for d in pendentes:
                pai = _ppid(d)
                if pai not in categoria:
                    resto.append(d)
                    continue
                categoria[d.pid] = _categoria(d, categoria[pai], cli_pids)
                if d.pid not in vistos:
                    vistos.add(d.pid)
                    saida.append((d, categoria[d.pid]))
            if len(resto) == len(pendentes):
                break  # pai sumiu no meio da leitura: o resto não tem como herdar
            pendentes = resto
    return saida


def _sondar(url: str) -> int | None:
    """Código HTTP de uma sonda curta, ou None quando não respondeu."""
    try:
        import httpx
        return httpx.get(url, timeout=sondas.prazo(url), trust_env=False).status_code
    except Exception:  # noqa: BLE001
        return None


def _detectar_xtts_carregado(voz_pids: list[int]) -> bool:
    """Verifica se o XTTS está carregado consultando /saude do serviço de voz."""
    if not voz_pids:
        return False
    try:
        import httpx
        r = httpx.get(URL_VOZ, timeout=sondas.prazo(URL_VOZ), trust_env=False)
        if r.status_code == 200:
            return bool(r.json().get("xtts"))
    except Exception:  # noqa: BLE001
        pass
    return False


def _detectar_externos() -> list[ComponenteRecursos]:
    """Detecta OpenJarvis e LM Studio rodando fora do Vard (as duas sondas ao mesmo tempo)."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        oj, lm = ex.map(_sondar, (URL_OPENJARVIS, URL_LMSTUDIO))
    externos: list[ComponenteRecursos] = []
    if oj is not None and oj < 400:
        externos.append(ComponenteRecursos(nome="OpenJarvis", detalhes="servidor externo ativo"))
    if lm is not None and lm < 400:
        externos.append(ComponenteRecursos(nome="LM Studio", detalhes="servidor externo ativo"))
    return externos


def coletar_recursos(cli_pids: list[int] | None = None) -> dict[str, Any]:
    """Coleta uso de recursos de todos os componentes do Vard. `cli_pids`: CLIs vivas do supervisor do núcleo."""
    processos = _coletar_arvores(_raizes(_ler_pids_registrados()), set(cli_pids or []))
    comps = {nome: ComponenteRecursos(nome=nome) for nome in COMPONENTES}
    for proc, categoria in processos:
        comps[categoria].pids.append(proc.pid)
        comps[categoria].memoria_mb += _memoria_mb(proc)

    with ThreadPoolExecutor(max_workers=2) as ex:
        xtts = ex.submit(_detectar_xtts_carregado, comps["Voz"].pids)
        fora = ex.submit(_detectar_externos)
        for proc, _c in processos:
            _cpu_percent(proc)          # arma o contador de todos
        _esperar(INTERVALO_CPU_S)       # uma espera só
        nucleos = psutil.cpu_count(logical=True) or 1
        for proc, categoria in processos:
            comps[categoria].cpu_percent += _cpu_percent(proc) / nucleos
        xtts_carregado = xtts.result()
        externos = fora.result()

    comps["Voz"].detalhes = f"XTTS {'carregado' if xtts_carregado else 'descarregado'}"
    componentes = [comps[nome] for nome in COMPONENTES]
    total_mem = sum(c.memoria_mb for c in componentes)
    total_cpu = sum(c.cpu_percent for c in componentes)

    return {
        "componentes": [
            {
                "nome": c.nome,
                "memoria_mb": round(c.memoria_mb, 1),
                "cpu_percent": round(c.cpu_percent, 1),
                "pids": c.pids[:10],  # limita lista para não inflar resposta
                "detalhes": c.detalhes,
            }
            for c in componentes
        ],
        "externos": [
            {"nome": e.nome, "detalhes": e.detalhes}
            for e in externos
        ],
        "total_memoria_mb": round(total_mem, 1),
        "total_cpu_percent": round(total_cpu, 1),
    }
