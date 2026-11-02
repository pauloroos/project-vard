import dataclasses
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from vard import delegada
from vard.delegada import ErroDelegada

CONFIG_TESTE = Path(__file__).resolve().parent / "fixtures" / "config"
CONF = delegada.carregar(CONFIG_TESTE / "delegada.toml")
PERGUNTA = 'quais e-mails "urgentes" & 100% $(rm -rf x) ^ | chegaram?\nsegunda linha'

pytestmark = pytest.mark.usefixtures("config_usuario")   # pasta de configuração do usuário fictícia em todo teste


@pytest.fixture
def conf_exes(tmp_path):
    """Config com um .exe falso por agente (os testes nunca rodam CLI de verdade)."""
    agentes = {}
    for a, dados in CONF.agentes.items():
        exe = tmp_path / "bin" / f"{a}.exe"
        exe.parent.mkdir(exist_ok=True)
        exe.write_bytes(b"MZ")
        agentes[a] = {**dados, "exe": str(exe)}
    return dataclasses.replace(CONF, agentes=agentes)


def _trocar_args(conf, agente, args):
    return dataclasses.replace(conf, agentes={**conf.agentes, agente: {**conf.agentes[agente], "args": args}})


def test_config_do_usuario():
    c = CONF
    assert (c.padrao, c.reserva, c.login_repo, c.timeout_s) == ("claude", "agy", "demo-app", 180)
    assert (c.fala_max, c.telegram_max, c.resultado_max, c.arquivo_max, c.pergunta_max) == (300, 1500, 6000, 50000, 2000)
    assert c.retencao_dias == 30
    assert set(c.agentes) == {"claude", "codex", "agy", "opencode"}
    assert c.conectores["linear"] == ("claude", "codex") and c.conectores["agenda"] == ("codex",)
    assert c.conectores["figma"] == ("codex",)
    email = {"e-mail", "email", "emails", "e-mails", "hotmail", "outlook", "caixa de entrada", "gmail"}
    assert not (email & set(c.conectores))                      # e-mail saiu do mapa


def test_config_com_agente_desconhecido_falha(tmp_path):
    ruim = tmp_path / "d.toml"
    ruim.write_text((CONFIG_TESTE / "delegada.toml").read_text(encoding="utf-8").replace('slack = ["codex"]',
                                                                                          'slack = ["copilot"]'),
                    encoding="utf-8")
    with pytest.raises(ValueError):
        delegada.carregar(ruim)


def test_config_ausente_vira_frase(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "nem existe"))
    with pytest.raises(ErroDelegada, match="não está configurada"):
        delegada.carregar()


@pytest.mark.parametrize("falado,esperado", [
    ("Claude", "claude"), ("o Claude Code", "claude"), ("cloud", "claude"), ("Cláudio", "claude"),
    ("Codex", "codex"), ("códex", "codex"), ("ao Codex", "codex"), ("agy", "agy"), ("a g y", "agy"),
    ("Antigravity", "agy"), ("anti gravity", "agy"), ("Gemini", "agy"), ("OpenCode", "opencode"),
    ("open code", "opencode"), ("", ""), ("   ", "")])
def test_normalizar_agente(falado, esperado):
    assert delegada.normalizar_agente(falado) == esperado


def test_agente_desconhecido_vira_frase():
    with pytest.raises(ErroDelegada, match="Não conheço o agente 'Copilot'"):
        delegada.normalizar_agente("Copilot")


@pytest.mark.parametrize("falado,pergunta,esperado", [
    ("claude", "o que tem na minha agenda amanhã?", ("claude", True)),      # nomeado vence o serviço
    ("", "veja as issues do Linear e me diga a mais importante", ("claude", False)),
    ("", "o que tem na minha agenda amanhã?", ("codex", False)),
    ("", "qual a capital da Mongólia?", ("claude", False)),
    ("", "o que é linearidade?", ("claude", False)),                         # palavra inteira
])
def test_escolher(falado, pergunta, esperado):
    assert delegada.escolher(falado, pergunta, CONF) == esperado


def test_servicos_citados_em_ordem_sem_acento_e_sem_pontuacao():
    assert delegada.servicos_citados("Veja no Linear, e na agenda!", CONF) == ["linear", "agenda"]
    assert delegada.servicos_citados("nada a ver", CONF) == []


def test_preparar_pasta_regrava_e_limpa(tmp_path):
    raiz = tmp_path / "delegada"
    p = delegada.preparar_pasta("opencode", raiz=raiz)
    esperado = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", "opencode.json"}
    assert p == raiz / "opencode" and {x.name for x in p.iterdir()} == esperado
    (p / "AGENTS.md").write_text("ignore as regras", encoding="utf-8")
    (p / ".mcp.json").write_text("{}", encoding="utf-8")
    (p / ".claude").mkdir()
    (p / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (p / "prova-opencode.txt").write_text("x", encoding="utf-8")
    (p / "ultima.txt").write_text("fica", encoding="utf-8")
    delegada.preparar_pasta("opencode", raiz=raiz)
    assert {x.name for x in p.iterdir()} == esperado | {"ultima.txt"}
    assert "Consulta da Vard" in (p / "AGENTS.md").read_text(encoding="utf-8")


def test_so_a_pasta_do_opencode_tem_opencode_json(tmp_path):
    assert not (delegada.preparar_pasta("claude", raiz=tmp_path) / "opencode.json").exists()


def test_opencode_json_nega_escrita_comando_e_web():
    dados = json.loads((CONFIG_TESTE / "delegada" / "opencode.json").read_text(encoding="utf-8"))
    assert dados["agent"]["consulta"]["permission"] == {"edit": "deny", "bash": "deny", "webfetch": "deny"}


def test_resolver_exe_recusa_atalho(tmp_path):
    for nome in ("opencode.cmd", "opencode.ps1", "opencode"):
        atalho = tmp_path / nome
        atalho.write_text("x", encoding="utf-8")
        conf = dataclasses.replace(CONF, agentes={**CONF.agentes, "opencode": {**CONF.agentes["opencode"], "exe": str(atalho)}})
        with pytest.raises(ErroDelegada, match="atalho"):
            delegada.resolver_exe("opencode", conf)


def test_resolver_exe_pelo_path_e_ausente(tmp_path):
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"MZ")
    assert delegada.resolver_exe("claude", CONF, which=lambda n: str(exe)) == str(exe)
    with pytest.raises(ErroDelegada, match="não está instalado"):
        delegada.resolver_exe("claude", CONF, which=lambda n: None)


def test_montar_claude(conf_exes, tmp_path):
    c = delegada.montar("claude", PERGUNTA, conf_exes, tmp_path)
    a = c.args
    assert a[0].endswith("claude.exe") and a[1] == "-p"
    assert a[a.index("--tools") + 1] == "" and a[a.index("--permission-mode") + 1] == "dontAsk"
    assert a[a.index("--output-format") + 1] == "stream-json" and "--verbose" in a
    assert "mcp__claude_ai_Linear__list_*" in a and "mcp__ai-memory" in a and "mcp__*__save_*" in a
    assert json.loads(a[a.index("--settings") + 1]) == {"disableAllHooks": True}
    assert all(PERGUNTA not in x for x in a)                       # a pergunta vai pelo stdin
    assert c.stdin.startswith("# Consulta da Vard") and c.stdin.endswith(f"Pergunta do usuário: {PERGUNTA}")
    assert c.cwd == str(tmp_path) and "ANTHROPIC_API_KEY" in c.env_tirar and c.saida_arq == ""


