import json
import os
import tempfile

import pytest

import preflight
from vard import delegada


def test_porta_em_loopback_passa():
    ok, d = preflight.avaliar_portas([(1234, "127.0.0.1"), (8000, "127.0.0.1"), (4700, "::1"), (5000, "0.0.0.0")])
    assert ok and "EXPOSTA" not in d


def test_porta_nossa_em_todas_as_interfaces_falha_e_lista():
    ok, d = preflight.avaliar_portas([(8000, "0.0.0.0"), (4700, "127.0.0.1")])
    assert not ok and "0.0.0.0:8000" in d and "EXPOSTA" in d


def test_lmstudio_na_rede_e_so_aviso():
    ok, d = preflight.avaliar_portas([(1234, "0.0.0.0"), (8000, "127.0.0.1"), (4700, "127.0.0.1")])
    assert ok and "AVISO" in d and "0.0.0.0:1234" in d and "EXPOSTA" not in d


def test_porta_em_ipv6_aberto_falha():
    ok, _ = preflight.avaliar_portas([(4700, "::")])
    assert not ok


def test_avaliar_token():
    assert preflight.avaliar_token(401) == (True, "401 sem token")
    ok, d = preflight.avaliar_token(200)
    assert not ok and "sem token" in d
    assert not preflight.avaliar_token(500)[0]


def test_avaliar_status_ciclo():
    ok, d = preflight.avaliar_status_ciclo({"modo": "ligado", "openjarvis": 1, "ponte": 2, "bandeja": 3, "lmstudio_modelos": 1, "variaveis_ok": True})
    assert ok
    ok, d = preflight.avaliar_status_ciclo({"modo": "jogo", "openjarvis": None, "ponte": None, "bandeja": 3, "lmstudio_modelos": 0, "variaveis_ok": True})
    assert not ok and "jogo" in d
    ok, d = preflight.avaliar_status_ciclo({"modo": "ligado", "openjarvis": 1, "ponte": 2, "bandeja": None, "lmstudio_modelos": 1, "variaveis_ok": False})
    assert not ok and "variáveis" in d


def test_avaliar_canal_telegram():
    assert preflight.avaliar_canal_telegram(True, "123")[0]
    ok, d = preflight.avaliar_canal_telegram(True, "")
    assert not ok and "allowed_chat_ids" in d
    ok, d = preflight.avaliar_canal_telegram(False, "")
    assert ok and "AVISO" in d


def test_avaliar_origin():
    assert preflight.avaliar_origin(403)[0]
    ok, d = preflight.avaliar_origin(422)
    assert not ok and "sumiu" in d
    assert not preflight.avaliar_origin(200)[0]


def test_avaliar_sonda():
    assert preflight.avaliar_sonda("1000\n", 900)[0]
    ok, d = preflight.avaliar_sonda("800", 900)
    assert not ok and "antigo" in d
    assert not preflight.avaliar_sonda(None, 900)[0]
    assert not preflight.avaliar_sonda("lixo", 900)[0]


def test_avaliar_transcricao():
    assert preflight.avaliar_transcricao({"text": "Preflight.", "language": "pt"})[0]
    ok, d = preflight.avaliar_transcricao({"text": "pré-voo", "language": "pt"})
    assert not ok and "preflight" in d
    assert not preflight.avaliar_transcricao({})[0]


def test_hora_rapida_exige_hora_e_menos_de_4s():
    assert preflight.avaliar_hora_rapida("Agora são 14:32, senhor.", 1.5)[0]
    assert not preflight.avaliar_hora_rapida("Agora são 14:32.", 5.0)[0]
    assert not preflight.avaliar_hora_rapida("Não sei dizer.", 1.0)[0]


def test_avaliar_repos_orca_ignora_caixa_e_barra():
    ok, _ = preflight.avaliar_repos_orca({"demo": "X:/DEV/Demo-Finance"}, ["X:\\DEV\\demo-finance\\"])
    assert ok
    ok, d = preflight.avaliar_repos_orca({"demo": "X:/DEV/Demo-Finance", "x": "X:/DEV/x"}, ["X:/DEV/Demo-Finance"])
    assert not ok and "x" in d and "orca repo add" in d


