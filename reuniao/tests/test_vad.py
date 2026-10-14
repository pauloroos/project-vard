import numpy as np

from vard_reuniao import vad
from tests.conftest import silencio, tom


def prob_energia(janela: np.ndarray) -> float:
    return 1.0 if np.abs(janela).mean() > 100 else 0.0


def pcm16(x: np.ndarray) -> np.ndarray:
    return (x * 32767).astype(np.int16)


def alimentar_tudo(seg: vad.Segmentador, sinal: np.ndarray, bloco=320) -> list:
    out = []
    for i in range(0, len(sinal), bloco):
        out += seg.alimentar(pcm16(sinal[i:i + bloco]), i / 16000)
    return out


def test_fala_entre_silencios_vira_um_segmento():
    s = vad.Segmentador("outros", prob_energia)
    sinal = np.concatenate([silencio(1.0), tom(440, 2.0), silencio(1.5)])
    segs = alimentar_tudo(s, sinal)
    assert len(segs) == 1
    seg = segs[0]
    assert seg.trilha == "outros" and abs(seg.t0 - 1.0) < 0.1 and abs(seg.t1 - 3.0) < 0.1
    assert seg.pcm.dtype == np.int16 and abs(len(seg.pcm) / 16000 - 2.0) < 0.15


def test_pausa_curta_nao_corta():
    s = vad.Segmentador("eu", prob_energia, min_silencio_ms=700)
    sinal = np.concatenate([tom(440, 1.0), silencio(0.4), tom(440, 1.0), silencio(1.0)])
    assert len(alimentar_tudo(s, sinal)) == 1


def test_fala_curta_demais_e_descartada():
    s = vad.Segmentador("eu", prob_energia, min_fala_ms=250)
    sinal = np.concatenate([silencio(0.5), tom(440, 0.1), silencio(1.0)])
    assert alimentar_tudo(s, sinal) == []


def test_fala_longa_corta_no_maximo():
    s = vad.Segmentador("eu", prob_energia, max_fala_s=5.0)
    segs = alimentar_tudo(s, np.concatenate([tom(440, 12.0), silencio(1.0)]))
    assert len(segs) == 3 and all(seg.t1 - seg.t0 <= 5.05 for seg in segs)


def test_fechar_devolve_o_que_estava_aberto():
    s = vad.Segmentador("eu", prob_energia)
    assert alimentar_tudo(s, tom(440, 1.0)) == []
    seg = s.fechar()
    assert seg is not None and abs(seg.t1 - seg.t0 - 1.0) < 0.1
    assert s.fechar() is None


def test_t0_usa_o_relogio_do_bloco_nao_a_contagem():
    # O loopback não entrega quadros no silêncio: o tempo vem de t_bloco (monotônico), não do número de amostras.
    s = vad.Segmentador("outros", prob_energia)
    segs = s.alimentar(pcm16(tom(440, 0.5)), 100.0) + s.alimentar(pcm16(silencio(1.0)), 100.5)
    assert len(segs) == 1 and abs(segs[0].t0 - 100.0) < 0.05


def test_lacuna_sem_quadros_fecha_a_fala():
    # Loopback em silêncio não entrega blocos: o buraco no relógio conta como silêncio.
    s = vad.Segmentador("outros", prob_energia)
    segs = s.alimentar(pcm16(tom(440, 0.5)), 100.0)
    segs += s.alimentar(pcm16(tom(440, 0.5)), 105.0)
    ultimo = s.fechar()
    assert len(segs) == 1 and abs(segs[0].t0 - 100.0) < 0.05
    assert ultimo is not None and abs(ultimo.t0 - 105.0) < 0.05


def test_relogio_nao_deriva_com_resto_de_amostras():
    # Blocos de 320 (não múltiplo de 512) deixam resto; o t0 segue o t_bloco real, não a contagem.
    s = vad.Segmentador("eu", prob_energia)
    segs = []
    for i in range(10):
        segs += s.alimentar(pcm16(silencio(0.02)), 50.0 + i * 0.02)
    segs += s.alimentar(pcm16(tom(440, 0.5)), 70.0)
    segs += s.alimentar(pcm16(silencio(1.0)), 70.5)
    assert len(segs) == 1 and abs(segs[0].t0 - 70.0) < 0.05


def test_silero_novo_por_chamada_e_reset():
    pytest = __import__("pytest")
    pytest.importorskip("silero_vad")
    a, b = vad.carregar_silero(), vad.carregar_silero()
    assert a is not b and callable(a.reset)
