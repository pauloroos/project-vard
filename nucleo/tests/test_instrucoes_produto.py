"""As instruções de produto precisam ir no pacote: instalado, não existe config/examples."""
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_pacote_leva_as_instrucoes_de_produto() -> None:
    dados = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    inclui = dados["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert inclui["../config/examples/persona.example.md"] == "vard/instrucoes_produto.md"


def test_instrucoes_pedem_para_perguntar_quando_nao_entender() -> None:
    from vard import perfil
    bloco = perfil._bloco_produto()
    assert "pergunte o que a pessoa quis dizer" in bloco and "nunca peça link" in bloco
