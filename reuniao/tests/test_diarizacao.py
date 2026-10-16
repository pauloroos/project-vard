import itertools
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vard_reuniao import armazenamento as arm
from vard_reuniao import diarizacao as dia
from vard_reuniao.armazenamento import Fala

FIXTURES = Path(__file__).parent / "fixtures"


def F(t0, t1, trilha="outros", texto="x", falante=None):
    return Fala(t0, t1, trilha, texto, falante)


# ---------- atribuir ----------
def test_atribuir_maior_sobreposicao_ganha():
    falas = [F(0, 10)]
    trechos = [(0.0, 3.0, 1), (3.0, 10.0, 2)]
    assert dia.atribuir(falas, trechos)[0].falante == 2


def test_atribuir_soma_sobreposicoes_do_mesmo_falante():
    falas = [F(0, 10)]
    trechos = [(0.0, 4.0, 1), (4.0, 6.0, 2), (6.0, 10.0, 1)]
    assert dia.atribuir(falas, trechos)[0].falante == 1


def test_atribuir_sem_sobreposicao_vai_para_o_trecho_mais_proximo():
    falas = [F(20, 22), F(0.5, 1)]
    trechos = [(2.0, 4.0, 1), (15.0, 18.0, 2)]
    r = dia.atribuir(falas, trechos)
    assert r[0].falante == 2 and r[1].falante == 1


def test_atribuir_nao_mexe_em_eu_nem_sistema_e_e_puro():
    falas = [F(0, 5, "eu", falante=None), F(1, 2, "sistema"), F(0, 5, "outros")]
    r = dia.atribuir(falas, [(0.0, 5.0, 3)])
    assert [f.falante for f in r] == [None, None, 3]
    assert falas[2].falante is None          # entrada intacta
    assert r[0] == falas[0]


def test_atribuir_sem_trechos_deixa_como_esta():
    assert dia.atribuir([F(0, 1)], [])[0].falante is None


# ---------- GPU ----------
def test_escolher_device_limite():
    assert dia.escolher_device(1499) == "cpu"
    assert dia.escolher_device(1500) == "cuda"


def test_gpu_livre_mb_le_o_nvidia_smi():
    chamadas = []

    def run(cmd, **kw):
        chamadas.append(cmd)
        return type("R", (), {"returncode": 0, "stdout": "1200\n"})()

    assert dia.gpu_livre_mb(run) == 1200
    assert chamadas[0][0] == "nvidia-smi" and "--query-gpu=memory.free" in chamadas[0]


def test_gpu_livre_mb_falha_vira_zero():
    def run(cmd, **kw):
        raise FileNotFoundError("nvidia-smi")

    assert dia.gpu_livre_mb(run) == 0
    assert dia.gpu_livre_mb(lambda c, **k: type("R", (), {"returncode": 1, "stdout": ""})()) == 0
    assert dia.gpu_livre_mb(lambda c, **k: type("R", (), {"returncode": 0, "stdout": "abc"})()) == 0


# ---------- renumerar ----------
def test_renumerar_por_primeira_aparicao():
    brutos = [(5.0, 6.0, "SPEAKER_01"), (0.0, 2.0, "SPEAKER_07"), (2.0, 4.0, "SPEAKER_01")]
    assert dia.renumerar(brutos) == [(0.0, 2.0, 1), (2.0, 4.0, 2), (5.0, 6.0, 2)]


# ---------- reserva por embeddings ----------
def test_agrupar_separa_vetores_distantes_e_junta_parecidos():
    emb = [[1.0, 0.0], [0.99, 0.05], [0.0, 1.0], [0.05, 0.98]]
    r = dia.agrupar(emb)
    assert r[0] == r[1] and r[2] == r[3] and r[0] != r[2]
    assert dia.agrupar([]) == [] and dia.agrupar([[1.0, 0.0]]) == [1]


def test_diarizar_reserva_com_embeddings_falsos():
    falas = [F(0, 3), F(3.5, 7), F(8, 11), F(1, 2, "eu"), F(12, 12.1)]       # eu e fala curtíssima ficam de fora
    vetores = {0: [1.0, 0.0], 3.5: [0.0, 1.0], 8: [0.98, 0.1]}
    r = dia.diarizar_reserva(Path("x.flac"), falas, "cpu", embeddar=lambda t0, t1: vetores[t0])
    assert r == [(0.0, 3.0, 1), (3.5, 7.0, 2), (8.0, 11.0, 1)]


