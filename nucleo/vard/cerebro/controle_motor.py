"""Interface injetável para coordenação global de motores locais (T5).

Contrato:
- Bloqueia novas inferências locais enquanto troca ocorre.
- Espera/cancela inferências ativas antes de descarregar.
- Descarrega o residente controlado; se falhar, NÃO carrega o novo.
- Carrega e confere prontidão/contexto do novo modelo.
- Não toca em processos/modelos externos não controlados.
- LM Studio enumera instâncias e descarrega por instance_id.
- llama-server usa controle documentado (não payload copiado do LM Studio).
- Reserva de API não exige segunda carga local.

Esta é uma interface abstrata; implementações reais (LM Studio, llama-server)
serão entregues na Parte B. Para testes e desenvolvimento, use ControleMotorFalso.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EstadoMotor:
    """Snapshot do estado de um motor local."""
    modelo_carregado: str | None = None
    pronto: bool = False
    inferencias_ativas: int = 0
    bloqueado: bool = False


class ControleMotorLocal(ABC):
    """Interface abstrata para coordenação de motores locais."""

    @abstractmethod
    async def obter_estado(self) -> EstadoMotor:
        """Retorna snapshot atual do motor."""
        ...

    @abstractmethod
    async def bloquear_inferencias(self) -> None:
        """Bloqueia novas inferências; inferências ativas continuam até concluir."""
        ...

    @abstractmethod
    async def desbloquear_inferencias(self) -> None:
        """Libera o bloqueio de novas inferências."""
        ...

    @abstractmethod
    async def esperar_ativas(self, timeout_s: float = 30.0) -> bool:
        """Espera inferências ativas concluírem. Retorna True se todas terminaram."""
        ...

    @abstractmethod
    async def cancelar_ativas(self) -> int:
        """Cancela inferências ativas. Retorna número de cancelamentos."""
        ...

    @abstractmethod
    async def descarregar(self) -> bool:
        """Descarrega o modelo residente. Retorna True se sucesso."""
        ...

    @abstractmethod
    async def carregar(self, modelo: str, contexto: dict[str, Any] | None = None) -> bool:
        """Carrega um modelo. Retorna True se sucesso e pronto."""
        ...

    @abstractmethod
    async def confirmar_prontidao(self) -> bool:
        """Confirma que o motor está pronto para inferência."""
        ...


class ControleMotorFalso(ControleMotorLocal):
    """Implementação falsa para testes — sem processos reais."""

    def __init__(self) -> None:
        self._estado = EstadoMotor(modelo_carregado=None, pronto=False)
        self._lock = asyncio.Lock()
        self._cronologia: list[str] = []
        self._cargas: int = 0
        self._descargas: int = 0

    @property
    def cronologia(self) -> list[str]:
        return list(self._cronologia)

    @property
    def total_cargas(self) -> int:
        return self._cargas

    async def obter_estado(self) -> EstadoMotor:
        async with self._lock:
            return EstadoMotor(
                modelo_carregado=self._estado.modelo_carregado,
                pronto=self._estado.pronto,
                inferencias_ativas=self._estado.inferencias_ativas,
                bloqueado=self._estado.bloqueado,
            )

    async def bloquear_inferencias(self) -> None:
        async with self._lock:
            self._estado.bloqueado = True
            self._cronologia.append("bloqueado")

    async def desbloquear_inferencias(self) -> None:
        async with self._lock:
            self._estado.bloqueado = False
            self._cronologia.append("desbloqueado")

    async def esperar_ativas(self, timeout_s: float = 30.0) -> bool:
        async with self._lock:
            self._cronologia.append("esperar_ativas")
            return self._estado.inferencias_ativas == 0

    async def cancelar_ativas(self) -> int:
        async with self._lock:
            n = self._estado.inferencias_ativas
            self._estado.inferencias_ativas = 0
            self._cronologia.append(f"cancelar_ativas:{n}")
            return n

    async def descarregar(self) -> bool:
        async with self._lock:
            if self._estado.modelo_carregado is None:
                self._cronologia.append("descarregar:vazio")
                return True
            self._descargas += 1
            self._estado.modelo_carregado = None
            self._estado.pronto = False
            self._cronologia.append("descarregar:ok")
            return True

    async def carregar(self, modelo: str, contexto: dict[str, Any] | None = None) -> bool:
        async with self._lock:
            self._cargas += 1
            self._estado.modelo_carregado = modelo
            self._estado.pronto = True
            self._cronologia.append(f"carregar:{modelo}")
            return True

    async def confirmar_prontidao(self) -> bool:
        async with self._lock:
            self._cronologia.append("confirmar_prontidao")
            return self._estado.pronto

    async def trocar_modelo(self, modelo: str) -> bool:
        """Troca atômica: bloqueia → espera → descarrega → carrega → confirma → desbloqueia.
        Lock de escopo amplo impede intercalação entre sessões concorrentes.
        Se o modelo já estiver carregado, pula a troca (idempotente)."""
        async with self._lock:
            # Idempotência: se já estamos no modelo alvo, não faz nada
            if self._estado.modelo_carregado == modelo and self._estado.pronto:
                self._cronologia.append(f"troca_redundante:{modelo}")
                return True
            self._estado.bloqueado = True
            self._cronologia.append("bloqueado")
            self._cronologia.append("esperar_ativas")
            # Descarrega
            if self._estado.modelo_carregado is not None:
                self._descargas += 1
                self._estado.modelo_carregado = None
                self._estado.pronto = False
                self._cronologia.append("descarregar:ok")
            else:
                self._cronologia.append("descarregar:vazio")
            # Carrega novo modelo
            self._cargas += 1
            self._estado.modelo_carregado = modelo
            self._estado.pronto = True
            self._cronologia.append(f"carregar:{modelo}")
            self._cronologia.append("confirmar_prontidao")
            self._estado.bloqueado = False
            self._cronologia.append("desbloqueado")
            return True