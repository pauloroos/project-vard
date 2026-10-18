"""Acessor de credenciais do cofre do Windows (o mesmo que o app grava em Rust).

Lê e grava direto no Gerenciador de Credenciais (CredReadW/CredWriteW), no formato do
keyring do app: alvo `vard:<tipo>:<id>`, credencial genérica, segredo em UTF-16LE.
Uso exclusivo pelo núcleo; o webview nunca recebe o valor da credencial.
Nada aqui imprime segredos.
"""
from __future__ import annotations

import sys

#: Mesmos tipos do cofre do app (src-tauri/src/cofre.rs); canal = Telegram e afins.
_TIPOS_VALIDOS = {"provedor", "voz", "mcp", "canal"}


def _validar_alvo(tipo: str, id_: str) -> str:
    if tipo not in _TIPOS_VALIDOS:
        raise ValueError(f"tipo de credencial desconhecido: {tipo!r}")
    if not id_ or len(id_) > 128:
        raise ValueError("id deve ter de 1 a 128 caracteres")
    if not all(c.isascii() and (c.isalnum() or c in "-_.") for c in id_):
        raise ValueError("id só aceita letras, dígitos, hífen, sublinhado e ponto")
    return f"vard:{tipo}:{id_}"


def _decodificar(blob: bytes) -> str:
    """O keyring do app grava o segredo em UTF-16; aceita UTF-8 também (gravado por outra ferramenta)."""
    if len(blob) % 2 == 0 and blob[1:2] == b"\x00":
        try:
            return blob.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    return blob.decode("utf-8", errors="strict")


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_ENTERPRISE = 3     # o mesmo do keyring do app
_COMENTARIO = "keyring v3.6.3"   # o app grava com este comentário; só informativo


def _api():
    """advapi32 e a estrutura CREDENTIALW; só no Windows."""
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

    return ctypes, ctypes.WinDLL("advapi32", use_last_error=True), _Credencial


def _ler_windows(alvo: str) -> str | None:
    """Lê uma credencial genérica do Gerenciador de Credenciais (o mesmo alvo que o app grava)."""
    if sys.platform != "win32":
        return None
    ctypes, advapi, _Credencial = _api()
    ponteiro = ctypes.POINTER(_Credencial)()
    if not advapi.CredReadW(alvo, _CRED_TYPE_GENERIC, 0, ctypes.byref(ponteiro)):
        return None
    try:
        cred = ponteiro.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return _decodificar(blob) or None
    except UnicodeDecodeError:
        return None
    finally:
        advapi.CredFree(ponteiro)


def _gravar_windows(alvo: str, valor: str) -> None:
    """Grava como o keyring do app (UTF-16LE, usuário = alvo), para o app ler o mesmo valor."""
    if sys.platform != "win32":
        raise RuntimeError("cofre do Windows indisponível")
    ctypes, advapi, _Credencial = _api()
    dados = valor.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(dados)).from_buffer_copy(dados)
    cred = _Credencial()
    cred.Type = _CRED_TYPE_GENERIC
    cred.TargetName = alvo
    cred.Comment = _COMENTARIO
    cred.CredentialBlobSize = len(dados)
    cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = _CRED_PERSIST_ENTERPRISE
    cred.TargetAlias = ""
    cred.UserName = alvo
    try:
        if not advapi.CredWriteW(ctypes.byref(cred), 0):
            raise RuntimeError("não foi possível gravar no cofre")   # nunca o valor nem o erro bruto
    finally:
        ctypes.memset(blob, 0, len(dados))


def _apagar_windows(alvo: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("cofre do Windows indisponível")
    ctypes, advapi, _ = _api()
    if not advapi.CredDeleteW(alvo, _CRED_TYPE_GENERIC, 0) and ctypes.get_last_error() != 1168:   # 1168 = não existe
        raise RuntimeError("não foi possível apagar do cofre")


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
    _gravar_windows(alvo, valor)


def apagar(tipo: str, id_: str) -> None:
    """Remove uma credencial do cofre (ausente não é erro)."""
    _apagar_windows(_validar_alvo(tipo, id_))


def ler_para_uso_interno(tipo: str, id_: str) -> str | None:
    """Lê uma credencial para uso interno do núcleo. NUNCA imprima o retorno."""
    return _ler_windows(_validar_alvo(tipo, id_))