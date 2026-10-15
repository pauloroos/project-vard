"""Contratos do cérebro próprio: pedidos, eventos e estados.

IDs de sessão são atribuídos pelo núcleo; pedido repetido com mesmo ID e corpo
devolve o existente, corpo diferente dá 409. Eventos carregam seq crescente por
pedido; estado não é texto falado. Persistência em arquivos atômicos dentro de
VARD_DADOS/cerebro/.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Origem(str, enum.Enum):
    VOZ = "voz"
    PAINEL = "painel"
    TELEGRAM = "telegram"


class EstadoPedido(str, enum.Enum):
    NA_FILA = "na_fila"
    EXECUTANDO = "executando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    CANCELADO = "cancelado"


class TipoEvento(str, enum.Enum):
    ESTADO = "estado"
    TEXTO = "texto"
    FERRAMENTA = "ferramenta"
    RESERVA = "reserva"
    FIM = "fim"
    ERRO = "erro"


@dataclass(frozen=True)
class Pedido:
    pedido_id: str
    sessao_id: str
    origem: Origem
    texto: str
    imagem: bytes | None = None


@dataclass
class EventoPedido:
    pedido_id: str
    sessao_id: str
    seq: int
    tipo: TipoEvento
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass
class EstadoPedidoInfo:
    estado: EstadoPedido
    pedido_id: str
    sessao_id: str
    ultimo_seq: int = 0
    resposta: str | None = None
    erro: str | None = None
    provedor_usado: str | None = None
    tarefas: list[str] = field(default_factory=list)