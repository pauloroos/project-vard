from types import SimpleNamespace

import pytest

from vard_voz.motor import VOZ, Motor


class _Falantes(dict):
    """dict que conta os acessos por chave."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.acessos = 0

    def __getitem__(self, chave):
        self.acessos += 1
        return super().__getitem__(chave)


def _motor():
    falantes = _Falantes({
        "Zeca": {"gpt_cond_latent": "gz", "speaker_embedding": "ez"},
        VOZ: {"gpt_cond_latent": "gs", "speaker_embedding": "es"},
        "Ana Florence": {"gpt_cond_latent": "ga", "speaker_embedding": "ea"},
    })
    m = Motor(device="cpu")
    m._modelo = SimpleNamespace(speaker_manager=SimpleNamespace(speakers=falantes))
    return m, falantes


def test_vozes_suad_primeiro_resto_alfabetico():
    m, _ = _motor()
    assert m.vozes() == [VOZ, "Ana Florence", "Zeca"]


def test_vozes_sem_modelo_so_a_padrao():
    assert Motor(device="cpu").vozes() == [VOZ]


def test_latentes_cacheia_por_voz():
    m, falantes = _motor()
    a = m._latentes("Ana Florence")
    assert a == ("ga", "ea")
    assert m._latentes("Ana Florence") is a
    assert falantes.acessos == 1


def test_latentes_sem_voz_usa_a_padrao():
    m, _ = _motor()
    assert m._latentes(None) == ("gs", "es") and m._latentes("") == ("gs", "es")


def test_latentes_desconhecida_levanta_e_nao_entra_no_cache():
    m, _ = _motor()
    with pytest.raises(KeyError):
        m._latentes("Ninguém")
    assert "Ninguém" not in m._cache


def test_tem_voz():
    m, _ = _motor()
    assert m.tem_voz("Ana Florence") and not m.tem_voz("Ninguém")
    assert Motor(device="cpu").tem_voz(VOZ) is False


def test_falar_fluxo_voz_desconhecida_levanta_na_chamada():
    m, _ = _motor()
    with pytest.raises(KeyError):
        m.falar_fluxo("Oi", 1.0, "Ninguém")  # sem consumir o gerador
