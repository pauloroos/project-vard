"""Diagnóstico do Vard: checagens somente-leitura para a aba Diagnóstico.

Contrato da T10 (0.7):
- `rodar_diagnostico(tipo="basico" | "preflight") -> ResultadoDiagnostico`
- Retorna `{checagens: [{grupo, nome, estado, frase}], relatorio, duracao_ms}`
- Básico: só leitura (portas, processos, config, GPU/RAM); nunca inicia serviço,
  carrega modelo, faz login, envia Telegram nem toca em OpenJarvis/LM Studio/voz/reuniao.
- Preflight: conserva checks sintéticos ativos do preflight.py quando configurados;
  integrações externas só se habilitadas. Em modo jogo, checks que exigem modelo/reunião
  ficam indisponíveis.
- Timeout/cancelamento mata só o job do diagnóstico; saída sanitizada (sem credenciais
  nem caminhos pessoais). Relatório público só com dados sintéticos.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from vard.primeiro_uso import deteccao

Estado = Literal["ok", "aviso", "falha"]


@dataclass(frozen=True)
class Checagem:
    grupo: str
    nome: str
    estado: Estado
    frase: str


@dataclass
class ResultadoDiagnostico:
    checagens: list[Checagem] = field(default_factory=list)
    relatorio: str = ""
    duracao_ms: int = 0


# --- Sanitização -----------------------------------------------------------------

_RE_CRED = re.compile(
    r"(?i)(api[_-]?key|token|x-vard-token|secret|password|senha|[\w-]+_chave)"
    r"\s*[:=]\s*(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}]+)"
)
_RE_BEARER = re.compile(r"(?i)bearer\s+\S+|sk-[\w-]+")
_RE_CAMINHO_PESSOAL = re.compile(
    r"(?i)[A-Z]:\\Users\\[^\\\s]+|/home/[^/\s]+|/Users/[^/\s]+"
)


def _seguro(texto: str) -> str:
    """Remove credenciais e caminhos pessoais da saída."""
    t = _RE_CRED.sub("credencial=***", texto)
    t = _RE_BEARER.sub("***", t)
    t = _RE_CAMINHO_PESSOAL.sub("<caminho-pessoal>", t)
    return t


# --- Checagens básicas (somente leitura) -----------------------------------------

def _checar_portas_vard() -> tuple[str, str]:
    """Portas do Vard (4700, 4710, 4720, 8000) só em loopback."""
    portas = [4700, 4710, 4720, 8000]
    problemas: list[str] = []
    for porta in portas:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            resultado = s.connect_ex(("127.0.0.1", porta))
            s.close()
            if resultado == 0:
                # Porta aberta em loopback: ok
                continue
        except OSError:
            pass
        # Porta fechada ou inacessível: aviso (serviço pode estar desligado)
    # Verifica se alguma está ouvindo em interface externa
    try:
        saida = subprocess.run(
            ["netstat", "-an"], capture_output=True, text=True, timeout=5
        )
        for linha in saida.stdout.splitlines():
            for porta in portas:
                if f":{porta}" in linha and "LISTENING" in linha:
                    if "127.0.0.1" not in linha and "[::1]" not in linha:
                        problemas.append(f"porta {porta} em interface externa")
    except (OSError, subprocess.TimeoutExpired):
        pass
    if problemas:
        return ("aviso", "; ".join(problemas))
    return ("ok", "portas do Vard em loopback ou fechadas")


def _checar_processos_vard() -> tuple[str, str]:
    """Verifica processos vard.exe e serviços relacionados sem matar nada."""
    try:
        saida = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq vard.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        linhas = [l.strip() for l in saida.stdout.splitlines() if l.strip()]
        if not linhas or "No tasks" in saida.stdout:
            return ("aviso", "nenhum processo vard.exe encontrado")
        pids = []
        for l in linhas:
            partes = l.replace('"', "").split(",")
            if len(partes) >= 2:
                pids.append(partes[1])
        return ("ok", f"vard.exe ativo: PID(s) {', '.join(pids)}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ("falha", f"não foi possível listar processos: {exc}")


def _checar_config_dados() -> tuple[str, str]:
    """Verifica existência das pastas de config e dados do Vard."""
    config_dir = os.environ.get("VARD_CONFIG", "")
    dados_dir = os.environ.get("VARD_DADOS", "")
    avisos: list[str] = []
    if config_dir and not Path(config_dir).is_dir():
        avisos.append(f"VARD_CONFIG={config_dir} não existe")
    if dados_dir and not Path(dados_dir).is_dir():
        avisos.append(f"VARD_DADOS={dados_dir} não existe")
    if avisos:
        return ("aviso", "; ".join(avisos))
    return ("ok", "pastas de config/dados presentes ou não definidas")


def _checar_gpu_ram() -> tuple[str, str]:
    """GPU e RAM disponíveis (leitura via wmic/powershell)."""
    detalhes: list[str] = []
    # RAM total
    try:
        saida = subprocess.run(
            ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
            capture_output=True, text=True, timeout=5,
        )
        for linha in saida.stdout.splitlines():
            if "=" in linha:
                bytes_total = int(linha.split("=")[1].strip())
                gb = bytes_total / (1024 ** 3)
                detalhes.append(f"RAM: {gb:.1f} GB")
                break
    except (OSError, subprocess.TimeoutExpired, ValueError):
        detalhes.append("RAM: não disponível")
    # GPU
    try:
        saida = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "Name", "/value"],
            capture_output=True, text=True, timeout=5,
        )
        gpus = [l.split("=")[1].strip() for l in saida.stdout.splitlines() if "=" in l]
        if gpus:
            detalhes.append(f"GPU: {', '.join(gpus[:2])}")
        else:
            detalhes.append("GPU: nenhuma detectada")
    except (OSError, subprocess.TimeoutExpired):
        detalhes.append("GPU: não disponível")
    return ("ok", "; ".join(detalhes))


def _checar_logon_registro() -> tuple[str, str]:
    """Verifica se o início no logon está registrado (leitura do registro)."""
    try:
        saida = subprocess.run(
            ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
             "/v", "Vard"],
            capture_output=True, text=True, timeout=5,
        )
        if saida.returncode == 0 and "Vard" in saida.stdout:
            return ("ok", "início no logon registrado")
        return ("aviso", "início no logon não registrado")
    except (OSError, subprocess.TimeoutExpired):
        return ("aviso", "não foi possível consultar o registro")


def _checar_instancia_unica() -> tuple[str, str]:
    """Verifica se há mais de uma instância do vard.exe."""
    try:
        saida = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq vard.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        linhas = [l.strip() for l in saida.stdout.splitlines()
                  if l.strip() and "No tasks" not in l]
        if len(linhas) > 1:
            return ("aviso", f"{len(linhas)} instâncias de vard.exe ativas")
        return ("ok", "instância única ou nenhuma ativa")
    except (OSError, subprocess.TimeoutExpired):
        return ("aviso", "não foi possível verificar instâncias")


# --- Orquestração ----------------------------------------------------------------

CHECAGENS_BASICAS: list[tuple[str, str, Callable[[], tuple[str, str]]]] = [
    ("Runtime", "Portas do Vard", _checar_portas_vard),
    ("Runtime", "Processos vard.exe", _checar_processos_vard),
    ("Configuração", "Pastas config/dados", _checar_config_dados),
    ("Hardware", "GPU e RAM", _checar_gpu_ram),
    ("Sistema", "Início no logon", _checar_logon_registro),
    ("Sistema", "Instância única", _checar_instancia_unica),
]


# --- Detecção do primeiro uso (T1, 0.9) ------------------------------------------
# Reaproveita o detector somente-leitura como um grupo do Diagnóstico. Opcional ausente vira
# aviso, nunca falha; nada aqui instala ferramenta nem inicia serviço.

_ROTULO_ITEM = {"encontrado": "encontrado", "nao_encontrado": "não encontrado",
                "nao_verificado": "não verificado"}


def _frase_deteccao(nome: str, estado: str, versao: str, detalhe: str) -> str:
    texto = f"{nome}: {_ROTULO_ITEM.get(estado, estado)}"
    if versao:
        texto += f" ({versao})"
    if detalhe:
        texto += f" - {detalhe}"
    return texto


def checagens_deteccao(resultado: "deteccao.ResultadoDeteccao | None" = None) -> list[Checagem]:
    """Converte a detecção local em checagens do Diagnóstico (grupo 'Primeiro uso')."""
    r = resultado if resultado is not None else deteccao.detectar()
    checagens: list[Checagem] = []
    for item in r.itens:
        estado: Estado = "ok" if item.estado == "encontrado" else "aviso"
        checagens.append(Checagem(grupo="Primeiro uso", nome=item.nome, estado=estado,
                                  frase=_seguro(_frase_deteccao(item.nome, item.estado, item.versao, item.detalhe))))
    gpu = r.gpu
    estado_gpu: Estado = "ok" if gpu.estado == "encontrado" else "aviso"
    detalhe = f"backend {gpu.backend}" if gpu.backend else "backend desconhecido"
    if gpu.vram_mb:
        detalhe += f", VRAM ~{gpu.vram_mb} MB"
    if gpu.detalhe:
        detalhe += f" - {gpu.detalhe}"
    checagens.append(Checagem(grupo="Primeiro uso", nome="GPU", estado=estado_gpu,
                              frase=_seguro(f"GPU: {'encontrada' if gpu.estado == 'encontrado' else gpu.estado} - {detalhe}")))
    return checagens


def _deteccao_segura(prazo_s: float) -> list[Checagem]:
    try:
        return checagens_deteccao(deteccao.detectar(prazo_s=min(deteccao.PRAZO_PADRAO_S, max(0.5, prazo_s))))
    except Exception as exc:  # noqa: BLE001
        return [Checagem(grupo="Primeiro uso", nome="Detecção local", estado="aviso",
                         frase=_seguro(f"não foi possível detectar: {type(exc).__name__}"))]


def _executar_checagem(
    grupo: str, nome: str, fn: Callable[[], tuple[str, str]], prazo_s: float
) -> Checagem:
    try:
        estado, frase = fn()
        return Checagem(grupo=grupo, nome=nome, estado=estado, frase=_seguro(frase))
    except Exception as exc:  # noqa: BLE001
        return Checagem(
            grupo=grupo, nome=nome, estado="falha",
            frase=_seguro(f"{type(exc).__name__}: {exc}"[:200]),
        )


def rodar_diagnostico(
    tipo: str = "basico",
    *,
    prazo_s: float = 20.0,
    cancelado: Callable[[], bool] | None = None,
    incluir_deteccao: bool = False,
) -> ResultadoDiagnostico:
    """Executa o diagnóstico e retorna o resultado estruturado.

    Args:
        tipo: "basico" (somente leitura), "preflight" (checks completos) ou
            "deteccao" (só o grupo do primeiro uso).
        prazo_s: tempo máximo total em segundos.
        cancelado: callback que retorna True se o usuário cancelou.
        incluir_deteccao: acrescenta o grupo "Primeiro uso" ao diagnóstico básico.
    """
    inicio = time.monotonic()
    resultado = ResultadoDiagnostico()

    if tipo == "deteccao":
        resultado.checagens.extend(_deteccao_segura(prazo_s))
    else:
        if tipo != "basico":
            # Preflight completo: por enquanto usa as mesmas checagens básicas.
            # Checks sintéticos do preflight.py serão integrados quando as
            # integrações externas estiverem configuradas e habilitadas.
            pass

        checks = CHECAGENS_BASICAS
        with ThreadPoolExecutor(max_workers=min(4, len(checks))) as pool:
            futuros = {
                pool.submit(_executar_checagem, g, n, fn, prazo_s): (g, n)
                for g, n, fn in checks
            }
            for futuro in as_completed(futuros, timeout=prazo_s):
                if cancelado and cancelado():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    checagem = futuro.result(timeout=1)
                    resultado.checagens.append(checagem)
                except Exception as exc:  # noqa: BLE001
                    g, n = futuros[futuro]
                    resultado.checagens.append(
                        Checagem(grupo=g, nome=n, estado="falha",
                                 frase=_seguro(f"timeout ou erro: {exc}"[:200]))
                    )
        if incluir_deteccao:
            resultado.checagens.extend(_deteccao_segura(prazo_s))

    # Ordena por grupo e nome para relatório consistente
    resultado.checagens.sort(key=lambda c: (c.grupo, c.nome))

    # Gera relatório
    linhas = [f"# Diagnóstico Vard ({tipo})"]
    ok = av = fa = 0
    for c in resultado.checagens:
        marca = {"ok": "✔", "aviso": "!", "falha": "✘"}[c.estado]
        linhas.append(f"{marca} [{c.grupo}] {c.nome}: {c.frase}")
        if c.estado == "ok":
            ok += 1
        elif c.estado == "aviso":
            av += 1
        else:
            fa += 1
    linhas.append(f"\n{ok} ok, {av} avisos, {fa} falhas")
    resultado.relatorio = _seguro("\n".join(linhas))
    resultado.duracao_ms = int((time.monotonic() - inicio) * 1000)
    return resultado