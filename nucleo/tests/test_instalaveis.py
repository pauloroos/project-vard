"""Instalação simulada: nenhum comando de instalação/login toca no computador."""
import threading
import time
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from vard import instalaveis


def aguardar(gerente, ident, estado):
    limite = time.monotonic() + 2
    while time.monotonic() < limite:
        atual = gerente.andamento(ident)
        if atual["estado"] == estado:
            return atual
        time.sleep(0.005)
    pytest.fail(f"Não chegou a {estado}: {atual}")


class ExecutorFalso:
    def __init__(self, codigo=0, bloquear=False):
        self.codigo = codigo
        self.bloquear = bloquear
        self.entrou = threading.Event()
        self.comandos = []

    def __call__(self, comando, emitir, cancelar):
        self.comandos.append(list(comando))
        self.entrou.set()
        emitir("Baixando pacote")
        if self.bloquear:
            assert cancelar.wait(2), "Teste não cancelou a instalação"
        return self.codigo


def gerente(executor=None, detectados=None):
    return instalaveis.GerenciadorInstalaveis(
        executor=executor or ExecutorFalso(),
        detectar=lambda: detectados or {},
        autenticar=lambda ident: "ausente",
    )


def test_catalogo_expoe_comandos_sem_aceitar_comando_do_cliente():
    itens = {i["id"]: i for i in gerente().listar()}
    assert set(itens) == {"lmstudio", "ollama", "claude", "codex", "opencode", "gemini", "agy", "openjarvis"}
    assert itens["lmstudio"]["comando"] == ["winget", "install", "--id", "ElementLabs.LMStudio", "-e"]
    assert itens["codex"]["comando"] == ["npm", "install", "-g", "@openai/codex"]
    assert itens["gemini"]["comando"] == ["npm", "install", "-g", "@google/gemini-cli"]
    assert itens["agy"]["manual"] is True
    assert itens["agy"]["fonte"].startswith("https://antigravity.google/")
    assert all(i["descricao"] and i["fonte"] for i in itens.values())
    assert all(i["estado"] == "aguardando" for i in itens.values())


def test_conclusao_progresso_e_confirmacao():
    falso = ExecutorFalso()
    g = gerente(falso)
    with pytest.raises(ValueError, match="confirmação"):
        g.instalar("codex")
    assert falso.comandos == []
    g.instalar("codex", confirmado=True)
    atual = aguardar(g, "codex", "concluido")
    assert atual["linhas"] == ["Baixando pacote", "Instalação concluída."]
    assert falso.comandos == [["npm", "install", "-g", "@openai/codex"]]


def test_apenas_uma_instalacao_e_cancelamento_antes_de_liberar():
    falso = ExecutorFalso(bloquear=True)
    g = gerente(falso)
    g.instalar("ollama", confirmado=True)
    assert falso.entrou.wait(1)
    assert g.andamento("ollama")["estado"] == "instalando"
    with pytest.raises(RuntimeError, match="andamento"):
        g.instalar("claude", confirmado=True)
    g.cancelar("ollama")
    aguardar(g, "ollama", "cancelado")
    assert g.cancelar("codex")["estado"] == "aguardando"


@pytest.mark.parametrize("codigo", [1, 42])
def test_codigo_nao_zero_falha(codigo):
    g = gerente(ExecutorFalso(codigo=codigo))
    g.instalar("claude", confirmado=True)
    assert "não foi concluída" in aguardar(g, "claude", "falhou")["linhas"][-1]


def test_erro_do_executor_nao_vaza_detalhe():
    def falhar(*args):
        raise OSError("dado que não deve sair")
    g = gerente(falhar)
    g.instalar("claude", confirmado=True)
    assert "dado que" not in str(aguardar(g, "claude", "falhou"))


def test_manual_e_id_invalido_nao_executam():
    g = gerente()
    with pytest.raises(ValueError, match="manual"):
        g.instalar("agy", confirmado=True)
    with pytest.raises(KeyError):
        g.andamento("arbitrario")


def test_ambiente_limpo_sem_alterar_original():
    original = {"PATH": "bin", "CLAUDECODE": "1", "claude_config": "x", "ANTHROPIC_API_KEY": "x", "ORCA_AGENT_TOKEN": "x", "VARD_CONFIG": "config"}
    assert instalaveis.ambiente_limpo(original) == {"PATH": "bin", "VARD_CONFIG": "config"}
    assert "CLAUDECODE" in original


