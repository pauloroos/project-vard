import datetime as dt
import json
import time

import numpy as np

from vard_reuniao import sessao as ses
from vard_reuniao.config import Conf


class CapturaFalsa:
    def __init__(self, ao_bloco):
        self.ao_bloco, self.aberta = ao_bloco, False
        self.dispositivos = type("D", (), {"como_dict": lambda s: {"eu": "Mic", "outros": "Fone"}, "eu_id": 1, "outros_id": 2})()

    def abrir(self):
        self.aberta = True

    def fechar(self):
        self.aberta = False
        self.fechou = getattr(self, "fechou", 0) + 1


def prob_energia(j):
    return 1.0 if np.abs(j).mean() > 100 else 0.0


def nova(tmp_path, transcrever, publicados=None, conf=None):
    publicados = publicados if publicados is not None else []
    s = ses.Sessao(conf or Conf(), raiz=tmp_path, transcritor=transcrever, prob=prob_energia,
                   captura_factory=CapturaFalsa, publicar=publicados.append)
    return s, publicados


def fala(amp=3000, dur_s=1.0):
    return np.full(int(16000 * dur_s), amp, dtype=np.int16)


def esperar(cond, s=5.0):
    fim = time.monotonic() + s
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_iniciar_cria_pasta_publica_e_status(tmp_path):
    s, pub = nova(tmp_path, lambda seg: ("x", 0.9))
    r = s.iniciar()
    assert r["ok"] and (tmp_path / r["pasta"] / "reuniao.json").exists()
    assert s.status()["ativa"] is True and s.status()["pasta"] == r["pasta"]
    assert pub[-1]["tipo"] == "reuniao" and pub[-1]["estado"] == "iniciou" and pub[-1]["resumo"] == "Acompanhando a reunião."
    assert s.iniciar() == {"ok": False, "erro": "ja_ativa"}
    s.encerrar()


def test_bloco_vira_fala_na_trilha_certa(tmp_path):
    s, _ = nova(tmp_path, lambda seg: (f"texto {seg.trilha}", 0.9))
    s.iniciar()
    s.ao_bloco("outros", fala(), 10.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 11.0)
    assert esperar(lambda: s.status()["falas"] == 1)
    r = s.encerrar()
    linhas = (tmp_path / r["pasta"] / "transcricao.jsonl").read_text(encoding="utf-8").splitlines()
    f = json.loads(linhas[0])
    assert f["trilha"] == "outros" and f["texto"] == "texto outros" and abs(f["t0"] - 0.0) < 0.1   # relativo ao início


def test_encerramento_por_voz_na_trilha_eu(tmp_path):
    s, pub = nova(tmp_path, lambda seg: ("Vard, encerra a reunião", 0.9) if seg.trilha == "eu" else ("oi", 0.9))
    s.iniciar()
    s.ao_bloco("eu", fala(), 1.0)
    s.ao_bloco("eu", np.zeros(16000, dtype=np.int16), 2.0)
    assert esperar(lambda: pub and pub[-1]["estado"] == "encerrou")
    r = s.status()
    assert r["ativa"] is False


def test_encerramento_na_trilha_outros_nao_encerra(tmp_path):
    s, _ = nova(tmp_path, lambda seg: ("Vard, encerra a reunião", 0.9))
    s.iniciar()
    s.ao_bloco("outros", fala(), 1.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 2.0)
    assert esperar(lambda: s.status()["falas"] == 1)
    assert s.status()["ativa"] is True
    s.encerrar()


def test_eco_descarta_fala_do_eu_repetida(tmp_path):
    s, _ = nova(tmp_path, lambda seg: ("vamos decidir o prazo da entrega", 0.9))
    s.iniciar()
    s.ao_bloco("outros", fala(), 1.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 2.0)
    assert esperar(lambda: s.status()["falas"] == 1)
    s.ao_bloco("eu", fala(), 1.1)
    s.ao_bloco("eu", np.zeros(16000, dtype=np.int16), 2.1)
    r = s.encerrar()
    assert r["falas"] == 1


def test_texto_bloqueado_nao_vira_fala(tmp_path):
    s, _ = nova(tmp_path, lambda seg: ("Legendas pela comunidade", 0.9))
    s.iniciar()
    s.ao_bloco("outros", fala(), 1.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 2.0)
    r = s.encerrar()
    assert r["falas"] == 0


