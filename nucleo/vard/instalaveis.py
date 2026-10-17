"""Catálogo e instalação explícita dos provedores; executor substituível nas provas."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from typing import Callable, Mapping, Sequence

from vard.primeiro_uso import deteccao


@dataclass(frozen=True)
class Instalavel:
    id: str
    nome: str
    descricao: str
    comando: tuple[str, ...]
    fonte: str
    tipo_provedor: str = ""
    url_base: str = ""
    tamanho_mb: int | None = None
    login_comando: tuple[str, ...] = ()


CATALOGO = (
    Instalavel("lmstudio", "LM Studio", "Servidor local de modelos. Os modelos são baixados separadamente.",
               ("winget", "install", "--id", "ElementLabs.LMStudio", "-e"), "https://lmstudio.ai/download", "lmstudio", "http://127.0.0.1:1234/v1"),
    Instalavel("ollama", "Ollama", "Servidor local de modelos. Os modelos são baixados separadamente.",
               ("winget", "install", "--id", "Ollama.Ollama", "-e"), "https://docs.ollama.com/windows", "ollama", "http://127.0.0.1:11434/v1"),
    Instalavel("claude", "Claude Code", "Agente de programação por terminal; exige conta ou provedor configurado.",
               ("winget", "install", "--id", "Anthropic.ClaudeCode", "-e"), "https://code.claude.com/docs/en/setup", "cli-claude", login_comando=("claude", "auth", "login")),
    Instalavel("codex", "Codex CLI", "Agente por terminal para tarefas delegadas; requer Node.js e npm.",
               ("npm", "install", "-g", "@openai/codex"), "https://developers.openai.com/codex/cli/", "cli-codex", login_comando=("codex", "login")),
    Instalavel("opencode", "OpenCode", "Agente por terminal para tarefas delegadas; requer Node.js e npm.",
               ("npm", "install", "-g", "opencode-ai"), "https://opencode.ai/docs/", "cli-opencode", login_comando=("opencode", "auth", "login")),
    Instalavel("gemini", "Gemini CLI", "CLI do Google; requer Node.js e npm. Configure a conexão nas instruções oficiais.",
               ("npm", "install", "-g", "@google/gemini-cli"), "https://geminicli.com/docs/get-started/installation/", login_comando=("gemini",)),
    Instalavel("agy", "Antigravity", "Instalação manual pelo fornecedor; o instalador oficial usa um script de shell.",
               (), "https://antigravity.google/docs/cli/install/", "cli-agy", login_comando=("agy",)),
    Instalavel("openjarvis", "OpenJarvis", "Usa o script do Vard e as pastas de instalacao.json; requer Git e uv.",
               ("powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", "scripts/windows/instalar-openjarvis.ps1"), "docs/fusao.md"),
)


def ambiente_limpo(original: Mapping[str, str] | None = None) -> dict[str, str]:
    """Remove contexto e credenciais do agente pai sem alterar seu ambiente."""
    return {k: v for k, v in (os.environ if original is None else original).items()
            if not k.upper().startswith(("CLAUDE", "ANTHROPIC", "ORCA_AGENT"))}


def limpar_ambiente_mcp() -> None:
    """Também protege MCPs iniciados por hospedeiros externos, como o OpenJarvis."""
    permitido = ambiente_limpo()
    for chave in tuple(os.environ):
        if chave not in permitido:
            os.environ.pop(chave, None)


def _comando_nativo(comando: Sequence[str]) -> list[str]:
    """npm.cmd não é executável nativo: chama seu npm-cli.js pelo Node, sem shell."""
    if comando[0] != "npm" or os.name != "nt":
        return list(comando)
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node and npm:
        for base in (Path(npm).parent, Path(node).parent):
            script = base / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if script.is_file():
                return [node, str(script), *comando[1:]]
    raise OSError("Node.js e npm precisam estar instalados.")


def _encerrar(processo, filhos: dict) -> None:
    """Encerra apenas os processos próprios, conferindo PID e instante de criação."""
    import psutil
    try:
        raiz = psutil.Process(processo.pid)
        if raiz.pid in filhos and filhos[raiz.pid] == raiz.create_time():
            for filho in raiz.children(recursive=True):
                filhos.setdefault(filho.pid, filho.create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    for pid, inicio in reversed(list(filhos.items())):
        try:
            alvo = psutil.Process(pid)
            if alvo.create_time() == inicio:
                alvo.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def executar_real(comando: Sequence[str], emitir: Callable[[str], None], cancelar: threading.Event) -> int:
    """Saída por linhas, sem shell/entrada interativa e sem dados brutos no progresso."""
    import psutil
    processo = subprocess.Popen(
        _comando_nativo(comando), shell=False, env=ambiente_limpo(),
        cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    filhos: dict[int, float] = {}
    try:
        raiz = psutil.Process(processo.pid)
        filhos[raiz.pid] = raiz.create_time()
    except psutil.NoSuchProcess:
        pass

    def ler():
        assert processo.stdout is not None
        etapa = 0
        while linha := processo.stdout.readline(4096):
            if not linha.strip():
                continue
            etapa += 1
            percentual = re.search(r"\b(\d{1,3})\s*%", linha)
            detalhe = f" ({min(100, int(percentual[1]))}%)" if percentual else ""
            # Instaladores podem imprimir nome de usuário, diretórios e tokens.
            emitir(f"Instalador: etapa {etapa}{detalhe}.")

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    try:
        while processo.poll() is None:
            try:
                for filho in psutil.Process(processo.pid).children(recursive=True):
                    filhos.setdefault(filho.pid, filho.create_time())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            if cancelar.wait(0.1):
                _encerrar(processo, filhos)
                break
        return processo.wait(timeout=5)
    finally:
        if cancelar.is_set() or processo.poll() is None:
            _encerrar(processo, filhos)
        leitor.join(timeout=2)
        if processo.stdout and not leitor.is_alive():
            processo.stdout.close()


def detectar_instalados() -> dict[str, bool]:
    return deteccao.detectar_instalaveis()


def verificar_login(ident: str) -> str:
    """Só sondas de status; nunca abre navegador, prompt nem lê o conteúdo de tokens."""
    comandos = {"claude": ["claude", "auth", "status"], "codex": ["codex", "login", "status"],
                "opencode": ["opencode", "auth", "list"]}
    if ident not in comandos:
        return "nao_verificado"
    try:
        comando = list(comandos[ident])
        comando[0] = deteccao.localizar_instalaveis().get(ident, comando[0])
        r = subprocess.run(comando, shell=False, env=ambiente_limpo(),
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=3,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if ident == "claude":
            dados = json.loads(r.stdout)
            if isinstance(dados, dict) and isinstance(dados.get("loggedIn"), bool):
                return "conectado" if dados["loggedIn"] else "ausente"
            return "nao_verificado"
        texto = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout + r.stderr)).lower()
        if "not logged in" in texto or "0 credentials" in texto or "no credentials" in texto:
            return "ausente"
        if ident == "codex" and r.returncode == 0:
            return "conectado"
        if ident == "opencode" and re.search(r"[1-9]\d* credentials?", texto):
            return "conectado"
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return "nao_verificado"


def abrir_terminal_real(comando: Sequence[str]) -> None:
    """Janela visível somente em resposta à ação explícita Entrar na conta."""
    comando = list(comando)
    comando[0] = deteccao.localizar_instalaveis().get(comando[0], comando[0])
    trecho = "& " + " ".join("'" + parte.replace("'", "''") + "'" for parte in comando)
    subprocess.Popen(["powershell", "-NoProfile", "-NoExit", "-Command", trecho],
                     shell=False, env=ambiente_limpo(), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


class GerenciadorInstalaveis:
    def __init__(self, *, executor=executar_real, detectar=detectar_instalados,
                 autenticar=verificar_login, abrir_terminal=abrir_terminal_real):
        self.executor = executor
        self.detectar = detectar
        self.autenticar = autenticar
        self.abrir_terminal = abrir_terminal
        self._trava = threading.RLock()
        self._estados: dict[str, dict] = {}
        self._cancelamento = threading.Event()
        self._tarefa: threading.Thread | None = None

    def _item(self, ident: str) -> Instalavel:
        for item in CATALOGO:
            if item.id == ident:
                return item
        raise KeyError("Instalável não encontrado.")

    def _manual(self, item: Instalavel) -> bool:
        return not item.comando or (item.id == "openjarvis" and not
            (Path(__file__).resolve().parents[2] / item.comando[-1]).is_file())

    def listar(self) -> list[dict]:
        detectados = self.detectar()
        lista = []
        for item in CATALOGO:
            instalado = bool(detectados.get(item.id))
            lista.append({**asdict(item), "comando": list(item.comando),
                          "manual": self._manual(item), "instalado": instalado,
                          "login": self.autenticar(item.id) if instalado and item.login_comando else "dispensado",
                          **self.andamento(item.id)})
        return lista

    def andamento(self, ident: str) -> dict:
        self._item(ident)
        with self._trava:
            atual = self._estados.get(ident, {"id": ident, "estado": "aguardando", "linhas": []})
            return {**atual, "linhas": list(atual["linhas"])}

    def instalar(self, ident: str, *, confirmado: bool = False) -> dict:
        item = self._item(ident)
        if confirmado is not True:
            raise ValueError("É necessária a confirmação da instalação.")
        if self._manual(item):
            raise ValueError("Instalação manual: consulte as instruções oficiais.")
        with self._trava:
            if self._tarefa and self._tarefa.is_alive():
                raise RuntimeError("Já há uma instalação em andamento.")
            self._cancelamento = threading.Event()
            self._estados[ident] = {"id": ident, "estado": "aguardando", "linhas": []}
            self._tarefa = threading.Thread(target=self._executar, args=(item,), daemon=True)
            self._tarefa.start()
            return self.andamento(ident)

    def _executar(self, item: Instalavel):
        def emitir(linha):
            with self._trava:
                linhas = self._estados[item.id]["linhas"]
                linhas.append(str(linha)[:500])
                del linhas[:-100]
        with self._trava:
            self._estados[item.id]["estado"] = "instalando"
        try:
            rc = self.executor(item.comando, emitir, self._cancelamento)
            estado = "cancelado" if self._cancelamento.is_set() else ("concluido" if rc == 0 else "falhou")
            emitir({"cancelado": "Instalação cancelada; alterações já feitas podem permanecer.",
                    "concluido": "Instalação concluída.", "falhou": "A instalação não foi concluída. Confira os requisitos e tente novamente."}[estado])
        except Exception:  # saída técnica pode conter dados locais ou credenciais
            estado = "cancelado" if self._cancelamento.is_set() else "falhou"
            emitir("Não foi possível executar a instalação. Confira os requisitos e tente novamente.")
        with self._trava:
            self._estados[item.id]["estado"] = estado

    def cancelar(self, ident: str) -> dict:
        with self._trava:
            if self.andamento(ident)["estado"] in ("aguardando", "instalando") and ident in self._estados:
                self._cancelamento.set()
            return self.andamento(ident)

    def login(self, ident: str) -> dict:
        item = self._item(ident)
        if not item.login_comando or not self.detectar().get(ident):
            raise ValueError("Instale a CLI antes de entrar na conta.")
        self.abrir_terminal(list(item.login_comando))
        return {"ok": True}

    def encerrar(self):
        self._cancelamento.set()
        if self._tarefa:
            self._tarefa.join(timeout=10)