# ---------- estado ----------
def test_estado_arquivo_ausente(tmp_path):
    e = dia.estado(tmp_path / "nao-existe.json")
    assert e["pronta"] is False and e["modo"] == "nenhum" and "instalar-reuniao" in e["motivo"]


def test_estado_le_o_arquivo(tmp_path):
    arq = tmp_path / "m.json"
    arq.write_text(json.dumps({"pronto": True, "modo": "community-1", "motivo": "", "baixado_em": "2026-10-13T10:00:00"}), encoding="utf-8")
    e = dia.estado(arq)
    assert e == {"pronta": True, "motivo": "", "modo": "community-1", "baixado_em": "2026-10-13T10:00:00"}


def test_estado_pronto_false_com_motivo(tmp_path):
    arq = tmp_path / "m.json"
    arq.write_text(json.dumps({"pronto": False, "motivo": "condições não aceitas: https://huggingface.co/x"}), encoding="utf-8")
    e = dia.estado(arq)
    assert e["pronta"] is False and "condições" in e["motivo"] and e["modo"] == "nenhum"


def test_estado_arquivo_ilegivel(tmp_path):
    arq = tmp_path / "m.json"
    arq.write_text("{ruim", encoding="utf-8")
    assert dia.estado(arq)["pronta"] is False


def test_modelos_e_reserva():
    assert dia.MODELOS == ("pyannote/speaker-diarization-community-1", "pyannote/segmentation-3.0", "pyannote/speaker-diarization-3.1")
    assert dia.MODELO_RESERVA == "pyannote/wespeaker-voxceleb-resnet34-LM"


# ---------- diarizar_pasta ----------
def pasta_com_flac(tmp_path, com_flac=True):
    p = tmp_path / "2026-10-13_1500"
    p.mkdir()
    arm.Reuniao(pasta=p.name, inicio="2026-10-13T15:00:00", falantes={"2": "Ana"}).salvar(p)
    t = arm.Transcricao(p)
    t.acrescentar(F(0.0, 4.0, "eu", "oi pessoal"))
    t.acrescentar(F(4.5, 8.0, "outros", "bom dia"))
    t.acrescentar(F(9.0, 12.0, "outros", "tudo bem"))
    if com_flac:
        (p / "tmp").mkdir()
        sf.write(str(p / "tmp" / "outros.flac"), np.zeros(16000, dtype=np.float32), 16000, format="FLAC")
    return p