def test_encerrar_fecha_flac_e_grava_fim(tmp_path):
    s, pub = nova(tmp_path, lambda seg: ("x", 0.9))
    r = s.iniciar()
    s.ao_bloco("eu", fala(), 1.0)
    e = s.encerrar()
    d = json.loads((tmp_path / r["pasta"] / "reuniao.json").read_text(encoding="utf-8"))
    assert d["fim"] and d["apagar_audio_em"] and (tmp_path / r["pasta"] / "tmp" / "eu.flac").stat().st_size > 0
    assert e["ok"] and pub[-1]["estado"] == "encerrou" and s.encerrar() == {"ok": False, "erro": "inativa"}


def test_guardar_audio_true_nao_marca_apagar(tmp_path):
    s, _ = nova(tmp_path, lambda seg: ("x", 0.9), conf=Conf(guardar_audio=True))
    r = s.iniciar()
    s.encerrar()
    d = json.loads((tmp_path / r["pasta"] / "reuniao.json").read_text(encoding="utf-8"))
    assert d["guardar_audio"] is True and d["apagar_audio_em"] == ""


def test_verificar_dispositivos_reabre_e_marca(tmp_path, monkeypatch):
    s, _ = nova(tmp_path, lambda seg: ("x", 0.9))
    r = s.iniciar()
    ids = iter([(1, 2), (1, 9)])
    monkeypatch.setattr(s, "_ids_padrao", lambda: next(ids))
    s.verificar_dispositivos()           # iguais: nada
    s.verificar_dispositivos()           # mudou: reabre e marca
    s.encerrar()
    assert "dispositivo trocou" in (tmp_path / r["pasta"] / "transcricao.md").read_text(encoding="utf-8")


def test_eco_fora_da_janela_nao_descarta(tmp_path):
    s, _ = nova(tmp_path, lambda seg: ("vamos decidir o prazo da entrega", 0.9))
    s.iniciar()
    s.ao_bloco("outros", fala(), 1.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 2.0)
    assert esperar(lambda: s.status()["falas"] == 1)
    s.ao_bloco("eu", fala(), 41.0)                      # 40 s depois
    s.ao_bloco("eu", np.zeros(16000, dtype=np.int16), 42.0)
    r = s.encerrar()
    assert r["falas"] == 2


def test_apagar_audio_em_e_fim_mais_24h(tmp_path):
    relogio = [dt.datetime(2026, 10, 13, 9, 0, 0)]
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob_energia,
                   captura_factory=CapturaFalsa, publicar=lambda ev: None, agora=lambda: relogio[0])
    r = s.iniciar()
    relogio[0] = dt.datetime(2026, 10, 13, 10, 0, 0)
    s.encerrar()
    d = json.loads((tmp_path / r["pasta"] / "reuniao.json").read_text(encoding="utf-8"))
    assert d["fim"] == "2026-10-13T10:00:00" and d["apagar_audio_em"] == "2026-10-14T10:00:00"


def test_encerrar_resiste_a_falha_do_gravador(tmp_path, monkeypatch):
    s, pub = nova(tmp_path, lambda seg: ("x", 0.9))
    r = s.iniciar()

    def quebra():
        raise OSError("disco")
    monkeypatch.setattr(s.gravador, "fechar", quebra)
    e = s.encerrar()
    assert e["ok"] is True
    d = json.loads((tmp_path / r["pasta"] / "reuniao.json").read_text(encoding="utf-8"))
    assert d["fim"]
    assert pub[-1]["estado"] == "encerrou"
    assert s.status()["ativa"] is False
    assert s.iniciar()["ok"] is True
    s.encerrar()


def test_iniciar_falha_no_gravador_desfaz_tudo(tmp_path, monkeypatch):
    s, pub = nova(tmp_path, lambda seg: ("x", 0.9))

    def quebra(pasta):
        raise OSError("sem disco")
    monkeypatch.setattr(ses, "Gravador", quebra)
    r = s.iniciar()
    assert r["ok"] is False
    assert list(tmp_path.iterdir()) == []
    assert s.status()["ativa"] is False and pub == []
    monkeypatch.undo()
    assert s.iniciar()["ok"] is True
    s.encerrar()


