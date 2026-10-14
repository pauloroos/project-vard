"""instalacao.json: onde o Vard e o OpenJarvis estão instalados nesta máquina."""
import json

from vard import instalacao


def _defaults():
    return {"raiz_codigo": "", "openjarvis_src": "", "openjarvis_home": "", "modelo": "",
            "contexto": 0, "servicos": {}}


def test_ausente_devolve_defaults_neutros(tmp_path):
    d = instalacao.ler(tmp_path / "nao-existe.json")
    assert d == _defaults()


def test_invalido_devolve_defaults_sem_lancar(tmp_path):
    arq = tmp_path / "instalacao.json"
    arq.write_text("{quebrado", encoding="utf-8")
    assert instalacao.ler(arq) == _defaults()
    arq.write_text("[1, 2]", encoding="utf-8")
    assert instalacao.ler(arq) == _defaults()
    arq.write_text('"texto"', encoding="utf-8")
    assert instalacao.ler(arq) == _defaults()


def test_le_os_campos_e_preenche_os_faltantes(tmp_path):
    arq = tmp_path / "instalacao.json"
    arq.write_text(json.dumps({"raiz_codigo": "X:/DEV/demo", "contexto": 16000}), encoding="utf-8")
    d = instalacao.ler(arq)
    assert d["raiz_codigo"] == "X:/DEV/demo" and d["contexto"] == 16000
    assert d["openjarvis_src"] == "" and d["openjarvis_home"] == "" and d["modelo"] == ""
    assert d["servicos"] == {}


def test_campos_errados_caem_no_neutro(tmp_path):
    arq = tmp_path / "instalacao.json"
    arq.write_text(json.dumps({"contexto": "muito", "servicos": "nao-objeto",
                              "openjarvis_home": 5}), encoding="utf-8")
    d = instalacao.ler(arq)
    assert d["contexto"] == 0 and d["servicos"] == {} and d["openjarvis_home"] == "5"


def test_variavel_de_ambiente_aponta_o_arquivo(tmp_path, monkeypatch):
    arq = tmp_path / "fora" / "instalacao maquina.json"
    arq.parent.mkdir()
    arq.write_text(json.dumps({"modelo": "modelo-local"}), encoding="utf-8")
    monkeypatch.setenv("VARD_INSTALACAO", str(arq))
    assert instalacao.arquivo() == arq
    assert instalacao.ler()["modelo"] == "modelo-local"


def test_padrao_e_pasta_de_dados(monkeypatch):
    monkeypatch.delenv("VARD_INSTALACAO", raising=False)
    from vard import config
    assert instalacao.arquivo() == config.pasta_dados() / "instalacao.json"


def test_caminho_com_espaco(tmp_path, monkeypatch):
    arq = tmp_path / "pasta com espaço" / "instalacao.json"
    arq.parent.mkdir()
    arq.write_text(json.dumps({"openjarvis_src": "X:/Programas DEV/openjarvis/src"}), encoding="utf-8")
    monkeypatch.setenv("VARD_INSTALACAO", str(arq))
    assert instalacao.ler()["openjarvis_src"] == "X:/Programas DEV/openjarvis/src"


def test_servicos_sao_copiados_nao_referenciados(tmp_path):
    arq = tmp_path / "instalacao.json"
    arq.write_text(json.dumps({"servicos": {"ponte": {"porta": 4700}}}), encoding="utf-8")
    d = instalacao.ler(arq)
    assert d["servicos"] == {"ponte": {"porta": 4700}}