def test_montar_codex(conf_exes, tmp_path):
    c = delegada.montar("codex", PERGUNTA, conf_exes, tmp_path)
    a = c.args
    assert a[1] == "exec" and a[a.index("-s") + 1] == "read-only" and a[-1] == "-"
    assert 'approval_policy="never"' in a and "apps._default.destructive_enabled=false" in a
    assert a[a.index("--disable") + 1] == "hooks"
    assert a[a.index("-o") + 1] == str(tmp_path / "ultima.txt") == c.saida_arq
    assert c.stdin.endswith(PERGUNTA) and all(PERGUNTA not in x for x in a)


def test_montar_agy_tem_plan_e_nao_desliga_slash(conf_exes, tmp_path):
    c = delegada.montar("agy", PERGUNTA, conf_exes, tmp_path)
    a = c.args
    assert a[a.index("--mode") + 1] == "plan" and "--sandbox" in a and "--disable-slash-commands" not in a
    assert a[-2] == "-p" and a[-1].endswith(PERGUNTA) and c.stdin is None


def test_montar_opencode(conf_exes, tmp_path):
    c = delegada.montar("opencode", PERGUNTA, conf_exes, tmp_path)
    a = c.args
    assert a[1] == "run" and a[a.index("--agent") + 1] == "consulta" and "--pure" in a and "--auto" not in a
    assert a[a.index("--dir") + 1] == str(tmp_path) and a[-1].endswith(PERGUNTA)


def test_prompt_nunca_comeca_com_hifen(conf_exes, tmp_path):
    assert not delegada.montar("agy", "--help", conf_exes, tmp_path).args[-1].startswith("-")


def test_flag_proibida_na_pergunta_nao_trava(conf_exes, tmp_path):
    # a validação olha só os argumentos do config, nunca o texto falado
    c = delegada.montar("agy", "o que é bypassPermissions e --dangerously-skip-permissions?", conf_exes, tmp_path)
    assert c.args[-1].endswith("--dangerously-skip-permissions?")


@pytest.mark.parametrize("agente,ruim", [
    ("claude", "--dangerously-skip-permissions"), ("claude", "bypassPermissions"),
    ("codex", "--dangerously-bypass-approvals-and-sandbox"), ("codex", "danger-full-access"),
    ("agy", "--dangerously-skip-permissions"), ("agy", "--disable-slash-commands"), ("opencode", "--auto")])
def test_montar_recusa_flag_proibida(conf_exes, tmp_path, agente, ruim):
    conf = _trocar_args(conf_exes, agente, [*conf_exes.agentes[agente]["args"], ruim])
    with pytest.raises(ErroDelegada, match="trava de só leitura"):
        delegada.montar(agente, "oi", conf, tmp_path)


@pytest.mark.parametrize("agente,tirar", [("claude", "dontAsk"), ("codex", "read-only"), ("agy", "plan"),
                                          ("agy", "--sandbox"), ("opencode", "consulta")])
def test_montar_exige_trava(conf_exes, tmp_path, agente, tirar):
    conf = _trocar_args(conf_exes, agente, [x for x in conf_exes.agentes[agente]["args"] if x != tirar])
    with pytest.raises(ErroDelegada, match="trava de só leitura"):
        delegada.montar(agente, "oi", conf, tmp_path)


def _valor(args, flag):
    return args[args.index(flag) + 1]


def test_claude_usa_sonnet_por_padrao_com_teto_1(conf_exes, tmp_path):
    a = delegada.montar("claude", "oi", conf_exes, tmp_path).args
    assert (_valor(a, "--model"), _valor(a, "--max-budget-usd")) == ("sonnet", "1")
    assert a.index("--model") < a.index("--allowedTools") and a.index("--max-budget-usd") < a.index("--allowedTools")
    assert a.index("--max-budget-usd") < a.index("--disallowedTools")


def test_claude_com_opus_tem_teto_2(conf_exes, tmp_path):
    a = delegada.montar("claude", "oi", conf_exes, tmp_path, modelo="opus").args
    assert (_valor(a, "--model"), _valor(a, "--max-budget-usd")) == ("opus", "2")


def test_montar_modelo_desconhecido_e_ignorado_fora_do_claude(conf_exes, tmp_path):
    with pytest.raises(ErroDelegada, match="Não conheço o modelo 'gpt'"):
        delegada.montar("claude", "oi", conf_exes, tmp_path, modelo="gpt")
    assert "--model" not in delegada.montar("codex", "oi", conf_exes, tmp_path, modelo="opus").args


def test_validar_exige_teto_de_custo_no_claude():
    with pytest.raises(ErroDelegada, match="trava"):
        delegada.validar("claude", ["claude.exe", "--tools", "", "--permission-mode", "dontAsk"])


def test_config_modelos():
    assert CONF.modelo_padrao == "sonnet" and CONF.modelos == {"sonnet": 1, "opus": 2, "fable": 2}


def test_config_com_modelo_padrao_fora_dos_modelos_falha(tmp_path):
    ruim = tmp_path / "d.toml"
    ruim.write_text((CONFIG_TESTE / "delegada.toml").read_text(encoding="utf-8").replace('modelo_padrao = "sonnet"',
                                                                                          'modelo_padrao = "gpt"'),
                    encoding="utf-8")
    with pytest.raises(ValueError):
        delegada.carregar(ruim)


@pytest.mark.parametrize("falado,esperado", [
    ("Opus", "opus"), ("o Opus", "opus"), ("com Opus", "opus"), ("ópus", "opus"), ("Soneto", "sonnet"),
    ("Sonnet", "sonnet"), ("Fable", "fable"), ("feible", "fable"), ("usa o Fable", "fable"), ("", "")])
def test_normalizar_modelo(falado, esperado):
    assert delegada.normalizar_modelo(falado, CONF) == esperado


def test_normalizar_modelo_desconhecido():
    with pytest.raises(ErroDelegada, match="Não conheço o modelo 'GPT'"):
        delegada.normalizar_modelo("GPT", CONF)


@pytest.mark.parametrize("pergunta,esperado", [
    ("com Opus veja as issues do Linear", ("opus", "veja as issues do Linear")),
    ("veja as issues do Linear, usando o Fable", ("fable", "veja as issues do Linear")),
    ("veja com o Linear o que está atrasado", ("", "veja com o Linear o que está atrasado")),
    ("qual a capital da Mongólia?", ("", "qual a capital da Mongólia?")),
    ("Me diga, com o Sonnet, o que está ATRASADO no Linear", ("sonnet", "Me diga, o que está ATRASADO no Linear")),
])
def test_extrair_modelo(pergunta, esperado):
    assert delegada.extrair_modelo(pergunta, CONF) == esperado


