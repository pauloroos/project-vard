"""Trazer o Telegram do OpenJarvis: token no cofre (dublê), chats no telegram.toml, origem intacta.

Tudo fictício e em pasta temporária: OPENJARVIS_HOME, VARD_CONFIG/VARD_DADOS e o cofre em memória
(fixture cofre_falso do conftest). O token nunca aparece em resposta nem em log.
"""
from __future__ import annotations

import hashlib
import json
import logging
import tomllib
from pathlib import Path

import pytest
import tomli_w

from vard import config as cfg_mod
from vard import telegram as tg
from vard import telegram_migracao as mig

TOKEN = "123456789:FICTICIO_token-de-teste_abc"
OUTRO = "987654321:OUTRO_token-ficticio_xyz"
ALVO = "vard:canal:telegram"


def _oj(casa: Path, *, token=TOKEN, chats="111,222", enabled=True) -> Path:
    casa.mkdir(parents=True, exist_ok=True)
    arq = casa / "config.toml"
    arq.write_text(tomli_w.dumps({
        "engine": {"default": "lmstudio"},
        "channel": {"enabled": enabled, "default_channel": "telegram",
                    "telegram": {"bot_token": token, "allowed_chat_ids": chats, "parse_mode": "Markdown"}},
    }), encoding="utf-8")
    return arq


@pytest.fixture
def oj(tmp_path, monkeypatch) -> Path:
    casa = tmp_path / "oj-casa"
    arq = _oj(casa)
    monkeypatch.setenv("OPENJARVIS_HOME", str(casa))
    return arq


def _tg_toml() -> dict:
    arq = cfg_mod.arquivo_config("telegram.toml")
    return tomllib.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def _sha(arq: Path) -> str:
    return hashlib.sha256(arq.read_bytes()).hexdigest()


def test_sem_openjarvis_nada_a_trazer():
    assert mig.previa()["disponivel"] is False
    r = mig.trazer()
    assert r["ok"] is False and r["motivo"] == "sem_origem"
    assert not cfg_mod.arquivo_config("telegram.toml").exists()


def test_previa_mostra_o_que_vem_sem_o_token(oj):
    p = mig.previa()
    assert p == {"disponivel": True, "vard_configurado": False, "ja_migrado": False, "pode_trazer": True,
                 "fonte": "openjarvis", "chats": 2, "ligado": True}
    assert TOKEN not in json.dumps(p)


def test_trazer_grava_token_no_cofre_e_chats_no_toml(oj, cofre_falso, caplog):
    caplog.set_level(logging.DEBUG)
    r = mig.trazer()
    assert r["ok"] is True and r["mudou"] is True and r["chats"] == 2
    assert cofre_falso == {ALVO: TOKEN}
    dados = _tg_toml()
    assert dados["habilitado"] is True
    assert dados["chats_permitidos"] == ["111", "222"]
    assert "token" not in dados
    assert TOKEN not in json.dumps(r) and TOKEN not in caplog.text
    # O poller do Vard passa a ter tudo o que precisa, sem OpenJarvis.
    assert tg.deve_iniciar_poller()
    assert tg._token_seguro(tg._ler_config_telegram()) == TOKEN


def test_origem_fica_intacta(oj):
    antes = _sha(oj)
    mig.previa()
    mig.trazer()
    mig.trazer(substituir=True)
    assert _sha(oj) == antes


def test_idempotente(oj, cofre_falso):
    assert mig.trazer()["mudou"] is True
    arq = cfg_mod.arquivo_config("telegram.toml")
    antes = _sha(arq)
    r = mig.trazer()
    assert r["ok"] is True and r["mudou"] is False
    assert _sha(arq) == antes
    assert mig.previa()["ja_migrado"] is True
    assert mig.previa()["pode_trazer"] is False