def test_executor_real_sem_shell_e_sem_ambiente_do_agente(monkeypatch):
    chamadas = []
    def criar(comando, **opcoes):
        chamadas.append((comando, opcoes))
        return SimpleNamespace(pid=81, stdout=io.StringIO("Baixando 25% em diretório local\n"),
                               poll=lambda: 0, wait=lambda **kw: 0)
    monkeypatch.setattr(instalaveis.subprocess, "Popen", criar)
    monkeypatch.setattr(instalaveis, "_comando_nativo", lambda args: list(args))
    import psutil
    monkeypatch.setattr(psutil, "Process", lambda pid: SimpleNamespace(pid=pid, create_time=lambda: 10))
    monkeypatch.setenv("CLAUDECODE", "contexto-ficticio")
    monkeypatch.setenv("ANTHROPIC_TESTE", "credencial-ficticia")
    monkeypatch.setenv("ORCA_AGENT_TESTE", "contexto-ficticio")
    linhas = []
    assert instalaveis.executar_real(["winget", "install", "pacote-falso"], linhas.append, threading.Event()) == 0
    comando, opcoes = chamadas[0]
    assert comando == ["winget", "install", "pacote-falso"]
    assert opcoes["shell"] is False
    assert not any(k.upper().startswith(("CLAUDE", "ANTHROPIC", "ORCA_AGENT")) for k in opcoes["env"])
    assert linhas == ["Instalador: etapa 1 (25%)."]


def test_npm_no_windows_usa_node_sem_cmd(monkeypatch, tmp_path):
    script = tmp_path / "node_modules" / "npm" / "bin" / "npm-cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("// dublê não executado", encoding="utf-8")
    monkeypatch.setattr(instalaveis.shutil, "which", lambda nome: str(tmp_path / (nome + (".cmd" if nome == "npm" else ".exe"))))
    comando = instalaveis._comando_nativo(["npm", "install", "-g", "@openai/codex"])
    assert comando == [str(tmp_path / "node.exe"), str(script), "install", "-g", "@openai/codex"]


def test_terminal_real_visivel_so_com_comando_fixo(monkeypatch):
    chamadas = []
    monkeypatch.setattr(instalaveis.deteccao, "localizar_instalaveis", lambda: {})
    monkeypatch.setattr(instalaveis.subprocess, "Popen", lambda args, **kw: chamadas.append((args, kw)))
    instalaveis.abrir_terminal_real(["claude", "auth", "login"])
    args, opcoes = chamadas[0]
    assert args == ["powershell", "-NoProfile", "-NoExit", "-Command", "& 'claude' 'auth' 'login'"]
    assert opcoes["shell"] is False
    assert opcoes["creationflags"] == instalaveis.subprocess.CREATE_NEW_CONSOLE


def test_cancelamento_nao_mata_pid_reutilizado(monkeypatch):
    import psutil
    mortos = []
    consultados = []
    def processo(pid):
        consultados.append(pid)
        return SimpleNamespace(pid=pid, create_time=lambda: 20,
            children=lambda **kw: [SimpleNamespace(pid=82, create_time=lambda: 20)],
            kill=lambda: mortos.append(pid))
    monkeypatch.setattr(psutil, "Process", processo)
    instalaveis._encerrar(SimpleNamespace(pid=81), {81: 10})
    assert mortos == []
    assert 82 not in consultados


def test_deteccao_pos_instalacao_sem_atualizar_path(tmp_path):
    from vard.primeiro_uso import deteccao
    raiz = tmp_path / "perfil"
    npm = raiz / "AppData" / "Roaming" / "npm"
    locais = {npm / "codex.cmd", npm / "gemini.cmd"}
    amb = deteccao.Ambiente(env={"APPDATA": str(raiz / "AppData" / "Roaming")},
        which=lambda nome: None, existe=lambda p: p in locais,
        rodar=lambda *args: pytest.fail("Não executar sonda"), http_json=lambda *args: None)
    resultado = deteccao.detectar_instalaveis(amb)
    assert resultado["codex"] and resultado["gemini"]


def test_openjarvis_detectado_na_instalacao_existente(tmp_path):
    import json
    from vard.primeiro_uso import deteccao
    origem = tmp_path / "openjarvis"
    arquivo = tmp_path / "instalacao.json"
    arquivo.write_text(json.dumps({"openjarvis_src": str(origem)}), encoding="utf-8")
    alvo = origem / ".venv" / "Scripts" / "jarvis.exe"
    amb = deteccao.Ambiente(env={"VARD_INSTALACAO": str(arquivo)}, which=lambda nome: None,
        existe=lambda p: p == alvo, rodar=lambda *args: pytest.fail("Não executar sonda"), http_json=lambda *args: None)
    assert deteccao.detectar_instalaveis(amb)["openjarvis"]