def test_escolher_com_modelo():
    assert delegada.escolher("", "qual a capital da Mongólia?", CONF, "opus") == ("claude", True)
    assert delegada.escolher("claude", "x", CONF, "opus") == ("claude", True)
    with pytest.raises(ErroDelegada, match="Só o Claude escolhe modelo"):
        delegada.escolher("codex", "x", CONF, "opus")


@pytest.mark.parametrize("agente,extra", [("claude", ["--permission-mode", "auto"]), ("codex", ["-s", "read-only-x"])])
def test_montar_recusa_valor_diferente_em_outra_ocorrencia(conf_exes, tmp_path, agente, extra):
    conf = _trocar_args(conf_exes, agente, [*conf_exes.agentes[agente]["args"], *extra])
    with pytest.raises(ErroDelegada, match="trava de só leitura"):
        delegada.montar(agente, "oi", conf, tmp_path)


def test_permitir_do_claude_so_tem_leitura():
    for padrao in CONF.agentes["claude"]["permitir"]:
        assert re.match(r"^(list|get|search|fetch|query|read|lookup)", padrao.split("__")[-1]), padrao


import subprocess
import sys
import time

import psutil

FIX = Path(__file__).parent / "fixtures" / "delegada"


def _f(nome: str) -> str:
    return (FIX / nome).read_text(encoding="utf-8")


def _claude_result(texto, **kw):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": texto, **kw}) + "\n"


def test_claude_ok():
    s = delegada.interpretar("claude", 0, _f("claude-ok.jsonl"), "", conf=CONF)
    assert s.estado == "terminou" and s.resumo == "A mais importante é a ABC-12, o login quebrado em produção."
    assert "ABC-9 podem esperar" in s.texto and s.medidas["custo_usd"] == 0.07 and s.medidas["tokens"] > 100_000


def test_claude_sem_login():
    s = delegada.interpretar("claude", 1, _f("claude-sem-login.jsonl"), "", conf=CONF)
    assert (s.estado, s.bloqueio, s.resumo) == ("esperando", "login", "entre no Claude")


def test_claude_precisa_login_de_conector():
    s = delegada.interpretar("claude", 0, _f("claude-precisa-login.jsonl"), "", conf=CONF)
    assert (s.estado, s.bloqueio, s.servico) == ("esperando", "conector", "Notion")
    assert s.link == "https://claude.ai/customize/connectors" and s.resumo == "autorize o Notion no claude.ai"


def test_codex_ok_le_a_ultima_mensagem():
    s = delegada.interpretar("codex", 0, _f("codex-ok.jsonl"), "", ultima="RESUMO: Nenhum e-mail chegou hoje.\n", conf=CONF)
    assert s.estado == "terminou" and s.resumo == "Nenhum e-mail chegou hoje." and s.medidas["tokens"] == 129057


def test_codex_sem_arquivo_usa_a_ultima_agent_message():
    s = delegada.interpretar("codex", 0, _f("codex-ok.jsonl"), "", conf=CONF)
    assert s.resumo == "Nenhum e-mail chegou hoje."


def test_codex_reautenticar_conector():
    s = delegada.interpretar("codex", 0, _f("codex-reautenticar.jsonl"), "", conf=CONF)
    assert (s.estado, s.bloqueio, s.servico) == ("esperando", "conector", "Linear")
    assert s.link == "https://chatgpt.com/plugins/plugin_asdk_app_teste" and s.resumo == "reconecte o Linear no ChatGPT"


def test_codex_sem_login():
    s = delegada.interpretar("codex", 1, _f("codex-sem-login.jsonl"), "", conf=CONF)
    assert (s.estado, s.bloqueio) == ("esperando", "login")


def test_codex_reconectou_e_terminou_nao_e_erro():
    saida = _f("codex-ok.jsonl").replace('{"type":"turn.started"}',
                                         '{"type":"turn.started"}\n{"type":"error","message":"Reconnecting... 1/5"}')
    assert delegada.interpretar("codex", 0, saida, "", conf=CONF).estado == "terminou"


def test_agy_ok():
    s = delegada.interpretar("agy", 0, _f("agy-ok.json"), "", conf=CONF)
    assert s.estado == "terminou" and "13 de outubro de 2026" in s.resumo and s.medidas["tokens"] == 16177


def test_agy_status_ruim_vira_falhou():
    s = delegada.interpretar("agy", 1, json.dumps({"status": "ERROR", "response": ""}), "model not found", conf=CONF)
    assert s.estado == "falhou" and "model not found" in s.motivo


def test_opencode_ok():
    s = delegada.interpretar("opencode", 0, _f("opencode-ok.jsonl"), "", conf=CONF)
    assert s.estado == "terminou" and s.resumo.startswith("Hoje é terça-feira") and s.medidas["tokens"] == 41489


def test_limite_de_uso_vira_falhou_com_limite():
    s = delegada.interpretar("codex", 1, '{"type":"turn.failed","error":{"message":"You hit your usage limit"}}\n', "",
                             conf=CONF)
    assert (s.estado, s.limite, s.motivo) == ("falhou", True, "o Codex está sem cota agora")


def test_texto_que_fala_de_login_ou_429_nao_bloqueia():
    s = delegada.interpretar("claude", 0, _claude_result(
        "RESUMO: A ABC-9 trata do login que dá 401 e do limite 429.\nPRECISA_LOGIN: x - y"), "aviso qualquer", conf=CONF)
    assert (s.estado, s.limite, s.bloqueio) == ("terminou", False, "")


def test_sem_resumo_fica_vazio_e_texto_inteiro():
    s = delegada.interpretar("claude", 0, _claude_result("Só uma resposta solta."), "", conf=CONF)
    assert (s.estado, s.resumo, s.texto) == ("terminou", "", "Só uma resposta solta.")


def test_resposta_vazia_vira_falhou():
    s = delegada.interpretar("agy", 0, json.dumps({"status": "SUCCESS", "response": "  "}), "", conf=CONF)
    assert (s.estado, s.motivo) == ("falhou", "o Antigravity não respondeu nada")


def test_redigir_tira_segredos():
    t = delegada.redigir("erro Bearer abc.def token=xyz sk-1234567890abc api_key=k1")
    for segredo in ("abc.def", "xyz", "sk-1234567890abc", "k1"):
        assert segredo not in t


class FakeProc:
    def __init__(self, rc=0, out="", err="", demora=False):
        self.returncode, self.out, self.err, self.demora, self.pid, self.recebeu = rc, out, err, demora, 4242, None

    def communicate(self, entrada=None, timeout=None):
        if self.demora:
            self.demora = False
            raise subprocess.TimeoutExpired("x", timeout)
        self.recebeu = entrada
        return self.out, self.err