def test_avaliar_trava_vigia(tmp_path):
    assert preflight.avaliar_trava_vigia(None)[0]
    fd = os.open(tmp_path / "x.lock", os.O_RDWR | os.O_CREAT)
    ok, d = preflight.avaliar_trava_vigia(fd)
    assert not ok and "ninguém vigiando" in d


def test_avaliar_paineis():
    assert preflight.avaliar_paineis({})[1].startswith("AVISO")
    assert preflight.avaliar_paineis({"exemplo": {"url": "https://p", "token": ""}})[1].startswith("AVISO")
    assert preflight.avaliar_paineis({"exemplo": {"url": "https://p", "token": "t"}}) is None
    assert preflight.avaliar_paineis({})[0] is True       # aviso, não falha


def test_ai_memory_sem_token_e_aviso():
    ok, d = preflight.avaliar_ai_memory("http://h/mcp", "")
    assert ok and d.startswith("AVISO")


def test_ai_memory_com_token_lista_ferramentas():
    fs = lambda: [{"name": "memory_query"}, {"name": "memory_write_page"}]
    assert preflight.avaliar_ai_memory("http://h/mcp", "t", listar=fs)[0] is True
    assert preflight.avaliar_ai_memory("http://h/mcp", "t", listar=lambda: [{"name": "x"}])[0] is False


def test_ai_memory_fora_do_ar_falha_sem_vazar():
    def cai():
        raise preflight.ErroMCP("token recusado (401)")
    ok, d = preflight.avaliar_ai_memory("http://h/mcp", "SEGREDO", listar=cai)
    assert not ok and "401" in d and "SEGREDO" not in d


def test_avaliar_digest():
    bom = {"enabled": False, "persona": "vard", "world": {"sources": ["news_rss"]}}
    assert preflight.avaliar_digest(bom, True)[0]
    ok, d = preflight.avaliar_digest({**bom, "enabled": True}, False)
    assert not ok and "enabled" in d and "persona" in d


def test_avaliar_feed():
    assert preflight.avaliar_feed(200, '<?xml version="1.0"?><rss version="2.0">')
    assert preflight.avaliar_feed(200, "<feed xmlns='http://www.w3.org/2005/Atom'>")
    assert not preflight.avaliar_feed(200, "<html>bloqueado</html>")
    assert not preflight.avaliar_feed(404, "<rss>")