def test_verificar_dispositivos_factory_que_levanta_mantem_estado(tmp_path, monkeypatch):
    chamadas = []

    def factory(ao_bloco):
        chamadas.append(1)
        if len(chamadas) == 2:
            raise RuntimeError("sem dispositivo")
        return CapturaFalsa(ao_bloco)
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob_energia,
                   captura_factory=factory, publicar=lambda ev: None)
    s.iniciar()
    monkeypatch.setattr(s, "_ids_padrao", lambda: (1, 9))
    s.verificar_dispositivos()                      # falha: não levanta, ids antigos ficam
    assert s._ids == () and s.status()["ativa"] is True
    s.verificar_dispositivos()                      # tenta de novo e funciona
    assert s._ids == (1, 9) and len(chamadas) == 3
    assert s.encerrar()["ok"] is True


def test_verificar_dispositivos_abrir_que_levanta_fecha_a_nova(tmp_path, monkeypatch):
    novas = []

    class Ruim(CapturaFalsa):
        def abrir(self):
            raise RuntimeError("nao abre")

    def factory(ao_bloco):
        c = CapturaFalsa(ao_bloco) if not novas else Ruim(ao_bloco)
        novas.append(c)
        return c
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob_energia,
                   captura_factory=factory, publicar=lambda ev: None)
    s.iniciar()
    monkeypatch.setattr(s, "_ids_padrao", lambda: (1, 9))
    s.verificar_dispositivos()
    assert s._ids == () and s.status()["ativa"] is True
    assert novas[1].aberta is False and novas[1].fechou == 1
    assert s.encerrar()["ok"] is True


def test_troca_de_dispositivo_reseta_vad_e_marca_tempo_relativo(tmp_path, monkeypatch):
    resets = []
    prob = lambda j: 1.0 if np.abs(j).mean() > 100 else 0.0    # noqa: E731
    prob.reset = lambda: resets.append(1)
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob,
                   captura_factory=CapturaFalsa, publicar=lambda ev: None)
    r = s.iniciar()
    s.ao_bloco("eu", fala(), 100.0)                 # primeiro bloco: t relativo 0
    s.ao_bloco("eu", fala(), 105.0)                 # t relativo 5
    monkeypatch.setattr(s, "_ids_padrao", lambda: (1, 9))
    s.verificar_dispositivos()
    assert len(resets) == 1      # prob injetado e compartilhado: um reset
    s.encerrar()
    marcador = [json.loads(x) for x in (tmp_path / r["pasta"] / "transcricao.jsonl").read_text(encoding="utf-8").splitlines()
                if '"sistema"' in x][0]
    assert marcador["t0"] == 5.0


def test_captura_real_fechar_idempotente():
    class PA:
        n = 0

        def terminate(self):
            PA.n += 1

    class Cap:
        def fechar(self):
            pass
    c = ses._CapturaReal.__new__(ses._CapturaReal)
    c.pa, c._cap = PA(), Cap()
    c.fechar()
    c.fechar()
    assert PA.n == 1


def test_ids_voltam_ao_original_depois_da_falha_reabre(tmp_path, monkeypatch):
    chamadas, capturas = [], []

    def factory(ao_bloco):
        chamadas.append(1)
        if len(chamadas) == 2:
            raise RuntimeError("sem dispositivo")
        c = CapturaFalsa(ao_bloco)
        capturas.append(c)
        return c
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob_energia,
                   captura_factory=factory, publicar=lambda ev: None)
    s.iniciar()
    ids = iter([(1, 9), (1, 2)])
    monkeypatch.setattr(s, "_ids_padrao", lambda: next(ids))
    s.verificar_dispositivos()                      # falha na reabertura
    assert s.captura is None
    s.verificar_dispositivos()                      # ids voltaram ao original: ainda assim reabre
    assert s.captura is not None and s.captura.aberta is True and len(chamadas) == 3
    assert s.encerrar()["ok"] is True


def test_iniciar_distingue_erro(tmp_path, monkeypatch):
    def cap_ruim(ao_bloco):
        raise RuntimeError("sem mic")
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob_energia,
                   captura_factory=cap_ruim, publicar=lambda ev: None)
    assert s.iniciar()["erro"] == "captura"
    s2, _ = nova(tmp_path, lambda seg: ("x", 0.9))
    monkeypatch.setattr(ses, "Gravador", lambda pasta: (_ for _ in ()).throw(OSError("disco")))
    assert s2.iniciar()["erro"] == "disco"
    monkeypatch.undo()
    s3, _ = nova(tmp_path, lambda seg: ("x", 0.9))
    monkeypatch.setattr(s3, "_probs", lambda: (_ for _ in ()).throw(RuntimeError("silero")))
    assert s3.iniciar()["erro"] == "vad"


