"""Supervisor de processos vivos de CLI (T16 da 0.8).

Contratos (plano 0.8 T16 / spec C3-C7/C12-C13):
- Um processo vivo por sessão (`cli-claude` ou `cli-agy`) em stream-json.
- Pasta própria `VARD_DADOS/cli/<provedor_id>/<sessao_id>/` com CLAUDE.md/AGENTS.md/perfil.md/mcp.json.
- Perfil montado vai por arquivo (--append-system-prompt-file no claude); nunca inline.
- yolo liga `--dangerously-skip-permissions`.
- enxuto (T17b/C5): ao abrir com enxuto=True o supervisor lê o evento de início,
  confere `Dialeto.ferramentas_iniciais` contra as ferramentas do cérebro local
  (`cli_capacidade.verificar_enxuto`) e, se faltar alguma, reabre a sessão SEM
  enxuto registrando o aviso que o /status mostra.
- Ocioso 600 s fecha o processo; próxima pergunta reabre.
- Nova conversa reinicia o processo.
- Jogo/saída encerram a árvore inteira por PID (taskkill /T /F /PID).
- Reserva só antes de texto entregue; após texto, termina com erro sem repetir.
- CLI não usa trava/slot do motor local.
- Sessões voz/telegram/painel não compartilham processo (cada sessão tem seu próprio).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from vard import config as modulo_config
from vard import perfil as modulo_perfil
from .cli import AdaptadorCli, CanalCli, DIALETOS
from .cli_capacidade import registrar_aviso, verificar_enxuto
from .provedores import ErroProvedor

log = logging.getLogger(__name__)

OCIOSO_SEGUNDOS = 600.0
# Prazo do primeiro evento útil da CLI (restrições globais do plano 0.8).
PRAZO_FERRAMENTAS_INICIAIS = 15.0


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
        self._inicio: Optional[str] = None

    def guardar_inicio(self, linha: str) -> None:
        """A conferência do enxuto leu o evento de início; o próximo leitor o vê de novo (T17b)."""
        self._inicio = linha

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
        if self._inicio is not None:
            linha, self._inicio = self._inicio, None
            yield linha
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


async def _ferramentas_iniciais(
    canal: CanalCli,
    dialeto: str,
    prazo: float = PRAZO_FERRAMENTAS_INICIAIS,
) -> Optional[List[str]]:
    """Lê o evento de início da sessão e devolve as ferramentas que a CLI informa (C5).

    None quando a CLI não informa a lista dentro do prazo ou o stream fecha:
    nesse caso o enxuto não é confirmado. As linhas lidas aqui são só o início
    do stream (antes de qualquer mensagem do usuário) e a linha do evento de
    início fica guardada no canal, para o adaptador vê-la normalmente.
    """
    dia = DIALETOS[dialeto]
    linhas = canal.linhas()
    if inspect.isawaitable(linhas):
        linhas = await linhas
    aiter = linhas.__aiter__()
    fim = time.monotonic() + prazo
    while True:
        restante = fim - time.monotonic()
        if restante <= 0:
            return None
        try:
            linha = await asyncio.wait_for(aiter.__anext__(), timeout=restante)
        except (asyncio.TimeoutError, StopAsyncIteration):
            return None
        ferramentas = dia.ferramentas_iniciais(linha)
        if ferramentas is not None:
            guardar = getattr(canal, "guardar_inicio", None)
            if callable(guardar):
                guardar(linha)
            return ferramentas


# Tamanho máximo de uma linha stream-json lida da CLI (D6).
_LIMITE_LINHA = 16 * 1024 * 1024


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

    def __init__(
        self,
        *,
        base_dados: Optional[Path] = None,
        ocioso_segundos: float = OCIOSO_SEGUNDOS,
        ferramentas_locais: Any = None,
    ) -> None:
        self._base_dados = base_dados
        self._ocioso = float(ocioso_segundos)
        # Fonte das ferramentas do cérebro local para o enxuto (C5):
        # lista, chamada síncrona ou assíncrona; None = nenhuma registrada.
        self._fonte_ferramentas_locais = ferramentas_locais
        self._processos: Dict[str, asyncio.subprocess.Process] = {}
        # Um canal (e um leitor do stdout) por processo: dois leitores no mesmo stdout derrubam o turno (D7).
        self._canais: Dict[str, "_CanalProcesso"] = {}
        self._ultimo_uso: Dict[str, float] = {}
        self._enxuto: Dict[str, bool] = {}
        self._trava = asyncio.Lock()
        self._limpeza_task: Optional[asyncio.Task] = None

    async def canal(self, provedor: ProvedorCli, sessao_id: str) -> CanalCli:
        """Retorna um canal para a sessão, abrindo/reabrindo o processo se necessário."""
        chave = f"{provedor.id}:{sessao_id}"
        async with self._trava:
            proc = self._processos.get(chave)
            if proc is not None and proc.returncode is None:
                self._ultimo_uso[chave] = time.monotonic()
                return self._canal_do_processo(chave, proc)
            if provedor.enxuto:
                return await self._abrir_enxuto(provedor, sessao_id, chave)
            self._enxuto[chave] = False
            return await self._abrir(provedor, sessao_id, chave)

    async def _abrir(self, provedor: ProvedorCli, sessao_id: str, chave: str) -> CanalCli:
        """Abre processo novo para a chave e devolve o canal (T16)."""
        pasta = _preparar_pasta_sessao(provedor, sessao_id, base_dados=self._base_dados)
        cmd = argv_cli(provedor, pasta)
        try:
            kwargs: Dict[str, Any] = {
                "stdin": asyncio.subprocess.PIPE,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
                "cwd": str(pasta),
                # A CLI claude real manda linhas de dezenas de KB (lista de comandos/skills); o padrão
                # do asyncio (64 KB) faria o readline falhar e o canal virar cli_caiu.
                "limit": _LIMITE_LINHA,
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
        return self._canal_do_processo(chave, proc)

    def _canal_do_processo(self, chave: str, proc: asyncio.subprocess.Process) -> "_CanalProcesso":
        """Devolve o canal já ligado a este processo, ou cria um se o processo é novo."""
        canal = self._canais.get(chave)
        if canal is None or canal._proc is not proc:
            canal = _CanalProcesso(proc)
            self._canais[chave] = canal
        return canal

    async def _abrir_enxuto(self, provedor: ProvedorCli, sessao_id: str, chave: str) -> CanalCli:
        """T17b/C5: confere as ferramentas iniciais; se faltar, reabre sem enxuto e avisa."""
        locais = await self._ferramentas_locais()
        canal = await self._abrir(provedor, sessao_id, chave)
        ferramentas_cli = await _ferramentas_iniciais(canal, _dialeto_do_tipo(provedor.tipo))
        if ferramentas_cli is None:
            await self._fechar_chave(chave)
            self._enxuto[chave] = False
            registrar_aviso(f"enxuto recusado em {provedor.id}: a CLI nao informou as ferramentas iniciais")
            return await self._abrir(replace(provedor, enxuto=False), sessao_id, chave)

        ok, faltando = verificar_enxuto(ferramentas_cli, locais)
        if ok:
            self._enxuto[chave] = True
            return canal

        await self._fechar_chave(chave)
        self._enxuto[chave] = False
        registrar_aviso(f"enxuto recusado em {provedor.id}: falta {', '.join(faltando)}")
        return await self._abrir(replace(provedor, enxuto=False), sessao_id, chave)

    async def _ferramentas_locais(self) -> List[str]:
        """Ferramentas do cérebro local usadas na conferência do enxuto (C5)."""
        fonte = self._fonte_ferramentas_locais
        if fonte is None:
            return []
        if isinstance(fonte, (list, tuple)):
            return [str(nome) for nome in fonte]
        valor = fonte()
        if inspect.isawaitable(valor):
            valor = await valor
        return [str(nome) for nome in (valor or [])]

    async def _fechar_chave(self, chave: str) -> None:
        """Encerra o processo da chave por PID e esquece o registro."""
        proc = self._processos.pop(chave, None)
        self._ultimo_uso.pop(chave, None)
        if proc is not None and proc.returncode is None:
            pid = proc.pid
            await asyncio.get_running_loop().run_in_executor(None, _encerrar_arvore, pid)

    def enxuto(self, provedor_id: str, sessao_id: str) -> bool:
        """Se a sessão viva está rodando com enxuto confirmado (T17b)."""
        chave = f"{provedor_id}:{sessao_id}"
        proc = self._processos.get(chave)
        if proc is None or proc.returncode is not None:
            return False
        return bool(self._enxuto.get(chave, False))

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
            self._enxuto.clear()

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