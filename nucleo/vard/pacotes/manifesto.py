"""Manifesto de pacotes opcionais do Vard.

Lê e valida config/pacotes/*.json. Cada pacote tem metadados fixos:
id, versao, tipo, url, sha256, bytes_download, bytes_instalado, python,
backend, licenca_url, dependencias e (para vozes) voz_id.

Regras:
- Hash SHA-256 obrigatório para download; pacote sem hash é recusado.
- Pacote marcado 'indisponivel' com motivo não pode ser instalado.
- Valores reais conferidos na origem; nunca inventar hash/tamanho.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("vard.pacotes")

RAIZ_CONFIG = Path(__file__).resolve().parent.parent.parent.parent / "config" / "pacotes"


@dataclass(frozen=True)
class PacoteInfo:
    """Metadados imutáveis de um pacote opcional."""

    id: str
    nome: str
    versao: str
    tipo: str  # "motor" | "voz" | "reuniao"
    descricao: str
    url: str
    sha256: str
    bytes_download: int
    bytes_instalado: int
    python: str
    backend: str
    licenca_url: str
    licenca_nome: str
    dependencias: list[str] = field(default_factory=list)
    voz_id: str | None = None
    indisponivel: bool = False
    motivo_indisponivel: str | None = None

    def instalavel(self) -> bool:
        """True se o pacote pode ser instalado (hash presente e não indisponível)."""
        if self.indisponivel:
            return False
        if not self.sha256 or not self.url:
            return False
        if self.bytes_download <= 0:
            return False
        return True


def _validar_pacote_raw(dados: dict[str, Any], origem: str) -> PacoteInfo:
    """Valida um dicionário bruto e devolve PacoteInfo ou levanta ValueError."""
    campos_obrigatorios = [
        "id", "nome", "versao", "tipo", "url", "sha256",
        "bytes_download", "bytes_instalado", "python", "backend",
        "licenca_url",
    ]
    faltando = [c for c in campos_obrigatorios if c not in dados]
    if faltando:
        raise ValueError(f"{origem}: campos obrigatórios ausentes: {faltando}")

    pid = str(dados["id"]).strip()
    if not pid:
        raise ValueError(f"{origem}: 'id' vazio")

    sha = str(dados.get("sha256", "")).strip()
    url = str(dados.get("url", "")).strip()
    indisponivel = bool(dados.get("indisponivel", False))
    motivo = dados.get("motivo_indisponivel")

    # Hash obrigatório para pacotes instaláveis; indisponíveis podem ter hash vazio
    if not indisponivel and not sha:
        raise ValueError(f"{origem} ({pid}): sha256 obrigatório para pacote instalável")
    if not indisponivel and not url:
        raise ValueError(f"{origem} ({pid}): url obrigatória para pacote instalável")

    try:
        bd = int(dados["bytes_download"])
        bi = int(dados["bytes_instalado"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{origem} ({pid}): bytes inválidos") from exc

    if not indisponivel and bd <= 0:
        raise ValueError(f"{origem} ({pid}): bytes_download deve ser > 0")

    deps = dados.get("dependencias", [])
    if not isinstance(deps, list):
        raise ValueError(f"{origem} ({pid}): dependencias deve ser lista")

    return PacoteInfo(
        id=pid,
        nome=str(dados["nome"]),
        versao=str(dados["versao"]),
        tipo=str(dados["tipo"]),
        descricao=str(dados.get("descricao", "")),
        url=url,
        sha256=sha,
        bytes_download=bd,
        bytes_instalado=bi,
        python=str(dados["python"]),
        backend=str(dados["backend"]),
        licenca_url=str(dados["licenca_url"]),
        licenca_nome=str(dados.get("licenca_nome", "")),
        dependencias=[str(d) for d in deps],
        voz_id=dados.get("voz_id"),
        indisponivel=indisponivel,
        motivo_indisponivel=motivo,
    )


def carregar_manifesto(caminho: Path | None = None) -> dict[str, PacoteInfo]:
    """Carrega todos os pacotes de um arquivo de manifesto JSON.

    Args:
        caminho: arquivo JSON específico; se None, lê config/pacotes/vozes.json.

    Returns:
        Dict mapeando id → PacoteInfo.

    Raises:
        FileNotFoundError: arquivo não existe.
        ValueError: JSON inválido ou pacote malformado.
    """
    alvo = caminho or (RAIZ_CONFIG / "vozes.json")
    if not alvo.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {alvo}")

    texto = alvo.read_text(encoding="utf-8")
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido em {alvo}: {exc}") from exc

    if not isinstance(dados, dict):
        raise ValueError(f"{alvo}: raiz deve ser objeto JSON")

    schema = dados.get("schema")
    if schema != 1:
        raise ValueError(f"{alvo}: schema desconhecido: {schema}")

    lista = dados.get("pacotes")
    if not isinstance(lista, list):
        raise ValueError(f"{alvo}: 'pacotes' deve ser lista")

    resultado: dict[str, PacoteInfo] = {}
    for i, item in enumerate(lista):
        if not isinstance(item, dict):
            raise ValueError(f"{alvo}: item {i} não é objeto")
        pkg = _validar_pacote_raw(item, f"{alvo}[{i}]")
        if pkg.id in resultado:
            raise ValueError(f"{alvo}: id duplicado '{pkg.id}'")
        resultado[pkg.id] = pkg

    log.info("manifesto carregado: %d pacotes de %s", len(resultado), alvo.name)
    return resultado


def validar_pacote(pacote: PacoteInfo) -> list[str]:
    """Verifica consistência de um pacote; devolve lista de problemas (vazia = ok)."""
    problemas: list[str] = []
    if not pacote.id:
        problemas.append("id vazio")
    if not pacote.nome:
        problemas.append("nome vazio")
    if pacote.tipo not in ("motor", "voz", "reuniao"):
        problemas.append(f"tipo desconhecido: {pacote.tipo}")
    if not pacote.indisponivel:
        if not pacote.sha256:
            problemas.append("sha256 ausente em pacote instalável")
        if not pacote.url:
            problemas.append("url ausente em pacote instalável")
        if pacote.bytes_download <= 0:
            problemas.append("bytes_download <= 0 em pacote instalável")
    if pacote.tipo == "voz" and not pacote.voz_id:
        problemas.append("pacote de voz sem voz_id")
    if pacote.tipo == "voz" and not pacote.dependencias:
        problemas.append("pacote de voz sem dependências (deve depender do motor)")
    return problemas