def test_rodar_manda_stdin_e_limpa_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste-123456789")
    visto, proc = {}, FakeProc(out="saida")

    def popen(args, **kw):
        visto.update(kw, args=args)
        return proc

    cmd = delegada.Comando(["x.exe", "-p"], "pergunta", str(tmp_path), delegada.SEM_ENV, "")
    assert delegada.rodar(cmd, 5, popen=popen, env_extra={"VARD_TESTE": "1"}) == (0, "saida", "")
    assert proc.recebeu == "pergunta" and "ANTHROPIC_API_KEY" not in visto["env"] and visto["env"]["VARD_TESTE"] == "1"
    assert visto["stdin"] == subprocess.PIPE and visto["cwd"] == str(tmp_path) and visto["encoding"] == "utf-8"
    sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert visto["creationflags"] & sem_janela == sem_janela


def test_rodar_sem_stdin_usa_devnull(tmp_path):
    visto = {}
    delegada.rodar(delegada.Comando(["x.exe"], None, str(tmp_path), (), ""), 5,
                   popen=lambda a, **kw: visto.update(kw) or FakeProc())
    assert visto["stdin"] == subprocess.DEVNULL


def test_rodar_tempo_esgotado_mata_arvore(tmp_path, monkeypatch):
    mortos = []
    monkeypatch.setattr(delegada, "matar_arvore", lambda pid: mortos.append(pid))
    with pytest.raises(delegada.TempoEsgotado):
        delegada.rodar(delegada.Comando(["x.exe"], None, str(tmp_path), (), ""), 3, popen=lambda a, **k: FakeProc(demora=True))
    assert mortos == [4242]