def test_google_sem_conexao_e_so_aviso(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    ok, d = preflight.google_conectado()
    assert ok and d.startswith("AVISO")


def test_avaliar_contexto():
    assert preflight.avaliar_contexto(None)[1].startswith("AVISO")
    assert preflight.avaliar_contexto(6000)[0] and not preflight.avaliar_contexto(9500)[0]


def test_avaliar_transcricao_ignora_hifen_e_espaco():
    assert preflight.avaliar_transcricao({"text": "Pre-flight."})[0]
    assert preflight.avaliar_transcricao({"text": "pre flight"})[0]


def test_avaliar_paineis_separa_url_de_token():
    assert "exemplo: falta token" in preflight.avaliar_paineis({"exemplo": {"url": "https://p"}})[1]
    assert "exemplo: falta url" in preflight.avaliar_paineis({"exemplo": {"token": "t"}})[1]
    assert "falta url e token" in preflight.avaliar_paineis({"exemplo": {}})[1]


# ---------------------------------------------------------------- modo reunião (R1 a R7)

REFERENCIA_REUNIAO = "A reunião de hoje é sobre o orçamento do projeto Demo. Vamos decidir o prazo da entrega."


def test_avaliar_servico_reuniao():
    assert preflight.avaliar_servico_reuniao(200, 421, 403)[0]
    ok, d = preflight.avaliar_servico_reuniao(200, 200, 403)
    assert not ok and "Host" in d
    ok, d = preflight.avaliar_servico_reuniao(200, 421, 200)
    assert not ok and "Origin" in d
    assert not preflight.avaliar_servico_reuniao(500, 421, 403)[0]


def test_avaliar_transcricao_reuniao_aceita_a_trilha_outros():
    falas = [{"trilha": "sistema", "texto": "reunião iniciada"},
             {"trilha": "outros", "texto": "A reunião de hoje é sobre o orçamento do projeto Demo."},
             {"trilha": "outros", "texto": "Vamos decidir o prazo da entrega."}]
    ok, d = preflight.avaliar_transcricao_reuniao(falas, REFERENCIA_REUNIAO)
    assert ok and "1,00" in d


def test_avaliar_transcricao_reuniao_recusa_trilha_errada_ou_texto_diferente():
    so_eu = [{"trilha": "eu", "texto": REFERENCIA_REUNIAO}]
    ok, d = preflight.avaliar_transcricao_reuniao(so_eu, REFERENCIA_REUNIAO)
    assert not ok and "outros" in d
    ok, d = preflight.avaliar_transcricao_reuniao([{"trilha": "outros", "texto": "bom dia, tudo bem?"}], REFERENCIA_REUNIAO)
    assert not ok and "similaridade" in d
    assert not preflight.avaliar_transcricao_reuniao([], REFERENCIA_REUNIAO)[0]


def test_avaliar_latencia_reuniao():
    assert preflight.avaliar_latencia_reuniao("olá", 1.1)[0]
    ok, d = preflight.avaliar_latencia_reuniao("olá", 5.2)
    assert not ok and "5,2" in d
    assert not preflight.avaliar_latencia_reuniao("", 1.0)[0]


ATA_BOA = "# Ata\n\n## Resumo\nx\n\n## Decisões\n- a\n\n## Pendências\n| a | b | c |\n\n## Pontos abertos\n- n\n\n## Próximos passos\n- s\n"


def test_avaliar_ata_reuniao_ok_e_aviso_de_lentidao():
    ok, d = preflight.avaliar_ata_reuniao(ATA_BOA, b"%PDF-1.7" + b"x" * 20_000, 30.0)
    assert ok and "AVISO" not in d and "5 de 5" in d
    ok, d = preflight.avaliar_ata_reuniao(ATA_BOA, b"%PDF-1.7" + b"x" * 20_000, 200.0)
    assert ok and "AVISO" in d


def test_avaliar_ata_reuniao_falhas():
    ok, d = preflight.avaliar_ata_reuniao(ATA_BOA.replace("## Decisões", "## Outra"), b"%PDF-" + b"x" * 20_000, 10)
    assert not ok and "Decisões" in d
    ok, d = preflight.avaliar_ata_reuniao(ATA_BOA, b"nao e pdf" * 5000, 10)
    assert not ok and "PDF" in d
    ok, d = preflight.avaliar_ata_reuniao(ATA_BOA, b"%PDF-1.7", 10)
    assert not ok and "kB" in d


def test_avaliar_audio_some():
    assert preflight.avaliar_audio_some(False)[0]
    assert not preflight.avaliar_audio_some(True)[0]
    ok, d = preflight.avaliar_audio_some(None)
    assert not ok and "ata" in d


def test_avaliar_diarizacao_reuniao():
    ok, d = preflight.avaliar_diarizacao_reuniao({"offline": True, "telemetria_desligada": True, "diarizacao": {"pronta": True, "modo": "community-1"}})
    assert ok and "AVISO" not in d and "community-1" in d
    ok, d = preflight.avaliar_diarizacao_reuniao({"offline": False, "telemetria_desligada": True, "diarizacao": {"pronta": True, "modo": "community-1"}})
    assert not ok and "HF_HUB_OFFLINE" in d
    ok, d = preflight.avaliar_diarizacao_reuniao({"offline": True, "telemetria_desligada": False, "diarizacao": {"pronta": True, "modo": "community-1"}})
    assert not ok and "PYANNOTE_METRICS_ENABLED" in d
    ok, d = preflight.avaliar_diarizacao_reuniao({"offline": True, "diarizacao": {"pronta": True, "modo": "community-1"}})
    assert not ok and "PYANNOTE_METRICS_ENABLED" in d
    ok, d = preflight.avaliar_diarizacao_reuniao({"offline": True, "telemetria_desligada": True, "diarizacao": {"pronta": False, "motivo": "modelo não baixado"}})
    assert ok and "AVISO" in d and "modelo não baixado" in d
    ok, d = preflight.avaliar_diarizacao_reuniao({"offline": True, "telemetria_desligada": True, "diarizacao": {"pronta": True, "modo": "reserva"}})
    assert ok and "AVISO" in d and "reserva" in d


def test_avaliar_jogo_ordem():
    bom = "function Jogo() {\n  EncerrarReuniao\n  Matar \"voz\"\n  InvocarLms unload\n}"
    assert preflight.avaliar_jogo(bom)[0]
    ok, d = preflight.avaliar_jogo(bom.replace("EncerrarReuniao", "x"))
    assert not ok and "EncerrarReuniao" in d
    ok, d = preflight.avaliar_jogo("function Jogo() {\n  InvocarLms unload\n  EncerrarReuniao\n}")
    assert not ok and "antes" in d
    assert not preflight.avaliar_jogo("")[0]


def test_reuniao_jogo_estrutura_le_o_script_de_verdade(tmp_path, monkeypatch, powershell_isolado):
    executar = preflight.subprocess.run

    def harness(args, **kwargs):
        assert args[:3] == ["powershell", "-NoProfile", "-Command"]
        script = tmp_path / "estrutura.ps1"
        script.write_text(args[3], encoding="utf-8-sig")
        return executar(["powershell", "-NoProfile", "-File", str(script)], **kwargs)

    monkeypatch.setattr(preflight.subprocess, "run", harness)
    ok, d = preflight.reuniao_jogo_estrutura()
    assert ok, d


@pytest.mark.pc_real
def test_reuniao_wav_a_16k_mono():
    import io, wave
    if not preflight.WAV_REUNIAO.exists():
        pytest.skip("sem o áudio real da reunião em <pasta_dados>/preflight/preflight-reuniao.wav")
    pcm = preflight.wav_16k_mono(preflight.WAV_REUNIAO.read_bytes())
    with wave.open(io.BytesIO(pcm)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert 7.5 < w.getnframes() / 16000 < 8.3


def test_normalizar_para_wer():
    assert preflight.normalizar_para_wer("Olá, Mundo! Tudo-bem?") == "olá mundo tudo bem"


class _Resp:
    def __init__(self, codigo=200, corpo=None):
        self.status_code, self._corpo = codigo, corpo or {}
        self.text = str(self._corpo)

    def json(self):
        return self._corpo


def _simular_4720(monkeypatch, *, encerrar_falha=False, ativa=False):
    import httpx
    chamadas = []
    ativos = preflight.Path(tempfile.mkdtemp(prefix="vard-ativos-teste-"))
    (ativos / "preflight-reuniao.wav").write_bytes(b"RIFF")     # o _tocar_wav é simulado: o conteúdo não importa
    (ativos / "preflight-reuniao.txt").write_text("preflight", encoding="utf-8")
    monkeypatch.setattr(preflight, "WAV_REUNIAO", ativos / "preflight-reuniao.wav")
    monkeypatch.setattr(preflight, "TXT_REUNIAO", ativos / "preflight-reuniao.txt")

    def get(url, **kw):
        return _Resp(200, {"ativa": ativa, "falas": 1})

    def post(url, **kw):
        chamadas.append(url)
        if url.endswith("/encerrar") and encerrar_falha:
            raise httpx.ConnectError("caiu")
        if url.endswith("/iniciar"):
            return _Resp(200, {"pasta": "2026-10-13_0999"})
        return _Resp(200, {"pasta": "2026-10-13_0999"})

    monkeypatch.setattr(preflight.httpx, "get", get)
    monkeypatch.setattr(preflight.httpx, "post", post)
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: type("P", (), {"wait": lambda self, timeout=0: 0})())
    monkeypatch.setattr(preflight.time, "sleep", lambda s: None)
    return chamadas


def test_loopback_falha_explicita_se_o_encerramento_falha(monkeypatch):
    _simular_4720(monkeypatch, encerrar_falha=True)
    ok, d = preflight.reuniao_loopback_transcreve()
    assert not ok and "ficou ativa" in d and "4720" in d


def test_loopback_nao_mascara_a_excecao_original(monkeypatch):
    _simular_4720(monkeypatch, encerrar_falha=True)
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(OSError("sem som")))
    ok, d = preflight.reuniao_loopback_transcreve()
    assert not ok and "sem som" in d and "ficou ativa" in d


