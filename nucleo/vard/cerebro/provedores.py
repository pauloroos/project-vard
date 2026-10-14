"""Adaptadores de provedores do cérebro: contratos e fábrica para inferência.

Cada adaptador implementa `inferir(mensagens, ferramentas)` e devolve um
`ResultadoInferencia`. A fábrica escolhe o adaptador pelo nome do provedor
cadastrado; nomes desconhecidos levantam ValueError. Nenhum adaptador faz
chamada real nesta versão — apenas registra a interface para que a T3/T5
conecte ao motor/API real.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResultadoInferencia:
    texto: str | None = None
    chamadas_ferramenta: list[dict[str, Any]] = field(default_factory=list)
    provedor: str = ""
    erro: str | None = None
    ttft_ms: int | None = None

    @property
    def ok(self) -> bool:
        return self.erro is None


class AdaptadorProvedor(abc.ABC):
    """Interface mínima que todo adaptador de provedor deve implementar."""

    nome: str = ""

    @abc.abstractmethod
    async def inferir(
        self,
        mensagens: list[dict[str, Any]],
        ferramentas: list[dict[str, Any]] | None = None,
    ) -> ResultadoInferencia: ...


class AdaptadorFalso(AdaptadorProvedor):
    """Adaptador de teste: devolve resposta fixa sem chamar nada externo."""

    nome = "falso"

    def __init__(self, resposta: str = "ok", falhar: bool = False) -> None:
        self._resposta = resposta
        self._falhar = falhar

    async def inferir(
        self,
        mensagens: list[dict[str, Any]],
        ferramentas: list[dict[str, Any]] | None = None,
    ) -> ResultadoInferencia:
        if self._falhar:
            return ResultadoInferencia(provedor=self.nome, erro="falha_simulada")
        return ResultadoInferencia(texto=self._resposta, provedor=self.nome)


_REGISTRO: dict[str, type[AdaptadorProvedor]] = {
    "falso": AdaptadorFalso,
}


def registrar(nome: str, cls: type[AdaptadorProvedor]) -> None:
    """Registra um adaptador pelo nome. Substitui se já existir."""
    if not nome or not isinstance(nome, str):
        raise ValueError(f"nome de provedor inválido: {nome!r}")
    _REGISTRO[nome] = cls


def obter(nome: str, **kwargs: Any) -> AdaptadorProvedor:
    """Instancia o adaptador registrado pelo nome. Desconhecido dá ValueError."""
    cls = _REGISTRO.get(nome)
    if cls is None:
        raise ValueError(f"provedor desconhecido: {nome!r}")
    return cls(**kwargs)


def listar_provedores() -> list[str]:
    """Devolve os nomes dos provedores registrados."""
    return sorted(_REGISTRO.keys())