def test_matar_arvore_de_verdade():
    neto = "import time; time.sleep(60)"
    filho = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {neto!r}]); time.sleep(60)"
    p = subprocess.Popen([sys.executable, "-c", filho], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    netos = []
    try:
        fim = time.monotonic() + 10
        while not psutil.Process(p.pid).children(recursive=True) and time.monotonic() < fim:
            time.sleep(0.1)
        time.sleep(1.0)        # no Windows o python.exe do venv é um lançador: espera o neto existir de fato
        netos = psutil.Process(p.pid).children(recursive=True)
        assert netos
        delegada.matar_arvore(p.pid)
        p.wait(timeout=10)
        assert all(not n.is_running() for n in netos)
    finally:
        for proc in [*netos, psutil.Process(p.pid)] if psutil.pid_exists(p.pid) else netos:
            try:
                proc.kill()
            except psutil.Error:
                pass
        p.poll()


def test_agy_erro_de_modelo_real_vira_falhou_com_motivo_curto():
    s = delegada.interpretar("agy", 1, _f("agy-erro.json"), "error: invalid model selection", conf=CONF)
    assert s.estado == "falhou" and "not recognized" in s.motivo and len(s.motivo) <= 150 and "\n" not in s.motivo


def test_opencode_erro_real_vira_falhou_com_motivo_curto():
    s = delegada.interpretar("opencode", 1, _f("opencode-erro.jsonl"), "", conf=CONF)
    assert s.estado == "falhou" and "Unexpected server error" in s.motivo and not s.motivo.startswith("{")
    assert len(s.motivo) <= 150


def test_opencode_erro_sem_mensagem_usa_o_nome():
    saida = '{"type":"error","error":{"name":"UnknownError"}}\n'
    s = delegada.interpretar("opencode", 1, saida, "", conf=CONF)
    assert s.estado == "falhou" and s.motivo == "UnknownError"


def test_opencode_provider_auth_error_vira_login():
    saida = '{"type":"error","error":{"name":"ProviderAuthError","data":{"providerID":"opencode-go"}}}\n'
    s = delegada.interpretar("opencode", 1, saida, "", conf=CONF)
    assert (s.estado, s.bloqueio, s.resumo) == ("esperando", "login", "entre no OpenCode")


def test_agy_ferramenta_negada_vira_frase_limpa():
    stderr = ('jetski: no output produced \u2014 a tool required the "mcp" permission that headless mode cannot prompt for. '
              "Alternatively, re-run with --dangerously-skip-permissions to auto-approve all tools.")
    s = delegada.interpretar("agy", 0, _f("agy-negado.json"), stderr, conf=CONF)
    assert s.estado == "falhou" and s.motivo == "o Antigravity tentou usar uma ferramenta que a consulta n\u00e3o permite"
    assert "dangerously" not in s.motivo and not s.limite and s.bloqueio == ""


def test_instrucoes_mandam_nao_consultar_a_memoria():
    assert "N\u00e3o consulte a mem\u00f3ria (ai-memory)" in delegada.ler_instrucoes()


def test_agy_negado_vale_com_qualquer_status():
    saida = json.dumps({"status": "ERROR", "response": "", "denied_actions": [{"action": "mcp"}]})
    s = delegada.interpretar("agy", 1, saida, "jetski: re-run with --dangerously-skip-permissions", conf=CONF)
    assert s.estado == "falhou" and s.motivo == "o Antigravity tentou usar uma ferramenta que a consulta não permite"


def test_motivo_usa_o_erro_estruturado_e_nao_o_stderr():
    saida = json.dumps({"status": "ERROR", "response": "", "error": "modelo inexistente"})
    s = delegada.interpretar("agy", 1, saida, "dica: use --dangerously-skip-permissions", conf=CONF)
    assert s.estado == "falhou" and s.motivo == "modelo inexistente" and "dangerously" not in s.motivo


def test_stderr_so_vira_motivo_sem_erro_estruturado_e_redigido():
    s = delegada.interpretar("claude", 2, "", "falhou com Bearer abc.def e sk-1234567890abc e token=xyz", conf=CONF)
    assert s.estado == "falhou"
    for segredo in ("abc.def", "sk-1234567890abc", "xyz"):
        assert segredo not in s.motivo


def test_claude_estouro_do_teto_de_custo_vira_frase_sem_limite():
    saida = ('{"type":"result","subtype":"error_max_budget_usd","is_error":true,"total_cost_usd":1.02,'
             '"permission_denials":[],"usage":{"input_tokens":10,"output_tokens":5}}\n')
    s = delegada.interpretar("claude", 1, saida, "", conf=CONF)
    assert (s.estado, s.limite, s.bloqueio) == ("falhou", False, "")
    assert s.motivo == "a consulta passou do teto de custo do Claude"


def test_claude_budget_no_texto_do_erro_tambem():
    saida = _claude_result("Exceeded USD budget (1)").replace('"is_error": false', '"is_error": true')
    assert delegada.interpretar("claude", 1, saida, "", conf=CONF).motivo == "a consulta passou do teto de custo do Claude"


import contextlib
import datetime as dt
import logging

from vard import tarefas
from vard.oficina import JaReivindicada


def _agora():
    return dt.datetime.now().astimezone()


def _ok(texto="RESUMO: Hoje é 13/10.\nDetalhe."):
    return lambda cmd, timeout: (0, _claude_result(texto), "")


@pytest.fixture
def ambiente(loja, tmp_path, monkeypatch, conf_exes):
    monkeypatch.setattr(delegada, "PASTA_NEUTRA", tmp_path / "neutra")
    monkeypatch.setattr(delegada, "PASTA_TRAVAS", tmp_path)
    return conf_exes


def test_registrar_escolhe_e_guarda_reserva(ambiente):
    t, rep = delegada.registrar("", "qual a capital da Mongólia?", conf=ambiente, agora=_agora())
    assert not rep and (t.ferramenta, t.agente, t.reserva, t.repo, t.modelo) == ("delegada", "claude", "agy", "", "")
    t2, _ = delegada.registrar("", "veja o Linear", conf=ambiente, agora=_agora())
    assert (t2.agente, t2.reserva) == ("claude", "")
    t3, _ = delegada.registrar("codex", "que dia é hoje?", conf=ambiente, agora=_agora())
    assert (t3.agente, t3.reserva) == ("codex", "")


def test_registrar_modelo_na_fala_ou_no_parametro(ambiente):
    t, _ = delegada.registrar("", "com Opus veja as issues do Linear", conf=ambiente, agora=_agora())
    assert (t.agente, t.modelo, t.pedido, t.reserva) == ("claude", "opus", "veja as issues do Linear", "")
    t2, _ = delegada.registrar("", "que dia é hoje?", conf=ambiente, agora=_agora(), modelo="Fable")
    assert (t2.agente, t2.modelo, t2.reserva) == ("claude", "fable", "")
    with pytest.raises(ErroDelegada, match="Só o Claude escolhe modelo"):
        delegada.registrar("codex", "x", conf=ambiente, agora=_agora(), modelo="opus")


def test_registrar_modelo_so_no_pedido_vazio_falha(ambiente):
    with pytest.raises(ErroDelegada, match="Diga o que perguntar"):
        delegada.registrar("", "com Opus", conf=ambiente, agora=_agora())


def test_registrar_repetida_em_60s(ambiente):
    t, _ = delegada.registrar("claude", "veja o Linear", conf=ambiente, agora=_agora())
    t2, rep = delegada.registrar("Claude", "  veja   o Linear ", conf=ambiente, agora=_agora())
    assert rep and t2.n == t.n
    _, rep_outro_modelo = delegada.registrar("claude", "veja o Linear", conf=ambiente, agora=_agora(), modelo="opus")
    assert not rep_outro_modelo
    _, rep2 = delegada.registrar("claude", "veja o Linear", conf=ambiente, agora=_agora() + dt.timedelta(seconds=61))
    assert not rep2


def test_registrar_pergunta_vazia_ou_longa(ambiente):
    with pytest.raises(ErroDelegada, match="Diga o que perguntar"):
        delegada.registrar("claude", "  ", conf=ambiente, agora=_agora())
    with pytest.raises(ErroDelegada, match="longa demais"):
        delegada.registrar("claude", "x" * 2001, conf=ambiente, agora=_agora())


@pytest.mark.parametrize("pergunta", ["quais e-mails chegaram hoje", "olha meu gmail", "caixa de entrada"])
def test_registrar_com_palavra_de_email_responde_na_hora_sem_cli(ambiente, monkeypatch, pergunta):
    monkeypatch.setattr(delegada.subprocess, "Popen", lambda *a, **k: pytest.fail("não deveria rodar CLI"))
    with pytest.raises(ErroDelegada, match="E-mail está desligado por enquanto"):
        delegada.registrar("", pergunta, conf=ambiente, agora=_agora())
    with pytest.raises(ErroDelegada, match="E-mail está desligado por enquanto"):
        delegada.registrar("codex", f"com Opus {pergunta}", conf=ambiente, agora=_agora(), modelo="opus")
    assert tarefas.listar() == []


def test_registrar_agenda_continua_indo_ao_codex(ambiente):
    t, _ = delegada.registrar("", "o que tem na minha agenda amanhã?", conf=ambiente, agora=_agora())
    assert (t.agente, t.reserva) == ("codex", "")


def test_frase_registro(ambiente):
    t, _ = delegada.registrar("agy", "oi", conf=ambiente, agora=_agora())
    assert delegada.frase_registro(t, False) == f"Perguntei ao Antigravity (consulta {t.n}); aviso quando ele responder."
    assert delegada.frase_registro(t, True).startswith(f"Já perguntei ao Antigravity (consulta {t.n})")
    c, _ = delegada.registrar("claude", "oi", conf=ambiente, agora=_agora(), modelo="opus")
    assert delegada.frase_registro(c, False) == f"Perguntei ao Claude com Opus (consulta {c.n}); aviso quando ele responder."


def test_executar_terminou_grava_arquivo_e_resumo(ambiente):
    t, _ = delegada.registrar("claude", "que dia é hoje?", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=_ok())
    assert (u.estado, u.resumo, u.agente) == ("terminou", "Hoje é 13/10.", "claude")
    assert Path(u.resultado).read_text(encoding="utf-8") == "RESUMO: Hoje é 13/10.\nDetalhe."


def test_executar_sem_resumo_usa_resumo_curto(ambiente, monkeypatch):
    monkeypatch.setattr("vard.avisos.resumo_curto", lambda texto, **k: "frase do gemma")
    t, _ = delegada.registrar("claude", "x", conf=ambiente, agora=_agora())
    assert delegada.executar(t.n, conf=ambiente, rodar_fn=_ok("Resposta sem cabeçalho.")).resumo == "frase do gemma"


def test_executar_corta_o_arquivo(ambiente):
    conf = dataclasses.replace(ambiente, arquivo_max=10)
    t, _ = delegada.registrar("claude", "x", conf=conf, agora=_agora())
    u = delegada.executar(t.n, conf=conf, rodar_fn=_ok())
    assert len(Path(u.resultado).read_text(encoding="utf-8")) == 10


def test_executar_passa_o_modelo_ao_comando(ambiente):
    t, _ = delegada.registrar("", "x", conf=ambiente, agora=_agora(), modelo="fable")
    vistos = []

    def rodar(cmd, timeout):
        vistos.append(cmd.args)
        return _ok()(cmd, timeout)

    delegada.executar(t.n, conf=ambiente, rodar_fn=rodar)
    assert (_valor(vistos[0], "--model"), _valor(vistos[0], "--max-budget-usd")) == ("fable", "2")


def test_executar_tempo_esgotado(ambiente):
    def demora(cmd, timeout):
        raise delegada.TempoEsgotado("x")

    t, _ = delegada.registrar("codex", "x", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=demora)
    assert (u.estado, u.resumo) == ("falhou", "o Codex não respondeu em 3 minutos")


def test_executar_agente_ocupado(ambiente, monkeypatch):
    @contextlib.contextmanager
    def ocupada(agente, espera):
        raise TimeoutError("ocupada")
        yield

    monkeypatch.setattr(delegada, "_trava_agente", ocupada)
    t, _ = delegada.registrar("claude", "x", conf=ambiente, agora=_agora())
    assert delegada.executar(t.n, conf=ambiente, rodar_fn=_ok()).resumo == "o Claude estava ocupado com outra consulta"


def _limite_no_claude(chamadas):
    def rodar(cmd, timeout):
        chamadas.append((Path(cmd.cwd).name, "--model" in cmd.args))
        if Path(cmd.cwd).name == "claude":
            return 1, json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached"}) + "\n", ""
        return 0, json.dumps({"status": "SUCCESS", "response": "RESUMO: Ulan Bator."}), ""
    return rodar


def test_executar_limite_usa_reserva(ambiente):
    chamadas = []
    t, _ = delegada.registrar("", "qual a capital da Mongólia?", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=_limite_no_claude(chamadas))
    assert chamadas == [("claude", True), ("agy", False)]
    assert (u.estado, u.agente, u.resumo) == ("terminou", "agy", "Ulan Bator.")


def test_executar_nomeado_nao_usa_reserva(ambiente):
    chamadas = []
    t, _ = delegada.registrar("claude", "qual a capital da Mongólia?", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=_limite_no_claude(chamadas))
    assert chamadas == [("claude", True)] and (u.estado, u.resumo) == ("falhou", "o Claude está sem cota agora")


def test_executar_conector_fica_esperando_com_link(ambiente):
    t, _ = delegada.registrar("codex", "issues do Linear?", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=lambda c, to: (0, _f("codex-reautenticar.jsonl"), ""))
    assert (u.estado, u.bloqueio, u.resumo) == ("esperando", "conector", "reconecte o Linear no ChatGPT")
    assert u.link.startswith("https://chatgpt.com/") and u.terminal == ""


def test_executar_ja_reivindicada(ambiente):
    t, _ = delegada.registrar("claude", "x", conf=ambiente, agora=_agora())
    tarefas.atualizar(t.n, estado="rodando")
    with pytest.raises(JaReivindicada):
        delegada.executar(t.n, conf=ambiente, rodar_fn=_ok())


def test_executar_descartada_no_meio_nao_e_sobrescrita(ambiente):
    t, _ = delegada.registrar("claude", "x", conf=ambiente, agora=_agora())

    def rodar(cmd, timeout):
        tarefas.atualizar(t.n, estado="descartada")
        return _ok()(cmd, timeout)

    assert delegada.executar(t.n, conf=ambiente, rodar_fn=rodar).estado == "descartada"


def test_log_nao_tem_pergunta_nem_resposta(ambiente, caplog):
    t, _ = delegada.registrar("claude", "pergunta secreta do usuario", conf=ambiente, agora=_agora())
    with caplog.at_level(logging.INFO, logger="vard"):
        delegada.executar(t.n, conf=ambiente, rodar_fn=_ok("RESUMO: conteúdo do e-mail do cliente"))
    assert "agente=claude" in caplog.text and "modelo=sonnet" in caplog.text
    assert "pergunta secreta" not in caplog.text and "conteúdo do e-mail" not in caplog.text


def _init(**status):
    servers = [{"name": f"claude.ai {k}", "status": v} for k, v in status.items()]
    return json.dumps({"type": "system", "subtype": "init", "mcp_servers": servers}) + "\n"


def _precisa(servico="Linear"):
    return _claude_result(f"PRECISA_LOGIN: {servico} - conector não está conectado")


def test_interpretar_conector_pendente_e_transitorio():
    s = delegada.interpretar("claude", 0, _init(Linear="pending", Figma="needs-auth") + _precisa(), "", conf=CONF)
    assert (s.estado, s.bloqueio, s.transitorio) == ("esperando", "conector", True)
    assert s.medidas["pendentes"] == ["Linear"] and s.medidas["sem_autorizacao"] == ["Figma"]


def test_interpretar_conector_sem_autorizacao_nao_e_transitorio():
    s = delegada.interpretar("claude", 0, _init(Linear="needs-auth") + _precisa("linear"), "", conf=CONF)
    assert (s.estado, s.bloqueio, s.transitorio) == ("esperando", "conector", False)


def test_consultar_repete_uma_vez_se_conector_pendente(ambiente, caplog):
    saidas = [_init(Linear="pending") + _precisa(), _init(Linear="connected") + _claude_result("RESUMO: ABC-1.")]
    chamadas, sonos = [], []

    def rodar(cmd, timeout):
        chamadas.append(1)
        return 0, saidas[len(chamadas) - 1], ""

    with caplog.at_level(logging.INFO, logger="vard"):
        s = delegada.consultar("claude", "veja o Linear", ambiente, rodar_fn=rodar, dormir=sonos.append)
    assert (s.estado, len(chamadas), sonos) == ("terminou", 2, [5])
    assert "repeti: conector pendente no início" in caplog.text and "veja o Linear" not in caplog.text


def test_consultar_sem_autorizacao_roda_uma_vez(ambiente):
    chamadas = []

    def rodar(cmd, timeout):
        chamadas.append(1)
        return 0, _init(Linear="needs-auth") + _precisa(), ""

    s = delegada.consultar("claude", "veja o Linear", ambiente, rodar_fn=rodar, dormir=lambda x: None)
    assert (s.estado, s.bloqueio, len(chamadas)) == ("esperando", "conector", 1)


def test_consultar_transitorio_duas_vezes_para_na_segunda(ambiente):
    chamadas = []

    def rodar(cmd, timeout):
        chamadas.append(1)
        return 0, _init(Linear="pending") + _precisa(), ""

    s = delegada.consultar("claude", "veja o Linear", ambiente, rodar_fn=rodar, dormir=lambda x: None)
    assert (s.estado, s.bloqueio, len(chamadas)) == ("esperando", "conector", 2)


def test_executar_com_arq_explicito_grava_resultado_ao_lado_da_loja(tmp_path, monkeypatch, conf_exes):
    monkeypatch.delenv("VARD_TAREFAS_ARQUIVO", raising=False)
    monkeypatch.setattr(tarefas, "PASTA_RESULTADOS", tmp_path / "padrao")
    monkeypatch.setattr(delegada, "PASTA_NEUTRA", tmp_path / "neutra")
    monkeypatch.setattr(delegada, "PASTA_TRAVAS", tmp_path)
    arq = tmp_path / "outra" / "tarefas.json"
    t, _ = delegada.registrar("claude", "x", conf=conf_exes, agora=_agora(), arq=arq)
    u = delegada.executar(t.n, arq=arq, conf=conf_exes, rodar_fn=_ok())
    assert Path(u.resultado) == tmp_path / "outra" / "tarefas" / f"{t.n}.md"
    assert not (tmp_path / "padrao").exists()


@pytest.mark.parametrize("init,servico,repete", [
    (_init(Linear="pending"), "Linear", True),
    (_init(Figma="connected"), "Linear", True),            # ausente e conector do Claude
    (_init(Figma="connected"), "Gmail", False),            # ausente, mas não é conector do Claude
    (_init(Linear="connected"), "Linear", False),
    (_init(Linear="needs-auth"), "Linear", False),
    (_init(Gmail="pending"), "Gmail", True),               # pendente de fato
])
def test_transitorio_so_para_conector_do_claude_pendente(init, servico, repete):
    s = delegada.interpretar("claude", 0, init + _precisa(servico), "", conf=CONF)
    assert (s.estado, s.transitorio) == ("esperando", repete)


from tests.fakes import FakeOrca
from vard.oficina import Repo

REPOS = {"demo-app": Repo("demo-app", "X:/dev/demo-app", "", "main", ())}


def _f(nome):
    return (Path(__file__).parent / "fixtures" / "delegada" / nome).read_text(encoding="utf-8")


def test_executar_sem_login_abre_aba_no_orca(ambiente):
    orca = FakeOrca()
    t, _ = delegada.registrar("claude", "x", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=lambda c, to: (1, _f("claude-sem-login.jsonl"), ""),
                          orca=orca, repos=REPOS)
    assert (u.estado, u.bloqueio, u.terminal) == ("esperando", "login", "term_1")
    _, wt, comando, titulo, shell = next(c for c in orca.chamadas if c[0] == "criar_terminal")
    assert (wt, titulo, shell) == ("path:X:/dev/demo-app", f"Vard #{t.n} login Claude", "powershell.exe")
    assert comando.startswith("Set-Location -LiteralPath '") and comando.endswith("'; claude; exit")
    assert str(delegada.PASTA_NEUTRA / "claude") in comando


def test_executar_sem_login_sem_login_repo_nao_abre_aba(ambiente):
    conf = dataclasses.replace(ambiente, login_repo="")
    orca = FakeOrca()
    t, _ = delegada.registrar("claude", "x", conf=conf, agora=_agora())
    u = delegada.executar(t.n, conf=conf, rodar_fn=lambda c, to: (1, _f("claude-sem-login.jsonl"), ""),
                          orca=orca, repos=REPOS)
    assert (u.estado, u.bloqueio, u.terminal) == ("esperando", "login", "")
    assert not any(c[0] == "criar_terminal" for c in orca.chamadas)


def test_executar_sem_login_com_repo_inexistente_nao_abre_aba(ambiente):
    conf = dataclasses.replace(ambiente, login_repo="sumiu")
    orca = FakeOrca()
    t, _ = delegada.registrar("claude", "x", conf=conf, agora=_agora())
    u = delegada.executar(t.n, conf=conf, rodar_fn=lambda c, to: (1, _f("claude-sem-login.jsonl"), ""),
                          orca=orca, repos=REPOS)
    assert (u.estado, u.bloqueio, u.terminal) == ("esperando", "login", "")
    assert not any(c[0] == "criar_terminal" for c in orca.chamadas)


def test_executar_sem_login_e_orca_fora_fica_esperando_sem_aba(ambiente):
    t, _ = delegada.registrar("codex", "x", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=lambda c, to: (1, _f("codex-sem-login.jsonl"), ""),
                          orca=FakeOrca(falha="criar_terminal"), repos=REPOS)
    assert (u.estado, u.bloqueio, u.terminal) == ("esperando", "login", "")


def test_conector_nao_abre_aba(ambiente):
    orca = FakeOrca()
    t, _ = delegada.registrar("codex", "issues do Linear?", conf=ambiente, agora=_agora())
    delegada.executar(t.n, conf=ambiente, rodar_fn=lambda c, to: (0, _f("codex-reautenticar.jsonl"), ""),
                      orca=orca, repos=REPOS)
    assert not any(c[0] == "criar_terminal" for c in orca.chamadas)


def test_login_descartada_no_meio_fecha_a_aba(ambiente):
    orca = FakeOrca()
    t, _ = delegada.registrar("claude", "x", conf=ambiente, agora=_agora())

    def rodar(c, to):
        tarefas.atualizar(t.n, estado="descartada")
        return 1, _f("claude-sem-login.jsonl"), ""
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=rodar, orca=orca, repos=REPOS)
    assert u.estado == "descartada" and ("fechar_terminal", "term_1") in orca.chamadas