def test_loopback_com_reuniao_ativa_vira_aviso_e_nao_inicia(monkeypatch):
    chamadas = _simular_4720(monkeypatch, ativa=True)
    ok, d = preflight.reuniao_loopback_transcreve()
    assert ok and "AVISO" in d and not chamadas


def test_servico_reuniao_prova_origin_sem_efeito_colateral(monkeypatch):
    chamadas = []
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: {"ativa": False})
    monkeypatch.setattr(preflight.httpx, "get", lambda url, **kw: _Resp(421 if kw.get("headers") else 200))
    monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: chamadas.append(url) or _Resp(403))
    assert preflight.reuniao_servico_no_ar()[0]
    assert chamadas == [f"{preflight.REUNIAO}/falante"]


def test_wav_16k_recusa_largura_diferente_de_16_bits():
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(8000); w.writeframes(b"\x80" * 80)
    import pytest
    with pytest.raises(ValueError, match="16 bits"):
        preflight.wav_16k_mono(buf.getvalue())


def test_loopback_ctrl_c_ainda_encerra_a_reuniao_de_teste(monkeypatch):
    import pytest
    chamadas = _simular_4720(monkeypatch)
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        preflight.executar_loopback()
    assert chamadas[-1].endswith("/encerrar")


def test_loopback_apaga_a_pasta_mesmo_com_excecao_no_corpo(monkeypatch):
    import pytest
    apagadas = []
    _simular_4720(monkeypatch)
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(OSError("sem som")))
    monkeypatch.setattr(preflight.reuniao_mod, "caminho_pasta", lambda n: preflight.Path("X") / n)
    monkeypatch.setattr(preflight.reuniao_mod, "carregar_falas", lambda p: [])
    monkeypatch.setattr(preflight.shutil, "rmtree", lambda p, **kw: apagadas.append(str(p)))
    with pytest.raises(OSError, match="sem som"):
        preflight.executar_loopback()
    assert len(apagadas) == 1 and apagadas[0].endswith("2026-10-13_0999")