def test_nao_sobrescreve_telegram_do_vard_sem_confirmacao(oj, cofre_falso):
    cofre_falso[ALVO] = OUTRO
    tg.gravar_config_telegram({"habilitado": False, "chats_permitidos": ["999"], "timeout_s": 30})
    antes = _sha(cfg_mod.arquivo_config("telegram.toml"))
    assert mig.previa()["pode_trazer"] is False
    r = mig.trazer()
    assert r["ok"] is False and r["motivo"] == "ja_configurado"
    assert cofre_falso[ALVO] == OUTRO
    assert _sha(cfg_mod.arquivo_config("telegram.toml")) == antes
    r = mig.trazer(substituir=True)
    assert r["ok"] is True and r["mudou"] is True
    assert cofre_falso[ALVO] == TOKEN
    dados = _tg_toml()
    assert dados["chats_permitidos"] == ["111", "222"] and dados["habilitado"] is True
    assert dados["timeout_s"] == 30   # opções do Vard preservadas


def test_token_antigo_em_texto_conta_como_configurado_e_sai_ao_substituir(oj, cofre_falso):
    tg.gravar_config_telegram({"habilitado": True, "token": OUTRO, "chats_permitidos": []})
    assert mig.trazer()["motivo"] == "ja_configurado"
    assert mig.trazer(substituir=True)["ok"] is True
    assert "token" not in _tg_toml()


def test_marcador_do_exemplo_nao_e_token(tmp_path, monkeypatch):
    casa = tmp_path / "oj-marcador"
    _oj(casa, token="__TELEGRAM_TOKEN__", chats="__TELEGRAM_CHAT__")
    monkeypatch.setenv("OPENJARVIS_HOME", str(casa))
    assert mig.previa()["disponivel"] is False


def test_casa_pelo_instalacao_json(tmp_path, monkeypatch):
    casa = tmp_path / "oj-instalado"
    _oj(casa, chats="333")
    inst = tmp_path / "instalacao.json"
    inst.write_text(json.dumps({"openjarvis_home": str(casa)}), encoding="utf-8")
    monkeypatch.setenv("VARD_INSTALACAO", str(inst))
    p = mig.previa()
    assert p["disponivel"] is True and p["chats"] == 1


def test_segredos_toml_quando_o_openjarvis_nao_tem(cofre_falso):
    arq = cfg_mod.arquivo_segredos()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(tomli_w.dumps({"telegram": {"token": TOKEN, "chat_id": "444"}}), encoding="utf-8")
    antes = _sha(arq)
    r = mig.trazer()
    assert r["ok"] is True and r["fonte"] == "segredos"
    assert cofre_falso[ALVO] == TOKEN and _tg_toml()["chats_permitidos"] == ["444"]
    assert _sha(arq) == antes


@pytest.mark.parametrize("bruto,esperado", [
    ("111, 222;333", ("111", "222", "333")),
    (["111", 222, "111"], ("111", "222")),
    (555, ("555",)),
    ("-100123, lixo, ", ("-100123",)),
    ("", ()),
])
def test_formatos_de_allowed_chat_ids(bruto, esperado):
    assert mig._chats(bruto) == esperado


def test_falha_no_cofre_nao_grava_nada(oj, monkeypatch, caplog):
    from vard import credenciais

    def falhar(alvo, valor):
        raise RuntimeError("falha no cofre")

    monkeypatch.setattr(credenciais, "_gravar_windows", falhar)
    r = mig.trazer()
    assert r["ok"] is False and r["motivo"] == "cofre"
    assert not cfg_mod.arquivo_config("telegram.toml").exists()
    assert TOKEN not in json.dumps(r) and TOKEN not in caplog.text


def test_avisa_quando_o_openjarvis_ainda_sobe(oj, tmp_path):
    hud = tmp_path / "hud"
    hud.mkdir(parents=True, exist_ok=True)
    (hud / "hud.config.json").write_text(json.dumps({"cerebro": "proprio", "usar_openjarvis": True}), encoding="utf-8")
    assert mig.openjarvis_sobe() is True
    assert "OpenJarvis" in mig.trazer().get("aviso", "")


def test_repr_da_origem_nao_mostra_token(oj):
    assert TOKEN not in repr(mig.ler_origem())


def test_configurar_define_os_chats_do_campo_e_vazio_mantem():
    tg.configurar(True, "111")
    tg.configurar(True, "111, 222")
    assert _tg_toml()["chats_permitidos"] == ["111", "222"]
    tg.configurar(False, "")
    dados = _tg_toml()
    assert dados["chats_permitidos"] == ["111", "222"] and dados["habilitado"] is False
    assert tg.estado()["chat_permitido"] == "111, 222"