def _esperando_login(tentativas=0):
    t = tarefas.nova("delegada", "", "x", agente="claude")
    return tarefas.atualizar(t.n, estado="esperando", bloqueio="login", terminal="term_1", avisado="esperando",
                             tentativas=tentativas)


def test_observar_login_relanca_uma_vez(loja, monkeypatch):
    lancados = []
    monkeypatch.setattr("vard.trabalhador.lancar", lambda n, **k: lancados.append(n))
    t = _esperando_login()
    assert delegada.observar_login(t, orca=FakeOrca(exit=False)).estado == "esperando" and lancados == []
    u = delegada.observar_login(t, orca=FakeOrca(exit=True))
    assert (u.estado, u.terminal, u.tentativas, u.avisado, u.bloqueio) == ("preparando", "", 1, "", "")
    assert lancados == [t.n]


def test_observar_login_segunda_vez_falha(loja, monkeypatch):
    monkeypatch.setattr("vard.trabalhador.lancar", lambda n, **k: pytest.fail("não deveria relançar"))
    u = delegada.observar_login(_esperando_login(tentativas=1), orca=FakeOrca(exit=True))
    assert (u.estado, u.resumo) == ("falhou", "continuei sem conseguir entrar no Claude")


def test_observar_login_cas_nao_relanca_se_o_usuario_descartou(loja, monkeypatch):
    lancados = []
    monkeypatch.setattr("vard.trabalhador.lancar", lambda n, **k: lancados.append(n))
    vista = _esperando_login()
    tarefas.atualizar(vista.n, estado="descartada")
    assert delegada.observar_login(vista, orca=FakeOrca(exit=True)).estado == "descartada" and lancados == []


