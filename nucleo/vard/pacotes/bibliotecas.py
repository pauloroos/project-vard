"""Bibliotecas Python de um pacote opcional, instaladas no ambiente do serviço de voz.

As `dependencias` do manifesto misturam ids de outros pacotes (ex.: "xtts-v2") e requisitos Python
(ex.: "kokoro-onnx==0.6.1"). Os requisitos vão para o Python do serviço de voz, achado como o app faz
(src-tauri/src/instalacao.rs): `servicos.voz_python` do instalacao.json, senão
`<raiz_codigo>/voz/.venv/Scripts/python.exe`. Instala com `uv pip install --python <python>` quando o uv
está no PATH; sem ele, `<python> -m pip install`.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

log = logging.getLogger("vard.pacotes")

# Bibliotecas grandes (torch) podem levar muitos minutos.
TIMEOUT_BIBLIOTECAS = 3600.0

Executar = Callable[[list[str]], "tuple[int, str]"]


def dependencias_python(dependencias: Iterable[str], ids_pacotes: Iterable[str]) -> list[str]:
    """Só os requisitos Python: o que não é id de outro pacote do manifesto."""
    ids = set(ids_pacotes)
    return [d.strip() for d in dependencias if d.strip() and d.strip() not in ids]


def python_da_voz(instalacao: dict | None = None) -> Path | None:
    """Python do serviço de voz desta máquina; None se não existe."""
    if instalacao is None:
        from vard import instalacao as _inst

        instalacao = _inst.ler()
    servicos = instalacao.get("servicos") if isinstance(instalacao.get("servicos"), dict) else {}
    configurado = str(servicos.get("voz_python") or "").strip()
    if configurado:
        caminho = Path(configurado)
    else:
        raiz = str(instalacao.get("raiz_codigo") or "").strip()
        if not raiz:
            return None
        caminho = Path(raiz) / "voz" / ".venv" / "Scripts" / "python.exe"
    return caminho if caminho.is_file() else None


def comando_instalacao(python: Path, deps: list[str], which: Callable[[str], str | None] | None = None) -> list[str]:
    """`uv pip install --python <python> <deps>`; sem uv, `<python> -m pip install <deps>`."""
    uv = (which or shutil.which)("uv")
    if uv:
        return [uv, "pip", "install", "--python", str(python), *deps]
    return [str(python), "-m", "pip", "install", *deps]


def _executar_padrao(comando: list[str]) -> tuple[int, str]:
    """Roda o instalador e devolve (código, saída de erro)."""
    try:
        r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT_BIBLIOTECAS, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return 1, "tempo esgotado"
    except OSError as exc:
        return 1, f"nao consegui executar o instalador ({type(exc).__name__})"
    return r.returncode, (r.stderr or "") + (r.stdout or "" if r.returncode else "")


def resumo_erro(saida: str, python: Path) -> str:
    """Última linha útil da saída, sem caminhos da máquina."""
    linhas = [l.strip() for l in saida.splitlines() if l.strip()]
    texto = linhas[-1] if linhas else "falha sem mensagem"
    for caminho in {str(python), str(python.parent), str(python).replace("\\", "/")}:
        texto = texto.replace(caminho, "<python da voz>")
    return texto[:200]


def instalar_bibliotecas(deps: list[str], python: Path | None, executar: Executar | None = None,
                         which: Callable[[str], str | None] | None = None) -> str | None:
    """Instala `deps` no Python do serviço de voz. Devolve None se deu certo, senão a mensagem de erro."""
    if not deps:
        return None
    if python is None:
        return "ambiente do servico de voz nao encontrado (instalacao.json: servicos.voz_python ou raiz_codigo)"
    comando = comando_instalacao(python, deps, which)
    log.info("instalando bibliotecas no servico de voz: %s", " ".join(deps))
    codigo, saida = (executar or _executar_padrao)(comando)
    if codigo == 0:
        return None
    return f"nao consegui instalar as bibliotecas ({', '.join(deps)}): {resumo_erro(saida, python)}"
