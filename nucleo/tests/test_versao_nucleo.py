"""Teste do D1 — versão do núcleo deve vir de fonte única e bater com pyproject.toml.

Antes do conserto: vard.__version__ está hardcoded em '0.7.0' e difere do
pyproject.toml (0.9.1). Após o conserto: a versão é lida dinamicamente e
o teste passa.
"""
from __future__ import annotations

import re
from pathlib import Path


def test_versao_do_nucleo_bate_com_pyproject():
    """A versão exposta por vard.__version__ deve ser igual à do pyproject.toml."""
    import vard

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    texto = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', texto, re.MULTILINE)
    assert m, "pyproject.toml sem linha version"
    versao_esperada = m.group(1)

    assert vard.__version__ == versao_esperada, (
        f"vard.__version__={vard.__version__!r} != pyproject {versao_esperada!r}"
    )