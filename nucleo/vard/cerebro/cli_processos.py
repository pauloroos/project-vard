"""Supervisor de processos vivos de CLI (T16 da 0.8).

Contratos (plano 0.8 T16 / spec C3-C7/C12-C13):
- Um processo vivo por sessão (`cli-claude` ou `cli-agy`) em stream-json.
- Pasta própria `VARD_DADOS/cli/<provedor_id>/<sessao_id>/` com CLAUDE.md/AGENTS.md/perfil.md/mcp.json.
- Perfil montado vai por arquivo (--append-system-prompt-file no claude); nunca inline.
- yolo liga `--dangerously-skip-permissions`; enxuto não é tratado aqui (capacidade na T17).
- Ocioso 600 s fecha o processo; próxima pergunta reabre.
- Nova conversa reinicia o processo.
- Jogo/saída encerram a árvore inteira por PID (taskkill /T /F /PID).
- Reserva só antes de texto entregue; após texto, termina com erro sem repetir.
- CLI não usa trava/slot do motor local.
- Sessões voz/telegram/painel não compartilham processo (cada sessão tem seu próprio).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from vard import config as modulo_config
from vard import perfil as modulo_perfil
from .cli import AdaptadorCli, CanalCli, DIALETOS
from .provedores import ErroProvedor

log = logging.getLogger(__name__)

OCIOSO_SEGUNDOS = 600.0


@dataclass
class ProvedorCli:
    """Cadastro do painel para provedores cli-*."""
    id: str
    tipo: str  # 'cli-claude' | 'cli-agy'
    modelo: str = ""
    yolo: bool = True
    enxuto: bool = False
    esforco: Optional[str] = None


class _CanalProcesso(CanalCli):
    """Canal real ligado a um subprocesso em stream-json (asyncio nativo)."""

    def __init__(self, processo: asyncio.subprocess.Process) -> None:
        self._proc = processo
        self._fila: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._leitor_task = asyncio.create_task(self._ler_stdout())

    async def enviar(self, linha: str) -> None:
        if self._proc.returncode is not None:
            raise ErroProvedor("cli_caiu", True, "processo da CLI morreu antes do envio")
        assert self._proc.stdin is not None
        dados = (linha + "\n").encode("utf-8")
        try:
            self._proc.stdin.write(dados)
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            log.warning("CLI stdin falhou: %s", exc)

    async def _ler_stdout(self) -> None:
        assert self._proc.stdout is not None
        try:
            while True:
                linha_bytes = await self._proc.stdout.readline()
                if not linha_bytes:
                    break
                try:
                    texto = linha_bytes.decode("utf-8", errors="replace").rstrip("\n")
                except Exception:  # noqa: BLE001
                    texto = ""
                await self._fila.put(texto)
        except Exception as exc:  # noqa: BLE001
            log.debug("leitor stdout encerrou: %s", exc)
        finally:
            await self._fila.put(None)

    async def linhas(self) -> AsyncIterator[str]:
        while True:
            item = await self._fila.get()
            if item is None:
                return
            yield item

    async def interromper(self) -> None:
        pid = self._proc.pid
        if pid and self._proc.returncode is None:
            await asyncio.get_running_loop().run_in_executor(None, _encerrar_arvore, pid)


def _dialeto_do_tipo(tipo: str) -> str:
    if tipo == "cli-claude":
        return "claude"
    if tipo == "cli-agy":
        return "agy"
    raise ValueError(f"tipo de CLI desconhecido: {tipo!r}")


def argv_cli(provedor: ProvedorCli, pasta: Path) -> List[str]:
    """Monta o argv da CLI conforme docs/cli.md da T13 e spec C4/C6."""
    dialeto = _dialeto_do_tipo(provedor.tipo)
    perfil_md = pasta / "perfil.md"
    mcp_json = pasta / "mcp.json"

    if dialeto == "claude":
        cmd = [
            "claude",
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
        ]
        if provedor.modelo:
            cmd.extend(["--model", provedor.modelo])
        if perfil_md.exists():
            cmd.extend(["--append-system-prompt-file", str(perfil_md)])
        if mcp_json.exists():
            cmd.extend(["--mcp-config", str(mcp_json), "--strict-mcp-config"])
        if provedor.yolo:
            cmd.append("--dangerously-skip-permissions")
        if provedor.esforco:
            cmd.extend(["--effort", provedor.esforco])
        return cmd

    # agy
    cmd = ["agy", "--stream-json"]
    if provedor.modelo:
        cmd.extend(["--model", provedor.modelo])
    # agy lê AGENTS.md da pasta automaticamente quando cwd é a pasta
    return cmd


def _preparar_pasta_sessao(
    provedor: ProvedorCli,
    sessao_id: str,
    *,
    base_dados: Optional[Path] = None,
) -> Path:
    """Cria VARD_DADOS/cli/<provedor_id>/<sessao_id>/ com perfil e MCPs."""
    raiz = Path(base_dados) if base_dados else modulo_config.pasta_dados()
    pasta = raiz / "cli" / provedor.id / sessao_id
    pasta.mkdir(parents=True, exist_ok=True)

    # nome/usuario vêm da config.json; se não existir ou falhar, usa vazio
    nome = ""
    usuario = ""
    try:
        import json as _json
        cfg_arq = modulo_config.arquivo_config("config.json")
        if cfg_arq.exists():
            _cfg = _json.loads(cfg_arq.read_text(encoding="utf-8"))
            if isinstance(_cfg, dict):
                nome = str(_cfg.get("nome", "") or "")
                usuario = str(_cfg.get("usuario", "") or "")
    except Exception:  # noqa: BLE001
        pass

    p = modulo_perfil.ler()
    persona = modulo_perfil.montar_persona(p, nome, usuario)

    perfil_md = pasta / "perfil.md"
    perfil_md.write_text(persona, encoding="utf-8")

    # CLAUDE.md e AGENTS.md recebem o mesmo texto para compatibilidade
    (pasta / "CLAUDE.md").write_text(persona, encoding="utf-8")
    (pasta / "AGENTS.md").write_text(persona, encoding="utf-8")

    # mcp.json vazio por enquanto; T17/T18 preenchem com MCPs habilitados
    mcp_json = pasta / "mcp.json"
    if not mcp_json.exists():
        mcp_json.write_text(json.dumps({"mcpServers": {}}, ensure_ascii=False), encoding="utf-8")

    return pasta


def _encerrar_arvore(pid: int) -> None:
    """Encerra a árvore de processos por PID. Windows: taskkill /T /F /PID. POSIX: killpg."""
    if pid <= 0:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                os.kill(pid, signal.SIGTERM)
    except Exception as exc:  # noqa: BLE001
        log.debug("encerrar_arvore(%s) falhou: %s", pid, exc)


class SupervisorCli:
    """Gerencia processos vivos de CLI, um por sessão."""

    def __init__(self, *, base_dados: Optional[Path] = None, ocioso_segundos: float = OCIOSO_SEGUNDOS) -> None:
        self._base_dados = base_dados
        self._ocioso = float(ocioso_segundos)
        self._processos: Dict[str, asyncio.subprocess.Process] = {}
        self._ultimo_uso: Dict[str, float] = {}
        self._trava = asyncio.Lock()
        self._limpeza_task: Optional[asyncio.Task] = None

    async def canal(self, provedor: ProvedorCli, sessao_id: str) -> CanalCli:
        """Retorna um canal para a sessão, abrindo/reabrindo o processo se necessário."""
        chave = f"{provedor.id}:{sessao_id}"
        async with self._trava:
            proc = self._processos.get(chave)
            if proc is not None and proc.returncode is None:
                self._ultimo_uso[chave] = time.monotonic()
                return _CanalProcesso(proc)
            # Abre novo processo
            pasta = _preparar_pasta_sessao(provedor, sessao_id, base_dados=self._base_dados)
            cmd = argv_cli(provedor, pasta)
            try:
                kwargs: Dict[str, Any] = {
                    "stdin": asyncio.subprocess.PIPE,
                    "stdout": asyncio.subprocess.PIPE,
                    "stderr": asyncio.subprocess.PIPE,
                    "cwd": str(pasta),
                }
                if sys.platform != "win32":
                    kwargs["preexec_fn"] = os.setsid
                proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            except FileNotFoundError as exc:
                raise ErroProvedor("cli_ausente", True, "CLI nao encontrada no PATH") from exc
            except OSError as exc:
                raise ErroProvedor("cli_caiu", True, "nao foi possivel iniciar a CLI") from exc
            self._processos[chave] = proc
            self._ultimo_uso[chave] = time.monotonic()
            self._garantir_limpeza()
            return _CanalProcesso(proc)

    async def nova_conversa(self, sessao_id: str) -> None:
        """Reinicia todos os processos da sessão (nova conversa ou limite de trocas)."""
        async with self._trava:
            chaves = [c for c in self._processos if c.endswith(f":{sessao_id}")]
            for chave in chaves:
                proc = self._processos.pop(chave, None)
                self._ultimo_uso.pop(chave, None)
                if proc is not None and proc.returncode is None:
                    pid = proc.pid
                    await asyncio.get_running_loop().run_in_executor(None, _encerrar_arvore, pid)

    async def encerrar_tudo(self) -> None:
        """Encerra todos os processos de CLI (jogo/saída do app)."""
        async with self._trava:
            if self._limpeza_task is not None:
                self._limpeza_task.cancel()
                self._limpeza_task = None
            for chave, proc in list(self._processos.items()):
                if proc.returncode is None:
                    pid = proc.pid
                    await asyncio.get_running_loop().run_in_executor(None, _encerrar_arvore, pid)
            self._processos.clear()
            self._ultimo_uso.clear()

    def pids(self) -> List[int]:
        """Lista PIDs vivos (para prova e diagnóstico)."""
        resultado: List[int] = []
        for proc in self._processos.values():
            if proc.returncode is None:
                resultado.append(proc.pid)
        return resultado

    def _garantir_limpeza(self) -> None:
        if self._limpeza_task is None or self._limpeza_task.done():
            self._limpeza_task = asyncio.create_task(self._ciclo_ocioso())

    async def _ciclo_ocioso(self) -> None:
        """Fecha processos ociosos além do prazo."""
        try:
            while True:
                await asyncio.sleep(min(self._ocioso / 2, 60.0))
                agora = time.monotonic()
                async with self._trava:
                    vencidas = [
                        c for c, t in self._ultimo_uso.items()
                        if (agora - t) >= self._ocioso and c in self._processos
                    ]
                    for chave in vencidas:
                        proc = self._processos.pop(chave, None)
                        self._ultimo_uso.pop(chave, None)
                        if proc is not None and proc.returncode is None:
                            pid = proc.pid
                            await asyncio.get_running_loop().run_in_executor(None, _encerrar_arvore, pid)
                            log.info("CLI ociosa fechada: %s pid=%s", chave, pid)
        except asyncio.CancelledError:
            pass