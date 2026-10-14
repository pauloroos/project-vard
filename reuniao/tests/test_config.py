from pathlib import Path

from vard_reuniao import config

EXEMPLO = Path(__file__).resolve().parents[2] / "config" / "examples" / "reuniao.example.toml"


def test_o_exemplo_publico_carrega():
    c = config.carregar(EXEMPLO)
    assert c.guardar_audio is False and c.apagar_audio_horas == 24 and c.reter_dias == 90
    assert "legendas pela comunidade" in c.bloqueio and c.eco_limiar == 0.8 and c.bloco_chars == 9000
    assert c.diarizacao is False and c.max_fala_s == 20.0


def test_arquivo_ausente_usa_padroes(tmp_path):
    c = config.carregar(tmp_path / "nao-existe.toml")
    assert c == config.Conf()
    assert c == config.carregar(EXEMPLO)   # padrões embutidos iguais ao exemplo público


def test_valor_invalido_cai_em_padroes(tmp_path):
    arq = tmp_path / "ruim.toml"
    arq.write_text('[audio]\nreter_dias = "muitos"\n', encoding="utf-8")
    assert config.carregar(arq) == config.Conf()


def test_bloqueio_exato_igual_ao_exemplo():
    c = config.carregar(EXEMPLO)
    assert "obrigado" in c.bloqueio_exato and "amém" in c.bloqueio_exato


def test_cadeia_de_precedencia_com_pasta_com_espaco(tmp_path, monkeypatch):
    """VARD_REUNIAO_CONFIG > VARD_CONFIG/reuniao.toml > pasta do usuário ($VARD_DADOS/config)."""
    raiz = tmp_path / "pasta com espaço"
    direto = raiz / "direta.toml"
    em_config = raiz / "config" / "reuniao.toml"
    em_config.parent.mkdir(parents=True)
    direto.write_text("[diarizacao]\nligada = true\n", encoding="utf-8")
    em_config.write_text("[ata]\nbloco_chars = 111\n", encoding="utf-8")
    monkeypatch.setenv("VARD_REUNIAO_CONFIG", str(direto))
    monkeypatch.setenv("VARD_CONFIG", str(raiz / "config"))
    monkeypatch.setenv("VARD_DADOS", str(raiz))
    assert config.carregar().diarizacao is True                   # a variável direta vence tudo
    monkeypatch.delenv("VARD_REUNIAO_CONFIG")
    assert config.carregar().bloco_chars == 111                   # depois, VARD_CONFIG/reuniao.toml
    monkeypatch.delenv("VARD_CONFIG")
    assert config.carregar().bloco_chars == 111                   # $VARD_DADOS/config/reuniao.toml
    em_config.unlink()
    assert config.carregar() == config.Conf()                     # sem nenhum arquivo, padrões embutidos


def test_variavel_de_ambiente_aponta_outra_config(tmp_path, monkeypatch):
    arq = tmp_path / "outra.toml"
    arq.write_text("[diarizacao]\nligada = true\n", encoding="utf-8")
    monkeypatch.setenv("VARD_REUNIAO_CONFIG", str(arq))
    assert config.carregar().diarizacao is True
    monkeypatch.delenv("VARD_REUNIAO_CONFIG")
    assert config.carregar().diarizacao is False


def test_pasta_dados_respeita_variavel(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados com espaço"))
    assert config.pasta_dados() == tmp_path / "dados com espaço"
    monkeypatch.delenv("VARD_DADOS")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    assert config.pasta_dados() == tmp_path / "appdata" / "rdl-vard"
