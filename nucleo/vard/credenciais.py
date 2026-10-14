"""Acessor de credenciais via cofre Windows (Rust/Tauri).

Este módulo chama os comandos Tauri do cofre generalizado sem expor valores.
Uso exclusivo pelo núcleo; o webview nunca recebe o valor da credencial.
Nada aqui imprime segredos.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_TIPOS_VALIDOS = {"provedor", "voz", "mcp"}


def _validar_alvo(tipo: str, id_: str) -> str:
    if tipo not in _TIPOS_VALIDOS:
        raise ValueError(f"tipo de credencial desconhecido: {tipo!r}")
    if not id_ or len(id_) > 128:
        raise ValueError("id deve ter de 1 a 128 caracteres")
    if not all(c.isascii() and (c.isalnum() or c in "-_.") for c in id_):
        raise ValueError("id só aceita letras, dígitos, hífen, sublinhado e ponto")
    return f"vard:{tipo}:{id_}"


def _binario_tauri() -> Path:
    """Caminho do binário Tauri em dev ou instalado."""
    # Em dev: target/debug/vard.exe ou target/release/vard.exe
    raiz = Path(__file__).resolve().parents[2]  # nucleo/vard/ → raiz do projeto
    for perfil in ("debug", "release"):
        candidato = raiz / "src-tauri" / "target" / perfil / "vard.exe"
        if candidato.exists():
            return candidato
    # Instalado: ao lado do executável principal
    exe = Path(sys.executable).resolve()
    candidato = exe.parent / "vard.exe"
    if candidato.exists():
        return candidato
    raise FileNotFoundError("binário Tauri não encontrado para acessar o cofre")


def _invocar_comando(comando: str, *args: str) -> str:
    """Chama um comando Tauri via CLI interna (placeholder).

    Na implementação real, isso será feito via IPC do Tauri ou chamada
    direta à DLL. Por enquanto, usamos subprocess como prova de conceito
    para validação de integração.
    """
    binario = _binario_tauri()
    cmd = [str(binario), "--cofre", comando, *args]
    resultado = subprocess.run(
        cmd, capture_output=True, text=True, timeout=10, creationflags=0x08000000
    )
    if resultado.returncode != 0:
        stderr = resultado.stderr.strip()
        # Não vazar detalhes sensíveis do erro
        if any(kw in stderr.lower() for kw in ("key", "token", "password", "secret")):
            raise RuntimeError("falha no cofre (detalhes suprimidos)")
        raise RuntimeError(stderr or "falha desconhecida no cofre")
    return resultado.stdout.strip()


def existe(tipo: str, id_: str) -> bool:
    """Verifica se uma credencial existe no cofre sem ler o valor."""
    try:
        alvo = _validar_alvo(tipo, id_)
    except ValueError:
        return False
    try:
        saida = _invocar_comando("existe", alvo)
        return saida.lower() == "true"
    except (FileNotFoundError, RuntimeError):
        return False


def gravar(tipo: str, id_: str, valor: str) -> None:
    """Grava uma credencial no cofre. Valor nunca é impresso."""
    alvo = _validar_alvo(tipo, id_)
    if not valor or len(valor) > 4096:
        raise ValueError("valor deve ter de 1 a 4096 caracteres")
    if any(ord(c) < 32 for c in valor):
        raise ValueError("valor não pode conter caracteres de controle")
    _invocar_comando("gravar", alvo, valor)


def apagar(tipo: str, id_: str) -> None:
    """Remove uma credencial do cofre."""
    alvo = _validar_alvo(tipo, id_)
    _invocar_comando("apagar", alvo)


def ler_para_uso_interno(tipo: str, id_: str) -> str | None:
    """Lê uma credencial para uso interno do núcleo. NUNCA imprima o retorno."""
    alvo = _validar_alvo(tipo, id_)
    try:
        saida = _invocar_comando("ler", alvo)
        return saida if saida else None
    except (FileNotFoundError, RuntimeError):
        return None