def test_loopback_com_apagar_falso_deixa_o_nome_em_loopback(monkeypatch):
    import pytest
    _simular_4720(monkeypatch)
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(OSError("sem som")))
    monkeypatch.setattr(preflight.reuniao_mod, "caminho_pasta", lambda n: preflight.Path("X") / n)
    monkeypatch.setattr(preflight.reuniao_mod, "carregar_falas", lambda p: [])
    with pytest.raises(OSError):
        preflight.executar_loopback(apagar=False)
    assert preflight.LOOPBACK["pasta"] == "2026-10-13_0999"


def test_ctrl_c_com_encerramento_falhando_avisa_e_propaga(monkeypatch, capsys):
    import pytest
    _simular_4720(monkeypatch, encerrar_falha=True)
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        preflight.executar_loopback()
    assert "ficou ativa" in capsys.readouterr().out


def test_encerrar_reuniao_de_teste_classifica_as_respostas(monkeypatch):
    def com(codigo, corpo):
        monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: _Resp(codigo, corpo))
        return preflight.encerrar_reuniao_de_teste("http://x/encerrar")
    assert com(200, {"pasta": "p"}) == ("ok", "p")
    assert com(409, {"ok": False, "erro": "inativa"})[0] == "ok"
    assert com(409, {"ok": False, "erro": "salvar", "pasta": "p"}) == ("salvar", "p")
    assert com(502, {})[0] == "ativa"