# --- retenção de 30 dias ---

def _velha(loja, dias, *, ferramenta="delegada", estado="terminou", nome_arquivo=None, conteudo="resposta"):
    t = tarefas.nova(ferramenta, "", "x", agente="claude" if ferramenta == "delegada" else "")
    res = tarefas.arquivo_resultado(t.n)
    res.write_text(conteudo, encoding="utf-8")
    alvo = res if nome_arquivo is None else res.parent / nome_arquivo
    alvo.write_text(conteudo, encoding="utf-8")
    tarefas.atualizar(t.n, estado=estado, resultado=str(alvo), resumo="um resumo")
    dados = json.loads(loja.read_text(encoding="utf-8"))
    for d in dados["tarefas"]:
        if d["n"] == t.n:
            d["atualizada_em"] = (_agora() - dt.timedelta(days=dias)).isoformat()
    loja.write_text(json.dumps(dados), encoding="utf-8")
    return t.n, alvo


def test_limpar_antigas_apaga_depois_de_30_dias(loja):
    n, arquivo = _velha(loja, 31)
    assert delegada.limpar_antigas(agora=_agora(), conf=CONF) == 1
    t = tarefas.obter(n)
    assert not arquivo.exists() and (t.resultado, t.resumo) == ("", "")


def test_limpar_antigas_29_dias_intacta(loja):
    n, arquivo = _velha(loja, 29)
    assert delegada.limpar_antigas(agora=_agora(), conf=CONF) == 0
    assert arquivo.exists() and tarefas.obter(n).resumo == "um resumo"


