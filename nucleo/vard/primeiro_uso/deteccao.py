"""Detecção local do primeiro uso (T1, 0.9): reconhecer, sem efeito colateral.

Somente leitura. Procura executáveis em caminho informado, configuração existente, PATH e
locais conhecidos; faz sondas de versão curtas (3 s cada, 15 s no total) e lê a GPU pela API
do Windows (com sonda NVIDIA quando há `nvidia-smi`). Nunca faz login, nunca dispara tarefa,
nunca carrega modelo, nunca abre programa e nunca varre o disco inteiro.

Ferramenta sem sonda de versão segura fica "encontrado / versão não verificada"; opcional
ausente é aviso, não bloqueio. O caminho do executável é metadado local: não entra no
relatório exportável (só id, estado, versão e detalhe saem da rota).

Contrato (T1): `detectar() -> ResultadoDeteccao`; `como_dict()` devolve
`{itens:[{id,estado,versao,detalhe}],gpu:{estado,backend,vram_mb}}`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from vard import config

IDS = ("lmstudio", "lms", "orca", "claude", "codex", "opencode", "agy")

#: Estados de um item: achado, ausente ou (quando a própria sonda falha) não verificado.
EstadoItem = str
#: Estados da GPU.
EstadoGpu = str

PRAZO_PADRAO_S = 15.0
SONDA_PADRAO_S = 3.0


@dataclass(frozen=True)
class Item:
    id: str
    nome: str
    estado: EstadoItem
    versao: str
    detalhe: str
    caminho: str = ""   # metadado local; nunca sai no `como_dict`


@dataclass(frozen=True)
class Gpu:
    estado: EstadoGpu
    backend: str
    vram_mb: int | None
    detalhe: str = ""


@dataclass(frozen=True)
class ResultadoDeteccao:
    itens: tuple[Item, ...]
    gpu: Gpu
    duracao_ms: int

    def como_dict(self) -> dict:
        return {
            "itens": [
                {"id": i.id, "estado": i.estado, "versao": i.versao, "detalhe": i.detalhe}
                for i in self.itens
            ],
            "gpu": {"estado": self.gpu.estado, "backend": self.gpu.backend, "vram_mb": self.gpu.vram_mb},
        }


# --- Ambiente (injetável para os testes) ----------------------------------------

Executor = Callable[[Sequence[str], float], tuple[int, str, str]]
Which = Callable[[str], "str | None"]
Existe = Callable[[Path], bool]
HttpJson = Callable[[str, float], "dict | None"]


@dataclass(frozen=True)
class Ambiente:
    env: Mapping[str, str]
    which: Which
    existe: Existe
    rodar: Executor
    http_json: HttpJson
    config_dir: Path | None = None


def rodar_real(args: Sequence[str], timeout: float) -> tuple[int, str, str]:
    """Roda um comando local sem shell, sem janela, sem stdin e com prazo."""
    p = subprocess.run(
        [str(a) for a in args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return p.returncode, p.stdout, p.stderr


def http_json_real(url: str, timeout: float) -> "dict | None":
    """GET de leitura num servidor local; qualquer falha é ausência, nunca exceção."""
    try:
        import httpx

        r = httpx.get(url, timeout=timeout, trust_env=False)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def ambiente_real() -> Ambiente:
    return Ambiente(
        env=dict(os.environ), which=shutil.which, existe=lambda p: p.is_file(),
        rodar=rodar_real, http_json=http_json_real, config_dir=config.pasta_config(),
    )


def _env(amb: Ambiente, nome: str) -> str:
    return str(amb.env.get(nome, "") or "").strip()


# --- O que procurar -------------------------------------------------------------

@dataclass(frozen=True)
class Definicao:
    id: str
    nome: str
    nomes_path: tuple[str, ...]
    versao_args: tuple[str, ...]
    locais: tuple[Path, ...]
    chave_env: str = ""
    agente: str = ""
    servidor: bool = False   # além do executável, tentar o servidor local


def _definicoes(amb: Ambiente) -> tuple[Definicao, ...]:
    la, pf, up = _env(amb, "LOCALAPPDATA"), _env(amb, "PROGRAMFILES"), _env(amb, "USERPROFILE")

    def local(raiz: str, *partes: str) -> tuple[Path, ...]:
        return (Path(raiz).joinpath(*partes),) if raiz else ()

    return (
        Definicao(
            "lmstudio", "LM Studio", (), (), (
                *local(la, "Programs", "LM Studio", "LM Studio.exe"),
                *local(la, "Programs", "lm-studio", "LM Studio.exe"),
                *local(pf, "LM Studio", "LM Studio.exe"),
            ), servidor=True,
        ),
        Definicao("lms", "lms (CLI do LM Studio)", ("lms",), ("--version",),
                  (*local(up, ".lmstudio", "bin", "lms.exe"),)),
        Definicao("orca", "Orca", ("orca",), (),
                  (*local(la, "Programs", "orca", "resources", "bin", "orca.exe"),),
                  chave_env="VARD_ORCA_EXE"),
        Definicao("claude", "Claude Code", ("claude",), ("--version",),
                  (*local(up, ".local", "bin", "claude.exe"),), agente="claude"),
        Definicao("codex", "Codex", ("codex",), ("--version",),
                  (*local(up, ".local", "bin", "codex.exe"),), agente="codex"),
        Definicao("opencode", "OpenCode", ("opencode",), ("--version",),
                  (*local(up, ".opencode", "bin", "opencode.exe"),), agente="opencode"),
        Definicao("agy", "Antigravity", ("agy",), ("--version",), (), agente="agy"),
    )


def _exe_do_config(amb: Ambiente) -> dict[str, str]:
    """Caminhos de executável informados no delegada.toml (mecanismo já existente). Vazio se não houver."""
    if amb.config_dir is None:
        return {}
    try:
        import tomllib

        arquivo = Path(amb.config_dir) / "delegada.toml"
        if not arquivo.is_file():
            return {}
        with arquivo.open("rb") as f:
            dados = tomllib.load(f)
        agentes = dados.get("agentes", {})
        return {
            str(k): os.path.expandvars(str(v.get("exe", "")).strip())
            for k, v in agentes.items()
            if isinstance(v, dict) and str(v.get("exe", "")).strip()
        }
    except Exception:  # noqa: BLE001
        return {}


@dataclass(frozen=True)
class _Achado:
    caminho: str
    origem: str
    existe: bool
    erro: str = ""


def _candidatos(d: Definicao, amb: Ambiente, manual: Mapping[str, str], conf: Mapping[str, str]) -> list[tuple[str, str]]:
    cands: list[tuple[str, str]] = []
    if manual.get(d.id):
        cands.append((os.path.expandvars(manual[d.id]), "informado"))
    if d.chave_env and _env(amb, d.chave_env):
        cands.append((os.path.expandvars(_env(amb, d.chave_env)), "configurado"))
    if d.agente and conf.get(d.agente):
        cands.append((conf[d.agente], "configurado"))
    for nome in d.nomes_path:
        achado = amb.which(nome)
        if achado:
            cands.append((str(achado), "path"))
    cands.extend((str(p), "local conhecido") for p in d.locais)
    return cands


def _resolver_item(d: Definicao, amb: Ambiente, manual: Mapping[str, str], conf: Mapping[str, str]) -> _Achado:
    try:
        for caminho, origem in _candidatos(d, amb, manual, conf):
            if caminho and amb.existe(Path(caminho)):
                return _Achado(caminho, origem, True)
    except Exception as exc:  # noqa: BLE001
        return _Achado("", "", False, type(exc).__name__)
    return _Achado("", "", False)


# --- Sondas ---------------------------------------------------------------------

_RE_VERSAO = re.compile(r"\d+\.\d+(?:\.\d+)*")


def _parse_versao(texto: str) -> str:
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = _RE_VERSAO.search(linha)
        return (m.group(0) if m else linha)[:60]
    return ""


def _probe_versao(amb: Ambiente, caminho: str, args: Sequence[str], timeout: float) -> tuple[str, str]:
    try:
        rc, out, _err = amb.rodar([caminho, *args], timeout)
    except subprocess.TimeoutExpired:
        return "", "sonda de versão excedeu o tempo"
    except (FileNotFoundError, OSError):
        return "", "não foi possível executar a sonda de versão"
    except Exception:  # noqa: BLE001
        return "", "versão não verificada"
    if rc == 0:
        versao = _parse_versao(out)
        if versao:
            return versao, ""
    return "", "versão não verificada"


def _probe_servidor(amb: Ambiente, timeout: float) -> bool:
    base = _env(amb, "VARD_LMSTUDIO_URL") or "http://127.0.0.1:1234"
    try:
        return amb.http_json(f"{base.rstrip('/')}/v1/models", timeout) is not None
    except Exception:  # noqa: BLE001
        return False


_COMANDO_GPU = (
    "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
)


def _backend_gpu(nomes: Sequence[str]) -> str:
    texto = " ".join(nomes).lower()
    if "nvidia" in texto:
        return "nvidia"
    if "amd" in texto or "radeon" in texto or "advanced micro devices" in texto:
        return "amd"
    if "intel" in texto:
        return "intel"
    return "cpu"


def _vram_adapterram(dados: Sequence[dict]) -> int | None:
    for d in dados:
        try:
            n = int(d.get("AdapterRAM"))
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n // (1024 * 1024)
    return None


def _vram_nvidia(amb: Ambiente, timeout: float) -> int | None:
    exe = amb.which("nvidia-smi")
    if not exe:
        return None
    try:
        rc, out, _err = amb.rodar([exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"], timeout)
    except Exception:  # noqa: BLE001
        return None
    if rc != 0:
        return None
    for linha in out.splitlines():
        m = re.search(r"\d+", linha)
        if m:
            return int(m.group(0))
    return None


def _detectar_gpu(amb: Ambiente, timeout: float) -> Gpu:
    try:
        rc, out, _err = amb.rodar(["powershell", "-NoProfile", "-NonInteractive", "-Command", _COMANDO_GPU], timeout)
    except subprocess.TimeoutExpired:
        return Gpu("nao_verificado", "", None, "sonda de GPU excedeu o tempo")
    except Exception:  # noqa: BLE001
        return Gpu("nao_verificado", "", None, "não foi possível consultar a API de vídeo")
    if rc != 0 or not out.strip():
        return Gpu("nao_verificado", "", None, "API de vídeo do Windows indisponível")
    try:
        dados = json.loads(out)
    except ValueError:
        return Gpu("nao_verificado", "", None, "resposta inválida da API de vídeo")
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        return Gpu("nao_verificado", "", None, "resposta inválida da API de vídeo")
    registros = [d for d in dados if isinstance(d, dict)]
    nomes = [str(d.get("Name", "")).strip() for d in registros if str(d.get("Name", "")).strip()]
    backend = _backend_gpu(nomes)
    if backend == "nvidia":
        vram = _vram_nvidia(amb, timeout) or _vram_adapterram(registros)
    else:
        vram = _vram_adapterram(registros)
    if backend == "cpu":
        detalhe = "sem GPU dedicada detectada; o Vard segue em CPU"
        return Gpu("nao_encontrado", "cpu", vram, detalhe)
    detalhe = "VRAM estimada não garante execução CUDA" if backend == "nvidia" and vram else ""
    return Gpu("encontrado", backend, vram, detalhe)


# --- Orquestração ---------------------------------------------------------------

def detectar(
    ambiente: Ambiente | None = None,
    *,
    prazo_s: float = PRAZO_PADRAO_S,
    sonda_s: float = SONDA_PADRAO_S,
    caminhos: Mapping[str, str] | None = None,
) -> ResultadoDeteccao:
    """Detecta as ferramentas locais e a GPU sem nenhum efeito colateral."""
    inicio = time.monotonic()
    limite = inicio + max(0.0, prazo_s)
    amb = ambiente or ambiente_real()
    manual = {str(k): str(v) for k, v in (caminhos or {}).items() if v}
    conf = _exe_do_config(amb)
    defs = _definicoes(amb)

    achados = [_resolver_item(d, amb, manual, conf) for d in defs]

    versoes: dict[str, tuple[str, str]] = {}
    servidor_lm = False
    gpu: Gpu | None = None

    def orcamento() -> float:
        return max(0.0, min(sonda_s, limite - time.monotonic()))

    tarefas: dict = {}
    pool = ThreadPoolExecutor(max_workers=min(6, max(1, len(defs))))
    try:
        for d, achado in zip(defs, achados):
            if achado.existe and d.versao_args:
                restante = orcamento()
                if restante > 0:
                    tarefas[pool.submit(_probe_versao, amb, achado.caminho, d.versao_args, restante)] = d.id
            if d.servidor:
                restante = orcamento()
                if restante > 0:
                    tarefas[pool.submit(_probe_servidor, amb, restante)] = "::servidor"
        restante = orcamento()
        if restante > 0:
            tarefas[pool.submit(_detectar_gpu, amb, restante)] = "::gpu"

        for futuro in as_completed(tarefas, timeout=max(0.05, limite - time.monotonic())):
            chave = tarefas[futuro]
            try:
                valor = futuro.result()
            except Exception:  # noqa: BLE001
                continue
            if chave == "::gpu":
                gpu = valor
            elif chave == "::servidor":
                servidor_lm = bool(valor)
            else:
                versoes[chave] = valor
    except TimeoutError:
        pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if gpu is None:
        gpu = Gpu("nao_verificado", "", None, "sonda de GPU fora do prazo")

    itens = [_montar_item(d, a, versoes, servidor_lm) for d, a in zip(defs, achados)]
    return ResultadoDeteccao(itens=tuple(itens), gpu=gpu, duracao_ms=int((time.monotonic() - inicio) * 1000))


def _montar_item(d: Definicao, achado: _Achado, versoes: Mapping[str, tuple[str, str]], servidor_lm: bool) -> Item:
    if d.id == "lmstudio":
        if achado.existe and servidor_lm:
            return Item(d.id, d.nome, "encontrado", "", "instalado; servidor acessível", achado.caminho)
        if achado.existe:
            return Item(d.id, d.nome, "encontrado", "", "instalado; servidor fechado", achado.caminho)
        if servidor_lm:
            return Item(d.id, d.nome, "encontrado", "", "servidor acessível", achado.caminho)
        return Item(d.id, d.nome, "nao_encontrado", "", "não encontrado", "")

    if achado.erro:
        return Item(d.id, d.nome, "nao_verificado", "", f"detecção falhou ({achado.erro})", "")
    if not achado.existe:
        return Item(d.id, d.nome, "nao_encontrado", "", "não encontrado", "")
    versao, detalhe = versoes.get(d.id, ("", ""))
    if not d.versao_args:
        detalhe = detalhe or "versão não verificada"
    return Item(d.id, d.nome, "encontrado", versao, detalhe, achado.caminho)


# --- Recomendação leve (0.9.4 rodada 2) -----------------------------------------

@dataclass(frozen=True)
class RecomendacaoLeve:
    """Sugestão de configuração mais leve para o primeiro uso."""
    voz: str           # "kokoro" | "piper" | "xtts" | "edge"
    cerebro: str       # "openjarvis" | "lmstudio" | "api"
    motivo: str        # frase curta explicando a escolha


def recomendar_configuracao_leve(resultado: ResultadoDeteccao) -> RecomendacaoLeve:
    """Recomenda a opção mais leve que funcione na máquina detectada.

    Prioridade de voz: Kokoro/Piper (CPU, ~50 MB) > Edge (cloud, 0 MB local) > XTTS (GPU, ~2 GB).
    Prioridade de cérebro: OpenJarvis/API (sem modelo local) > LM Studio pequeno > LM Studio grande.
    """
    gpu = resultado.gpu
    tem_gpu = gpu.estado == "encontrado" and gpu.backend in ("nvidia", "amd")
    vram = gpu.vram_mb or 0

    # Voz: prefere as mais leves sempre; XTTS só se tiver GPU com VRAM suficiente
    if tem_gpu and vram >= 4000:
        voz = "xtts"
        motivo_voz = "GPU com VRAM suficiente para voz natural local"
    elif tem_gpu:
        voz = "kokoro"
        motivo_voz = "GPU com pouca VRAM; Kokoro usa menos memória"
    else:
        voz = "kokoro"
        motivo_voz = "Sem GPU dedicada; Kokoro roda leve em CPU"

    # Cérebro: verifica se LM Studio está acessível e se há modelos pequenos
    lm_studio = next((i for i in resultado.itens if i.id == "lmstudio"), None)
    lm_acessivel = lm_studio is not None and "servidor acessível" in (lm_studio.detalhe or "")

    if lm_acessivel:
        cerebro = "lmstudio"
        motivo_cerebro = "LM Studio acessível; modelo local sem dependência de internet"
    else:
        cerebro = "openjarvis"
        motivo_cerebro = "OpenJarvis já configurado; evita baixar modelos agora"

    motivo = f"{motivo_voz}. {motivo_cerebro}."
    return RecomendacaoLeve(voz=voz, cerebro=cerebro, motivo=motivo)
