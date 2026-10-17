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


def _decodificar(blob: bytes) -> str:
    """O keyring do app grava o segredo em UTF-16; aceita UTF-8 também (gravado por outra ferramenta)."""
    if len(blob) % 2 == 0 and blob[1:2] == b"\x00":
        try:
            return blob.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    return blob.decode("utf-8", errors="strict")


def _ler_windows(alvo: str) -> str | None:
    """Lê uma credencial genérica do Gerenciador de Credenciais (o mesmo alvo que o app grava)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _Credencial(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    ponteiro = ctypes.POINTER(_Credencial)()
    if not advapi.CredReadW(alvo, 1, 0, ctypes.byref(ponteiro)):   # 1 = CRED_TYPE_GENERIC
        return None
    try:
        cred = ponteiro.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return _decodificar(blob) or None
    except UnicodeDecodeError:
        return None
    finally:
        advapi.CredFree(ponteiro)


def separar_referencia(ref: str, tipo_padrao: str) -> tuple[str, str]:
    """`provedor:lm1` (como a tela grava em credencial_ref) ou só `lm1` → (tipo, id)."""
    tipo, sep, id_ = ref.strip().partition(":")
    return (tipo, id_) if sep and tipo in _TIPOS_VALIDOS else (tipo_padrao, ref.strip())


def existe(tipo: str, id_: str) -> bool:
    """Verifica se uma credencial existe no cofre sem ler o valor."""
    try:
        alvo = _validar_alvo(tipo, id_)
    except ValueError:
        return False
    return _ler_windows(alvo) is not None


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
    return _ler_windows(_validar_alvo(tipo, id_))