def test_limpar_antigas_ignora_outras_ferramentas(loja):
    n, arquivo = _velha(loja, 31, ferramenta="agente_remoto")
    assert delegada.limpar_antigas(agora=_agora(), conf=CONF) == 0
    assert arquivo.exists() and tarefas.obter(n).resumo == "um resumo"


def test_limpar_antigas_ignora_viva(loja):
    n, arquivo = _velha(loja, 31, estado="esperando")
    assert delegada.limpar_antigas(agora=_agora(), conf=CONF) == 0
    assert arquivo.exists()


def test_limpar_antigas_nao_apaga_arquivo_de_outro_nome(loja):
    n, arquivo = _velha(loja, 31, nome_arquivo="alheio.md")
    assert delegada.limpar_antigas(agora=_agora(), conf=CONF) == 1
    t = tarefas.obter(n)
    assert arquivo.exists() and (t.resultado, t.resumo) == ("", "")


# --- limite de sessão do Claude ---

def test_limite_de_sessao_do_claude_conta_como_sem_cota_com_a_hora():
    s = delegada.interpretar("claude", 1, _f("claude-sem-cota.jsonl"), "", conf=CONF)
    assert s.limite is True and s.estado == "falhou"
    assert s.motivo == "o Claude está sem cota agora (volta às 12:50pm)"


@pytest.mark.parametrize("msg", ["You've hit your weekly limit · resets 9am", "You have hit your Opus limit"])
def test_outras_mensagens_de_limite_do_claude(msg):
    out = json.dumps({"type": "result", "is_error": True, "result": msg}) + "\n"
    s = delegada.interpretar("claude", 1, out, "", conf=CONF)
    assert s.limite is True and s.motivo.startswith("o Claude está sem cota agora")


def test_limite_de_sessao_entra_a_reserva_agy(ambiente):
    chamadas = []

    def rodar(cmd, to):
        agente = "claude" if "claude" in Path(cmd.args[0]).name else "agy"
        chamadas.append(agente)
        if agente == "claude":
            return 1, _f("claude-sem-cota.jsonl"), ""
        return 0, json.dumps({"status": "SUCCESS", "response": "RESUMO: Ulan Bator."}), ""
    t, _ = delegada.registrar("", "qual a capital da Mongólia?", conf=ambiente, agora=_agora())
    u = delegada.executar(t.n, conf=ambiente, rodar_fn=rodar)
    assert chamadas == ["claude", "agy"] and (u.estado, u.agente) == ("terminou", "agy")


# --- onda final ---

def test_repetir_zera_tentativas_e_o_login_relanca_de_novo(loja, monkeypatch):
    lancados = []
    monkeypatch.setattr("vard.trabalhador.lancar", lambda n, **k: lancados.append(n))
    t = tarefas.nova("delegada", "", "x", agente="claude")
    tarefas.atualizar(t.n, estado="falhou", tentativas=1)
    delegada.repetir(t.n)
    assert tarefas.obter(t.n).tentativas == 0 and lancados == [t.n]
    tarefas.atualizar(t.n, estado="esperando", bloqueio="login", terminal="term_1")
    u = delegada.observar_login(tarefas.obter(t.n), orca=FakeOrca(exit=True))
    assert u.estado == "preparando" and lancados == [t.n, t.n]


def test_rodar_tira_as_marcas_da_sessao_do_claude_code(tmp_path, monkeypatch):
    for v in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT"):
        monkeypatch.setenv(v, "1")
    visto = {}

    def popen(args, **kw):
        visto.update(kw)
        return FakeProc(out="ok")

    cmd = delegada.Comando(["x.exe"], None, str(tmp_path), delegada.SEM_ENV, "")
    delegada.rodar(cmd, 5, popen=popen)
    assert not {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT"} & set(visto["env"])


@pytest.mark.parametrize("pergunta,esperado", [
    ("veja no Linear e no Figma", "codex"),            # o Codex cobre os dois
    ("veja no Linear e no Notion", "claude"),
    ("veja no Notion e no Figma", "claude"),           # ninguém cobre os dois: o primeiro citado
    ("veja no Figma e no Notion", "codex"),
])
def test_escolher_pelos_servicos_citados_na_pergunta(pergunta, esperado):
    assert delegada.escolher("", pergunta, CONF) == (esperado, False)


def test_servicos_citados_na_ordem_da_pergunta():
    assert delegada.servicos_citados("figma antes e depois o Linear", CONF) == ["figma", "linear"]


def test_preparar_pasta_remove_juncao_sem_seguir_o_alvo(tmp_path):
    import subprocess as sp
    raiz = tmp_path / "delegada"
    p = delegada.preparar_pasta("claude", raiz=raiz)
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    (alvo / "importante.txt").write_text("fica", encoding="utf-8")
    r = sp.run(["cmd", "/c", "mklink", "/J", str(p / "atalho"), str(alvo)], capture_output=True)
    if r.returncode != 0:
        pytest.skip("sem permissão para criar a junção")
    delegada.preparar_pasta("claude", raiz=raiz)
    assert not (p / "atalho").exists() and (alvo / "importante.txt").read_text(encoding="utf-8") == "fica"


def test_consultar_prepara_a_pasta_dentro_da_trava(conf_exes, tmp_path, monkeypatch):
    eventos = []

    @contextlib.contextmanager
    def trava(agente, espera):
        eventos.append("entrou")
        yield
        eventos.append("saiu")

    real = delegada.preparar_pasta

    def prepara(*a, **k):
        eventos.append("preparou")
        return real(*a, **k)

    monkeypatch.setattr(delegada, "_trava_agente", trava)
    monkeypatch.setattr(delegada, "preparar_pasta", prepara)
    s = delegada.consultar("claude", "x", conf_exes, rodar_fn=lambda c, to: (0, json.dumps(
        {"type": "result", "is_error": False, "result": "RESUMO: ok"}) + "\n", ""), raiz=tmp_path)
    assert eventos == ["entrou", "preparou", "saiu"] and s.estado == "terminou"


def test_consultar_erro_ao_preparar_a_pasta_falha_com_frase(conf_exes, tmp_path, monkeypatch):
    def prepara(*a, **k):
        raise PermissionError("negado")
    monkeypatch.setattr(delegada, "preparar_pasta", prepara)
    monkeypatch.setattr(delegada, "PASTA_TRAVAS", tmp_path / "travas")
    s = delegada.consultar("claude", "x", conf_exes, rodar_fn=lambda c, to: pytest.fail("não roda"), raiz=tmp_path)
    assert (s.estado, s.motivo) == ("falhou", "não consegui preparar a pasta da consulta")


def test_link_do_conector_so_https():
    http = _f("codex-reautenticar.jsonl").replace("https://chatgpt.com/plugins", "http://chatgpt.com/plugins")
    assert delegada.interpretar("codex", 0, http, "", conf=CONF).link == ""
    js = _f("codex-reautenticar.jsonl").replace("https://chatgpt.com/plugins", "javascript:alert(1)//")
    assert delegada.interpretar("codex", 0, js, "", conf=CONF).link == ""