def test_loopback_409_salvar_mantem_a_pasta_e_falha(monkeypatch):
    _simular_4720(monkeypatch)
    apagadas = []
    monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: _Resp(409, {"erro": "salvar", "pasta": "2026-10-13_0999"})
                        if url.endswith("/encerrar") else _Resp(200, {"pasta": "2026-10-13_0999"}))
    monkeypatch.setattr(preflight.shutil, "rmtree", lambda p, **kw: apagadas.append(p))
    ok, d = preflight.reuniao_loopback_transcreve()
    assert not ok and "sem salvar" in d and not apagadas


def test_loopback_pasta_vem_do_status_se_o_json_falha(monkeypatch):
    import pytest

    class Quebrada(_Resp):
        def json(self):
            raise ValueError("sem json")

    _simular_4720(monkeypatch)
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: {"ativa": False, "pasta": "2026-10-13_0888", "falas": 1})
    monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: Quebrada(200) if url.endswith("/iniciar") else _Resp(200, {"pasta": "2026-10-13_0888"}))
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        preflight.executar_loopback(apagar=False)
    assert preflight.LOOPBACK["pasta"] == "2026-10-13_0888"


def test_loopback_pasta_null_no_iniciar_cai_no_status(monkeypatch):
    import pytest
    _simular_4720(monkeypatch)
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: {"ativa": False, "pasta": "2026-10-13_0444", "falas": 1})
    monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: _Resp(200, {"pasta": None}) if url.endswith("/iniciar")
                        else _Resp(409, {"erro": "salvar"}))
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(RuntimeError, match="sem salvar"):
        preflight.executar_loopback(apagar=False)
    assert preflight.LOOPBACK["pasta"] == "2026-10-13_0444" and preflight.LOOPBACK["salvar_falhou"]
    preflight.LOOPBACK.update(pasta=None, salvar_falhou=False)


def test_ctrl_c_com_409_salvar_avisa_pasta_mantida(monkeypatch, capsys):
    import pytest
    _simular_4720(monkeypatch)
    monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: _Resp(409, {"erro": "salvar"})
                        if url.endswith("/encerrar") else _Resp(200, {"pasta": "2026-10-13_0999"}))
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        preflight.executar_loopback(apagar=False)
    assert "pasta de teste mantida" in capsys.readouterr().out and preflight.LOOPBACK["salvar_falhou"]
    preflight.LOOPBACK.update(pasta=None, salvar_falhou=False)


def test_avaliar_mcp_list():
    saida = ("claude.ai Linear: https://mcp.linear.app/mcp - ✔ Connected\n"
             "claude.ai Notion: https://mcp.notion.com/mcp - ! Needs authentication\n"
             "ai-memory: http://memoria.exemplo.com/mcp (HTTP) - ✔ Connected\n")
    assert preflight.avaliar_mcp_list(saida) == (True, "Linear conectado; precisam de autorização: Notion")
    ok, det = preflight.avaliar_mcp_list("claude.ai Linear: x - ! Needs authentication\n")
    assert ok and det.startswith("AVISO")


def test_avaliar_mcp_list_not_connected_nao_conta():
    for linha in ("claude.ai Linear: x - ✗ Not connected\n", "claude.ai Linear: x - not connected\n"):
        ok, det = preflight.avaliar_mcp_list(linha)
        assert ok and det.startswith("AVISO")


def test_avaliar_respostas_delegada():
    S = delegada.Saida
    r = {"claude": S("terminou", texto="ok"), "codex": S("terminou", texto="ok"), "agy": S("esperando", bloqueio="login"),
         "opencode": S("falhou", motivo="o OpenCode não respondeu nada")}
    ok, det = preflight.avaliar_respostas_delegada(r)
    assert not ok and "opencode: o OpenCode não respondeu nada" in det
    r["opencode"] = S("terminou", texto="ok")
    ok, det = preflight.avaliar_respostas_delegada(r)
    assert ok and det == "AVISO agy sem login"
    del r["codex"]
    assert preflight.avaliar_respostas_delegada(r)[0] is False
    todos = {a: S("terminou", texto="ok") for a in delegada.AGENTES}
    assert preflight.avaliar_respostas_delegada(todos) == (True, "os 4 responderam")