def test_login_resolve_cli_instalada_fora_do_path(monkeypatch, tmp_path):
    chamadas = []
    caminho = str(tmp_path / "cli-falsa.exe")
    monkeypatch.setattr(instalaveis.deteccao, "localizar_instalaveis", lambda: {"claude": caminho}, raising=False)
    monkeypatch.setattr(instalaveis.subprocess, "Popen", lambda args, **kw: chamadas.append(args))
    instalaveis.abrir_terminal_real(["claude", "auth", "login"])
    assert caminho in chamadas[0][-1]


@pytest.mark.parametrize(("ident", "codigo", "saida", "esperado"), [
    ("claude", 0, '{"loggedIn":true}', "conectado"),
    ("claude", 1, '{"loggedIn":false}', "ausente"),
    ("codex", 1, 'Not logged in', "ausente"),
    ("codex", 0, 'Logged in', "conectado"),
    ("opencode", 0, '0 credentials', "ausente"),
    ("opencode", 0, '2 credentials', "conectado"),
    ("claude", 0, 'saída inválida', "nao_verificado"),
])
def test_status_login_sem_interacao(monkeypatch, ident, codigo, saida, esperado):
    chamadas = []
    def rodar(args, **kw):
        chamadas.append((args, kw))
        return SimpleNamespace(returncode=codigo, stdout=saida, stderr="")
    monkeypatch.setattr(instalaveis.subprocess, "run", rodar)
    assert instalaveis.verificar_login(ident) == esperado
    assert chamadas[0][0][1:] in (["auth", "status"], ["login", "status"], ["auth", "list"])
    assert chamadas[0][1]["stdin"] == instalaveis.subprocess.DEVNULL


def test_deteccao_reutiliza_caminho_configurado_sem_sondas(tmp_path):
    from vard.primeiro_uso import deteccao
    config = tmp_path / "config"
    config.mkdir()
    executavel = tmp_path / "claude-falso.exe"
    (config / "delegada.toml").write_text('[agentes.claude]\nexe = "' + executavel.as_posix() + '"\n', encoding="utf-8")
    def proibido(*args):
        pytest.fail("Detecção de presença não pode executar programas")
    amb = deteccao.Ambiente(env={}, which=lambda nome: "bin/gemini.cmd" if nome == "gemini" else None,
        existe=lambda p: p == executavel or p == Path("bin/gemini.cmd"), rodar=proibido, http_json=proibido, config_dir=config)
    resultado = deteccao.detectar_instalaveis(amb)
    assert resultado["claude"] and resultado["gemini"]
    assert not resultado["ollama"] and not resultado["openjarvis"]


def test_detectado_sem_login_e_terminal_so_sob_pedido():
    abertos = []
    g = instalaveis.GerenciadorInstalaveis(
        executor=ExecutorFalso(), detectar=lambda: {"claude": True},
        autenticar=lambda ident: "ausente", abrir_terminal=lambda cmd: abertos.append(cmd),
    )
    claude = next(i for i in g.listar() if i["id"] == "claude")
    assert claude["instalado"] and claude["login"] == "ausente"
    assert abertos == []
    g.login("claude")
    assert abertos == [["claude", "auth", "login"]]
    with pytest.raises(ValueError):
        g.login("codex")


def test_rotas_iniciam_consultam_cancelam_e_recusam_sem_confirmacao(monkeypatch):
    import server
    g = gerente(ExecutorFalso(bloquear=True))
    monkeypatch.setattr(server, "_instalaveis", g)
    cliente = TestClient(server.app, base_url="http://127.0.0.1:4700")
    assert len(cliente.get("/instalaveis").json()["itens"]) == 8
    assert cliente.post("/instalaveis/codex/instalar", json={}).status_code == 400
    assert cliente.post("/instalaveis/codex/instalar", json={"confirmado": "sim"}).status_code == 400
    assert cliente.post("/instalaveis/codex/instalar", json={"confirmado": True}).status_code == 200
    assert cliente.post("/instalaveis/claude/instalar", json={"confirmado": True}).status_code == 409
    assert cliente.get("/instalaveis/codex/andamento").json()["estado"] == "instalando"
    assert cliente.post("/instalaveis/codex/cancelar").status_code == 200
    aguardar(g, "codex", "cancelado")
    assert cliente.get("/instalaveis/invalido/andamento").status_code == 404
    assert cliente.post("/instalaveis/agy/instalar", json={"confirmado": True}).status_code == 400