def test_encerrar_com_falha_ao_salvar_devolve_erro_mas_limpa_e_publica(tmp_path, monkeypatch):
    s, pub = nova(tmp_path, lambda seg: ("x", 0.9))
    s.iniciar()
    monkeypatch.setattr(s.reuniao, "salvar", lambda pasta: (_ for _ in ()).throw(OSError("disco")))
    e = s.encerrar()
    assert e["ok"] is False and e["erro"] == "salvar"
    assert pub[-1]["estado"] == "encerrou" and s.status()["ativa"] is False


# ---------- diarização pós-reunião ----------
def nova_dia(tmp_path, transcrever, resultado, pronta=True, **conf):
    chamadas, publicados = [], []

    def diarizar(pasta):
        chamadas.append(pasta.name)
        return resultado

    s = ses.Sessao(Conf(diarizacao=True, **conf), raiz=tmp_path, transcritor=transcrever, prob=prob_energia,
                   captura_factory=CapturaFalsa, publicar=publicados.append, diarizar=diarizar,
                   diarizacao_estado=lambda: {"pronta": pronta, "motivo": "x", "modo": "community-1", "baixado_em": ""})
    return s, publicados, chamadas


def test_encerrar_diariza_em_thread_e_publica_de_novo(tmp_path):
    s, pub, chamadas = nova_dia(tmp_path, lambda seg: ("x", 0.9), {"ok": True, "falantes": 2, "device": "cpu", "modo": "community-1"})
    r = s.iniciar()
    s.ao_bloco("outros", fala(), 1.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 2.0)
    e = s.encerrar()
    assert e["ok"] and e["pasta"] == r["pasta"]
    assert esperar(lambda: [p["estado"] for p in pub].count("encerrou") == 2)
    assert [p["estado"] for p in pub] == ["iniciou", "encerrou", "diarizando", "encerrou"]
    assert all(p["pasta"] == r["pasta"] for p in pub[1:])
    assert pub[1]["resumo"].endswith("falas.") and "falantes" not in pub[1]["resumo"]
    assert pub[-1]["resumo"].startswith("Reunião encerrada: ") and pub[-1]["resumo"].endswith("2 falantes identificados.")
    assert chamadas == [r["pasta"]]


def test_encerrar_nao_espera_a_diarizacao(tmp_path):
    import threading
    solta = threading.Event()
    s, pub, _ = nova_dia(tmp_path, lambda seg: ("x", 0.9), {"ok": True, "falantes": 1})
    s.diarizar_fn = lambda pasta: (solta.wait(10), {"ok": True, "falantes": 1})[1]
    s.iniciar()
    t0 = time.monotonic()
    s.encerrar()
    assert time.monotonic() - t0 < 2 and [p["estado"] for p in pub][-1] == "diarizando"
    solta.set()
    assert esperar(lambda: pub[-1]["estado"] == "encerrou" and "1 falante identificado" in pub[-1]["resumo"])


def test_encerrar_sem_modelo_pronto_nao_diariza(tmp_path):
    s, pub, chamadas = nova_dia(tmp_path, lambda seg: ("x", 0.9), {"ok": True, "falantes": 2}, pronta=False)
    s.iniciar()
    s.encerrar()
    assert not esperar(lambda: chamadas or s.diarizando, 0.3)       # a decisão é síncrona no encerrar: nada dispara
    assert [p["estado"] for p in pub] == ["iniciou", "encerrou"]


def test_encerrar_com_diarizacao_desligada_na_config_nao_diariza(tmp_path):
    chamadas = []
    s = ses.Sessao(Conf(), raiz=tmp_path, transcritor=lambda seg: ("x", 0.9), prob=prob_energia, captura_factory=CapturaFalsa,
                   publicar=lambda e: None, diarizar=lambda p: chamadas.append(p),
                   diarizacao_estado=lambda: {"pronta": True, "motivo": "", "modo": "community-1", "baixado_em": ""})
    s.iniciar()
    s.encerrar()
    assert not esperar(lambda: chamadas or s.diarizando, 0.3)


def test_diarizacao_que_falha_publica_erro_e_nao_derruba(tmp_path):
    s, pub, _ = nova_dia(tmp_path, lambda seg: ("x", 0.9), {"ok": False, "erro": "sem_audio"})
    s.iniciar()
    s.encerrar()
    assert esperar(lambda: pub[-1]["estado"] == "erro")
    assert pub[-1]["pasta"] and "falantes" in pub[-1]["resumo"]


