"""Vard: central de voz do PC."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vard-nucleo")
except PackageNotFoundError:  # rodando da fonte sem instalar
    import re as _re
    from pathlib import Path as _Path

    _pyproject = _Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        _texto = _pyproject.read_text(encoding="utf-8")
        _m = _re.search(r'^version\s*=\s*"([^"]+)"', _texto, _re.MULTILINE)
        __version__ = _m.group(1) if _m else "0.0.0"
    except OSError:
        __version__ = "0.0.0"