# ---------------------------------------------------------------- integrações opcionais sem configuração


def test_agente_remoto_sem_config_e_aviso():
    ok, d = preflight.agente_remoto_acessivel()
    assert ok and d.startswith("AVISO") and "não configurado" in d


def test_omniroute_sem_url_e_aviso():
    ok, d = preflight.omniroute_responde()
    assert ok and d.startswith("AVISO") and "OmniRouter" in d


def test_ativos_de_reuniao_ausentes_sao_aviso(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "PASTA_ATIVOS", tmp_path)
    monkeypatch.setattr(preflight, "WAV_REUNIAO", tmp_path / "preflight-reuniao.wav")
    monkeypatch.setattr(preflight, "TXT_REUNIAO", tmp_path / "preflight-reuniao.txt")
    ok, d = preflight.reuniao_loopback_transcreve()
    assert ok and d.startswith("AVISO") and "checagem pulada" in d and str(tmp_path) in d
    ok, d = preflight.reuniao_latencia()
    assert ok and d.startswith("AVISO") and "checagem pulada" in d


def test_home_openjarvis_vem_do_instalacao_e_env_sobrepoe(tmp_path, monkeypatch):
    arq = tmp_path / "instalacao.json"
    arq.write_text(json.dumps({"openjarvis_home": "X:/DEV/oj-home"}), encoding="utf-8")
    monkeypatch.setenv("VARD_INSTALACAO", str(arq))
    assert preflight._home_openjarvis() == "X:/DEV/oj-home"
    monkeypatch.setenv("OPENJARVIS_HOME", "X:/outro/casa")
    assert preflight._home_openjarvis() == "X:/outro/casa"


