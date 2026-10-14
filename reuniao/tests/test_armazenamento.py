import datetime as dt
import json

import numpy as np
import soundfile as sf

from vard_reuniao import armazenamento as arm


def test_nome_pasta():
    assert arm.nome_pasta(dt.datetime(2026, 10, 13, 15, 0)) == "2026-10-13_1500"


def test_reuniao_salva_e_carrega(pasta_reuniao):
    r = arm.Reuniao(pasta=pasta_reuniao.name, inicio="2026-10-13T15:00:00-04:00", dispositivos={"eu": "Mic", "outros": "Fone"})
    r.salvar(pasta_reuniao)
    assert json.loads((pasta_reuniao / "reuniao.json").read_text(encoding="utf-8"))["trilhas"] == ["eu", "outros"]
    assert arm.Reuniao.carregar(pasta_reuniao) == r


def test_transcricao_jsonl_e_md(pasta_reuniao):
    t = arm.Transcricao(pasta_reuniao)
    t.acrescentar(arm.Fala(12.4, 18.9, "outros", "Vamos decidir o prazo."))
    t.acrescentar(arm.Fala(20.0, 21.0, "eu", "Fechado."))
    t.marcador(25.0, "dispositivo trocou")
    linhas = (pasta_reuniao / "transcricao.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 3 and json.loads(linhas[0]) == {"t0": 12.4, "t1": 18.9, "trilha": "outros", "falante": None, "texto": "Vamos decidir o prazo."}
    md = (pasta_reuniao / "transcricao.md").read_text(encoding="utf-8")
    assert "[00:12] outros: Vamos decidir o prazo." in md and "[00:20] usuário: Fechado." in md and "[00:25] [dispositivo trocou]" in md
    assert [f.texto for f in t.falas()] == ["Vamos decidir o prazo.", "Fechado.", "dispositivo trocou"]


def test_linha_md_com_falantes():
    assert arm.linha_md(arm.Fala(18.0, 19.0, "outros", "Oi", falante=2), {"2": "Ana"}) == "[00:18] falante 2 (Ana): Oi"
    assert arm.linha_md(arm.Fala(18.0, 19.0, "outros", "Oi", falante=1), {}) == "[00:18] falante 1: Oi"
    assert arm.linha_md(arm.Fala(18.0, 19.0, "eu", "Oi"), {}) == "[00:18] usuário: Oi"


def test_reescrever_md_com_nomes(pasta_reuniao):
    t = arm.Transcricao(pasta_reuniao)
    t.acrescentar(arm.Fala(1.0, 2.0, "outros", "Oi", falante=2))
    t.reescrever({"2": "Ana"})
    assert "falante 2 (Ana): Oi" in (pasta_reuniao / "transcricao.md").read_text(encoding="utf-8")


def test_gravador_flac_16k_mono(pasta_reuniao):
    g = arm.Gravador(pasta_reuniao)
    g.escrever("eu", np.zeros(1600, dtype=np.int16))
    g.escrever("eu", np.full(1600, 1000, dtype=np.int16))
    g.escrever("outros", np.zeros(800, dtype=np.int16))
    g.fechar()
    dados, taxa = sf.read(pasta_reuniao / "tmp" / "eu.flac", dtype="int16")
    assert taxa == 16000 and dados.ndim == 1 and len(dados) == 3200 and dados[-1] == 1000
    assert (pasta_reuniao / "tmp" / "outros.flac").exists()


def test_listar_mais_recentes_primeiro(tmp_path):
    for nome in ("2026-10-11_0900", "2026-10-13_1500", "2026-10-12_1000"):
        p = tmp_path / nome
        p.mkdir()
        arm.Reuniao(pasta=nome, inicio="x").salvar(p)
    (tmp_path / "lixo").mkdir()          # pasta sem reuniao.json é ignorada
    assert [r.pasta for r in arm.listar(tmp_path, n=2)] == ["2026-10-13_1500", "2026-10-12_1000"]
    assert arm.ultima(tmp_path).pasta == "2026-10-13_1500"
    assert arm.ultima(tmp_path / "vazia") is None


def test_reescrever_persiste_nomes_no_json(pasta_reuniao):
    arm.Reuniao(pasta=pasta_reuniao.name, inicio="x").salvar(pasta_reuniao)
    t = arm.Transcricao(pasta_reuniao)
    t.acrescentar(arm.Fala(1.0, 2.0, "outros", "Oi", falante=2))
    t.reescrever({"2": "Ana"})
    assert arm.Reuniao.carregar(pasta_reuniao).falantes == {"2": "Ana"}
    t2 = arm.Transcricao(pasta_reuniao)                  # reabre: nomes mantidos
    t2.acrescentar(arm.Fala(3.0, 4.0, "outros", "Tchau", falante=2))
    md = (pasta_reuniao / "transcricao.md").read_text(encoding="utf-8")
    assert "[00:01] falante 2 (Ana): Oi" in md and "[00:03] falante 2 (Ana): Tchau" in md


def test_transcricao_reabre_com_falas_existentes(pasta_reuniao):
    arm.Transcricao(pasta_reuniao).acrescentar(arm.Fala(1.0, 2.0, "eu", "um"))
    t = arm.Transcricao(pasta_reuniao)
    t.acrescentar(arm.Fala(3.0, 4.0, "eu", "dois"))
    assert [f.texto for f in t.falas()] == ["um", "dois"]


def test_mmss_vem_do_armazenamento():
    from vard_reuniao import texto
    assert texto.mmss is arm.mmss


def test_fechar_orfas_grava_fim_duracao_apagar_audio_e_marcador(tmp_path):
    import datetime as dt
    from vard_reuniao import armazenamento as arm

    p = tmp_path / "2026-10-13_1000"
    arm.Reuniao(pasta=p.name, inicio="2026-10-13T10:00:00").salvar(p)
    t = arm.Transcricao(p)
    t.acrescentar(arm.Fala(1.0, 4.5, "eu", "oi"))
    t.acrescentar(arm.Fala(60.0, 95.9, "outros", "tchau"))
    fechada = tmp_path / "2026-10-12_1000"
    arm.Reuniao(pasta=fechada.name, inicio="2026-10-12T10:00:00", fim="2026-10-12T11:00:00", duracao_s=3600).salvar(fechada)
    agora = dt.datetime(2026, 10, 14, 9, 0)
    assert arm.fechar_orfas(tmp_path, agora) == [p.name]
    r = arm.Reuniao.carregar(p)
    assert r.fim == "2026-10-14T09:00:00" and r.duracao_s == 95
    assert r.apagar_audio_em == "2026-10-15T09:00:00" and r.guardar_audio is False
    ultima = arm.Transcricao(p).falas()[-1]
    assert ultima.trilha == "sistema" and "queda do serviço" in ultima.texto
    assert "queda do serviço" in (p / "transcricao.md").read_text(encoding="utf-8")
    assert arm.Reuniao.carregar(fechada).fim == "2026-10-12T11:00:00"          # a já fechada não muda
    assert arm.fechar_orfas(tmp_path, agora) == []                              # idempotente


def test_fechar_orfas_respeita_guardar_audio(tmp_path):
    import datetime as dt
    from vard_reuniao import armazenamento as arm

    p = tmp_path / "2026-10-13_1000"
    arm.Reuniao(pasta=p.name, inicio="2026-10-13T10:00:00").salvar(p)
    arm.fechar_orfas(tmp_path, dt.datetime(2026, 10, 14, 9, 0), guardar_audio=True)
    r = arm.Reuniao.carregar(p)
    assert r.guardar_audio is True and r.apagar_audio_em == "" and r.duracao_s == 0


def test_raiz_dos_dados_respeita_vard_dados(tmp_path):
    import os
    from importlib import reload
    from vard_reuniao import armazenamento as arm

    guardado = os.environ.get("VARD_DADOS")                # valor do conftest (isolado por teste)
    try:
        os.environ["VARD_DADOS"] = str(tmp_path / "pasta com espaço")
        reload(arm)
        assert arm.RAIZ == tmp_path / "pasta com espaço" / "reunioes"
    finally:
        if guardado is None:
            os.environ.pop("VARD_DADOS", None)
        else:
            os.environ["VARD_DADOS"] = guardado
        reload(arm)                                         # devolve o módulo ao estado isolado do conftest