def test_diarizar_pasta_pedida_roda_uma_por_vez(tmp_path):
    import threading
    solta = threading.Event()
    s, pub, _ = nova_dia(tmp_path, lambda seg: ("x", 0.9), None)
    s.diarizar_fn = lambda pasta: (solta.wait(10), {"ok": True, "falantes": 2})[1]
    assert s.diarizar_pasta_em_thread("2026-10-13_1500") == {"ok": True}
    assert s.diarizar_pasta_em_thread("2026-10-13_1500") == {"ok": False, "erro": "rodando"}
    solta.set()
    assert esperar(lambda: pub and pub[-1]["estado"] == "encerrou")
    assert s.diarizar_pasta_em_thread("2026-10-13_1500") == {"ok": True}
    esperar(lambda: not s.diarizando)


def test_sem_fala_publica_encerrou_com_nenhum_falante(tmp_path):
    s, pub, _ = nova_dia(tmp_path, lambda seg: ("x", 0.9), {"ok": False, "erro": "sem_fala"})
    s.iniciar()
    s.encerrar()
    assert esperar(lambda: pub[-1]["estado"] == "encerrou" and pub[-1]["resumo"].endswith("Nenhum falante identificado."))
    assert "0 falantes" not in pub[-1]["resumo"] and [p["estado"] for p in pub].count("erro") == 0


def test_flac_segue_o_relogio_das_falas_com_lacuna_sem_quadros(tmp_path):
    import soundfile as sf
    s, _ = nova(tmp_path, lambda seg: ("", 0.9))
    r = s.iniciar()
    meio = np.full(8000, 3000, dtype=np.int16)           # 0,5 s
    s.ao_bloco("outros", meio, 0.0)
    s.ao_bloco("outros", meio, 10.0)                      # 9,5 s sem quadros no meio
    s.encerrar()
    dados, taxa = sf.read(str(tmp_path / r["pasta"] / "tmp" / "outros.flac"), dtype="int16")
    assert taxa == 16000 and abs(len(dados) / 16000 - 10.5) < 0.01
    assert np.all(dados[8000:160000] == 0) and np.all(dados[160000:] == 3000)


def test_lacuna_pequena_nao_gera_zeros_e_lacuna_enorme_e_limitada(tmp_path):
    s, _ = nova(tmp_path, lambda seg: ("", 0.9))
    s.iniciar()
    meio = np.full(8000, 3000, dtype=np.int16)
    s.ao_bloco("outros", meio, 0.0)
    s.ao_bloco("outros", meio, 0.52)                      # 20 ms de jitter: nada a preencher
    assert s.gravador.amostras("outros") == 16000
    s.ao_bloco("outros", meio, 20000.0)                   # ~5,5 h: limitada a 1 h de zeros
    assert s.gravador.amostras("outros") == 16000 + 3600 * 16000 + 8000
    s.encerrar()


def test_falha_do_transcritor_deixa_marcador_e_resumo(tmp_path):
    s, pub = nova(tmp_path, lambda seg: ("", -1.0))
    r0 = s.iniciar()
    s.ao_bloco("outros", fala(), 10.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 11.0)
    assert esperar(lambda: s.transcricao.falas())
    r = s.encerrar()
    f = json.loads((tmp_path / r0["pasta"] / "transcricao.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert f["trilha"] == "sistema" and f["texto"] == "trecho não transcrito" and f["t1"] > f["t0"]
    assert "[trecho não transcrito]" in (tmp_path / r0["pasta"] / "transcricao.md").read_text(encoding="utf-8")
    assert r["falas"] == 0
    assert "1 trecho não transcrito" in [p for p in pub if p["estado"] == "encerrou"][0]["resumo"]


def test_vazio_legitimo_nao_gera_marcador_nem_aviso(tmp_path):
    s, pub = nova(tmp_path, lambda seg: ("", 0.9))
    r0 = s.iniciar()
    s.ao_bloco("outros", fala(), 10.0)
    s.ao_bloco("outros", np.zeros(16000, dtype=np.int16), 11.0)
    s.encerrar()
    arq = tmp_path / r0["pasta"] / "transcricao.jsonl"
    assert not arq.exists() or not arq.read_text(encoding="utf-8").strip()
    assert "não transcrito" not in [p for p in pub if p["estado"] == "encerrou"][0]["resumo"]