def test_diarizar_pasta_grava_falantes_e_md(tmp_path):
    p = pasta_com_flac(tmp_path)
    vistos = []

    def falso(flac, device):
        vistos.append((flac.name, device))
        return [(4.0, 8.5, 1), (8.5, 13.0, 2)]

    r = dia.diarizar_pasta(p, run_diarizar=falso, gpu_livre=lambda: 900)
    assert r == {"ok": True, "falantes": 2, "device": "cpu", "modo": "community-1"}
    assert vistos == [("outros.flac", "cpu")]
    assert arm.Reuniao.carregar(p).diarizada is True
    falas = arm.Transcricao(p).falas()
    assert [f.falante for f in falas] == [None, 1, 2]
    md = (p / "transcricao.md").read_text(encoding="utf-8")
    assert "falante 1: bom dia" in md and "falante 2 (Ana): tudo bem" in md and "usuário: oi pessoal" in md
    linhas = (p / "transcricao.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(linhas[1])["falante"] == 1


def test_diarizar_pasta_recebe_o_modo_por_parametro(tmp_path):
    p = pasta_com_flac(tmp_path)
    r = dia.diarizar_pasta(p, run_diarizar=lambda f, d: [(0.0, 20.0, 1)], gpu_livre=lambda: 0, modo="reserva")
    assert r["modo"] == "reserva"
    r = dia.diarizar_pasta(p, run_diarizar=lambda f, d: [(0.0, 20.0, 1)], gpu_livre=lambda: 0)
    assert r["modo"] == ("reserva" if dia.estado().get("modo") == "reserva" else "community-1")


def test_diarizar_pasta_sem_trechos_e_sem_fala_e_nao_marca(tmp_path):
    p = pasta_com_flac(tmp_path)
    r = dia.diarizar_pasta(p, run_diarizar=lambda f, d: [], gpu_livre=lambda: 0)
    assert r == {"ok": False, "erro": "sem_fala"}
    assert arm.Reuniao.carregar(p).diarizada is False
    assert [f.falante for f in arm.Transcricao(p).falas()] == [None, None, None]


def test_diarizar_pasta_usa_cuda_com_gpu_livre(tmp_path):
    p = pasta_com_flac(tmp_path)
    r = dia.diarizar_pasta(p, run_diarizar=lambda f, d: [(0.0, 20.0, 1)], gpu_livre=lambda: 4000)
    assert r["device"] == "cuda" and r["falantes"] == 1


def test_diarizar_pasta_sem_audio(tmp_path):
    p = pasta_com_flac(tmp_path, com_flac=False)
    assert dia.diarizar_pasta(p, run_diarizar=lambda f, d: [], gpu_livre=lambda: 0) == {"ok": False, "erro": "sem_audio"}
    assert arm.Reuniao.carregar(p).diarizada is False


def test_diarizar_pasta_falha_do_modelo_nao_estraga_a_transcricao(tmp_path):
    p = pasta_com_flac(tmp_path)

    def quebra(f, d):
        raise RuntimeError("sem memória")

    r = dia.diarizar_pasta(p, run_diarizar=quebra, gpu_livre=lambda: 0)
    assert r["ok"] is False and r["erro"] == "falha" and "sem memória" in r["detalhe"]
    assert arm.Reuniao.carregar(p).diarizada is False
    assert [f.falante for f in arm.Transcricao(p).falas()] == [None, None, None]


# ---------- DER próprio e prova real (só com o modelo baixado) ----------
def der(ref, hip, passo=0.05):
    """DER simples: fração do tempo de fala da referência com rótulo errado, após o melhor mapeamento entre permutações."""
    fim = max(b for _, b, _ in ref)
    rotulos_h = sorted({f for _, _, f in hip})
    rotulos_r = sorted({f for _, _, f in ref})

    def em(trechos, t):
        for a, b, f in trechos:
            if a <= t < b:
                return f
        return None

    amostras = [(em(ref, t), em(hip, t)) for t in np.arange(0, fim, passo)]
    amostras = [(r, h) for r, h in amostras if r is not None]
    alvo = rotulos_r + [None] * max(0, len(rotulos_h) - len(rotulos_r))
    melhor = 1.0
    for perm in itertools.permutations(alvo, len(rotulos_h)):
        mapa = dict(zip(rotulos_h, perm))
        melhor = min(melhor, sum(1 for r, h in amostras if mapa.get(h) != r) / len(amostras))
    return melhor


def test_der_proprio():
    ref = [(0, 5, 1), (5, 10, 2)]
    assert der(ref, [(0, 5, 2), (5, 10, 1)]) == 0.0          # rótulos trocados não contam
    assert abs(der(ref, [(0, 7.5, 1), (7.5, 10, 2)]) - 0.25) < 0.02
    assert der(ref, [(0, 10, 1)]) == 0.5


@pytest.mark.pc_real
def test_real_dois_falantes_der_abaixo_de_30_por_cento():
    if not dia.estado()["pronta"]:
        pytest.skip("modelo não baixado")
    ref = [(d["t0"], d["t1"], d["falante"]) for d in json.loads((FIXTURES / "dois-falantes.json").read_text(encoding="utf-8"))]
    t0 = time.monotonic()
    trechos = dia.diarizar_community(FIXTURES / "dois-falantes.wav", "cpu")
    print(f"\nDIARIZACAO_CPU_S={time.monotonic() - t0:.1f}")
    assert len({f for _, _, f in trechos}) == 2
    valor = der(ref, trechos)
    print(f"DER={valor:.3f}")
    assert valor < 0.3


def test_telemetria_do_pyannote_forcada_desligada(monkeypatch):
    import importlib
    import os

    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "1")
    from vard_reuniao import diarizacao
    importlib.reload(diarizacao)
    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "0"      # atribuição, não setdefault
    try:
        from pyannote.audio.telemetry import metrics
    except ImportError:
        return
    assert metrics.is_metrics_enabled() is False


def test_local_dos_modelos_respeita_vard_dados(tmp_path):
    import os
    from importlib import reload

    guardado = os.environ.get("VARD_DADOS")                    # valor do conftest (isolado por teste)
    try:
        os.environ["VARD_DADOS"] = str(tmp_path / "pasta com espaço")
        reload(dia)
        assert dia._LOCAL == tmp_path / "pasta com espaço"
        assert dia.ESTADO == tmp_path / "pasta com espaço" / "reuniao-modelos.json"
    finally:
        if guardado is None:
            os.environ.pop("VARD_DADOS", None)
        else:
            os.environ["VARD_DADOS"] = guardado
        reload(dia)                                             # devolve o módulo ao estado isolado do conftest