def test_home_openjarvis_sem_config_lanca_e_nao_configurado(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_INSTALACAO", str(tmp_path / "nao-existe.json"))
    with pytest.raises(FileNotFoundError):
        preflight._home_openjarvis()
    assert preflight._openjarvis_configurado() is False


def test_patch_oj_vem_do_instalacao(monkeypatch, tmp_path):
    assert preflight._patch_oj() is None   # sem openjarvis_src configurado
    arq = tmp_path / "instalacao.json"
    arq.write_text(json.dumps({"openjarvis_src": "X:/DEV/oj-src"}), encoding="utf-8")
    monkeypatch.setenv("VARD_INSTALACAO", str(arq))
    assert preflight._patch_oj() == preflight.Path("X:/DEV/oj-src/src/openjarvis/system/_channel_kwargs.py")


@pytest.mark.parametrize("fn", [preflight.sintetiza_curto, preflight.telegram_conectado,
                                preflight.allowed_chat_ids_preenchido, preflight.manha_config_viva,
                                preflight.feeds_respondem, preflight.google_conectado,
                                preflight.patch_telegram_aplicado])
def test_checks_de_home_sem_config_sao_aviso(fn, tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_INSTALACAO", str(tmp_path / "instalacao sumido.json"))
    ok, d = fn()
    assert ok and d.startswith("AVISO"), f"{fn.__name__}: {d}"


def test_agente_remoto_com_config_usa_o_remoto(monkeypatch, tmp_path):
    from vard import config
    config.arquivo_config("remoto.toml").parent.mkdir(parents=True, exist_ok=True)
    config.arquivo_config("remoto.toml").write_text(
        '[remoto]\ndestino = "usuario@servidor.exemplo.com"\ncomando = "sudo docker ps"\ncontainer_prefixo = "vard-"\n',
        encoding="utf-8")
    chamado = {}

    class _P:
        returncode = 0
        stdout = "vard-agente\n"
        stderr = ""

    def _run(args, **kw):
        chamado["args"] = args
        return _P()

    monkeypatch.setattr(preflight.subprocess, "run", _run)
    ok, d = preflight.agente_remoto_acessivel()
    assert ok and "vard-agente" in d and "ssh" in " ".join(chamado["args"])


# === T10c: testes do modo --json ===


@pytest.fixture
def checagens_duble(monkeypatch):
    """As checagens reais falam com LM Studio, ponte, CLIs, SSH e scripts do PC de quem roda a suíte.
    Os testes do modo --json só precisam dos nomes: cada checagem vira um dublê que não chama nada."""
    reais = preflight.checagens()
    chamadas = []

    def _duble(nome):
        def _fn():
            chamadas.append(nome)
            return (False, "dublê: sem chamada real")
        return _fn

    monkeypatch.setattr(preflight, "checagens", lambda: [(n, _duble(n)) for n, _fn in reais])
    return chamadas


def test_rodar_como_json_tem_todas_as_checagens_do_texto(checagens_duble):
    """O JSON deve ter exatamente as mesmas checagens (por nome) que o modo texto."""
    resultado = preflight.rodar_como_json()
    nomes_json = {c["nome"] for c in resultado["checagens"]}
    nomes_texto = {nome for nome, _fn in preflight.checagens()}
    assert nomes_json == nomes_texto, f"Diferença: {nomes_texto - nomes_json} | {nomes_json - nomes_texto}"


def test_rodar_como_json_estrutura_correta(checagens_duble):
    """Cada checagem JSON tem grupo, nome, estado válido e frase não vazia."""
    resultado = preflight.rodar_como_json()
    estados_validos = {"ok", "aviso", "falha"}
    for c in resultado["checagens"]:
        assert "grupo" in c and isinstance(c["grupo"], str) and len(c["grupo"]) > 0
        assert "nome" in c and isinstance(c["nome"], str) and len(c["nome"]) > 0
        assert c["estado"] in estados_validos, f"Estado inválido: {c['estado']} em {c['nome']}"
        assert "frase" in c and isinstance(c["frase"], str)
    assert "relatorio" in resultado and isinstance(resultado["relatorio"], str)
    assert "duracao_ms" in resultado and isinstance(resultado["duracao_ms"], int)


def test_rodar_como_json_integracao_desligada_vira_aviso_ou_falha(checagens_duble):
    """Integração desligada (ex: OpenJarvis fora) vira aviso ou falha, nunca ok falso."""
    resultado = preflight.rodar_como_json()
    # Pelo menos uma checagem de integração deve existir
    integracoes = [c for c in resultado["checagens"] if c["grupo"] == "Integração"]
    assert len(integracoes) > 0, "Deve haver checagens de Integração"
    assert all(c["estado"] != "ok" for c in integracoes)
    assert checagens_duble, "o dublê deve ter sido usado no lugar das checagens reais"


def test_sanitizar_remove_segredo_sintetico():
    """Segredo sintético numa exceção não aparece na saída sanitizada."""
    segredo = "sk-" + "a" * 32
    texto = f"Erro: token={segredo} vazou"
    limpo = preflight._sanitizar(texto)
    assert segredo not in limpo
    assert "***REDACTED***" in limpo or "token=" in limpo.lower()


def test_sanitizar_remove_caminho_pessoal():
    """Caminho pessoal Windows é substituído por placeholder."""
    usuario = "usuario-teste"
    texto = f"Arquivo em X:\\Users\\{usuario}\\.env não encontrado"
    limpo = preflight._sanitizar(texto)
    assert usuario not in limpo.lower() or "***USER***" in limpo


def test_main_json_flag_produz_json_valido(capsys, monkeypatch, checagens_duble):
    """main() com --json produz JSON válido no stdout."""
    import sys
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])
    codigo = preflight.main()
    capturado = capsys.readouterr()
    import json as _json
    dados = _json.loads(capturado.out.strip())
    assert "checagens" in dados
    assert isinstance(dados["checagens"], list)
    assert codigo in (0, 1)  # 0 se tudo ok, 1 se alguma falha
