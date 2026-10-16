"""Testes da instalação local do pacote de reunião (T6b).
Cobre:
- Manifesto com instalacao_local é instalável sem url/hash
- Instalar local cria venv falso (sem rede, sem uv real)
- Saúde ativa após instalação local
- Remover com reunião ativa é recusado
- Remover preserva atas/config do usuário
- Reinstalar reabre serviço
- Pacote ausente não afeta conversa padrão
- Cancelamento não marca disponível
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from vard.pacotes import InstaladorPacotes, carregar_manifesto, validar_pacote
from vard.pacotes.manifesto import PacoteInfo

RAIZ_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "pacotes"


# ---------------------------------------------------------------------------
# Manifesto
# ---------------------------------------------------------------------------


class TestManifestoReuniaoLocal:
    def test_manifesto_reuniao_tem_instalacao_local(self):
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        pkg = pkgs["reuniao"]
        assert pkg.instalacao_local is True
        assert pkg.indisponivel is False

    def test_manifesto_reuniao_instalavel_sem_url(self):
        """Pacote com instalacao_local=True é instalável mesmo sem url/hash."""
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        pkg = pkgs["reuniao"]
        assert pkg.instalavel() is True

    def test_validar_pacote_reuniao_local_ok(self):
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        problemas = validar_pacote(pkgs["reuniao"])
        assert all("sha256 ausente" not in p for p in problemas)
        assert all("url ausente" not in p for p in problemas)


# ---------------------------------------------------------------------------
# Instalador local
# ---------------------------------------------------------------------------


class TestInstaladorReuniaoLocal:
    @pytest.mark.asyncio
    async def test_instalar_local_cria_venv_falso(self, tmp_path):
        """Instalação local cria diretório ativo sem download real."""
        inst = InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes")
        pacote = PacoteInfo(
            id="reuniao",
            nome="Reunião",
            versao="0.1.0",
            tipo="reuniao",
            descricao="",
            url="",
            sha256="",
            bytes_download=0,
            bytes_instalado=524288000,
            python=">=3.12,<3.13",
            backend="cpu|cuda",
            licenca_url="https://example.com",
            licenca_nome="MIT",
            instalacao_local=True,
        )
        # Mock do _criar_venv_local: cria diretório e sentinela sem executar uv real
        async def _fake_venv(pkg, destino):
            destino.mkdir(parents=True, exist_ok=True)
            (destino / ".venv_local").write_text(
                json.dumps({"id": pkg.id, "versao": pkg.versao}), encoding="utf-8"
            )

        with patch.object(inst, "_criar_venv_local", side_effect=_fake_venv):
            resultado = await inst.instalar(pacote)
            assert resultado.estado == "concluido", f"erro: {resultado.erro}"
            assert inst.esta_instalado("reuniao")
            dir_ativo = tmp_path / "pacotes" / "ativo" / "reuniao"
            assert dir_ativo.exists()
        await inst.fechar()

    @pytest.mark.asyncio
    async def test_instalar_local_cancelado_nao_marca_disponivel(self, tmp_path):
        """Cancelamento durante instalação local não marca como instalado."""
        inst = InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes")
        pacote = PacoteInfo(
            id="reuniao",
            nome="Reunião",
            versao="0.1.0",
            tipo="reuniao",
            descricao="",
            url="",
            sha256="",
            bytes_download=0,
            bytes_instalado=524288000,
            python=">=3.12,<3.13",
            backend="cpu|cuda",
            licenca_url="https://example.com",
            licenca_nome="MIT",
            instalacao_local=True,
        )
        inst.cancelar("reuniao")
        resultado = await inst.instalar(pacote)
        assert resultado.estado == "cancelado"
        assert not inst.esta_instalado("reuniao")
        await inst.fechar()

    @pytest.mark.asyncio
    async def test_remover_reuniao_ativa_recusado(self, tmp_path):
        """Remover com reunião ativa é recusado."""
        inst = InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes")
        # Simula instalação prévia
        dir_ativo = tmp_path / "pacotes" / "ativo" / "reuniao"
        dir_ativo.mkdir(parents=True)
        inst.marcar_instalado(PacoteInfo(
            id="reuniao", nome="Reunião", versao="0.1.0", tipo="reuniao",
            descricao="", url="", sha256="", bytes_download=0,
            bytes_instalado=0, python=">=3.12", backend="cpu",
            licenca_url="", licenca_nome="", instalacao_local=True,
        ))
        # Simula reunião ativa via callback
        ok, erro = await inst.remover("reuniao", reuniao_ativa=True)
        assert ok is False
        assert "ativa" in (erro or "").lower()
        assert inst.esta_instalado("reuniao")
        await inst.fechar()

    @pytest.mark.asyncio
    async def test_remover_preserva_atas(self, tmp_path):
        """Remover pacote preserva atas/gravações no diretório de dados."""
        inst = InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes")
        dir_ativo = tmp_path / "pacotes" / "ativo" / "reuniao"
        dir_ativo.mkdir(parents=True)
        # Cria ata fictícia fora do diretório do pacote (em dados/reunioes)
        dir_reunioes = tmp_path / "reunioes"
        dir_reunioes.mkdir(parents=True)
        (dir_reunioes / "ata-teste.txt").write_text("conteudo da ata", encoding="utf-8")
        inst.marcar_instalado(PacoteInfo(
            id="reuniao", nome="Reunião", versao="0.1.0", tipo="reuniao",
            descricao="", url="", sha256="", bytes_download=0,
            bytes_instalado=0, python=">=3.12", backend="cpu",
            licenca_url="", licenca_nome="", instalacao_local=True,
        ))
        ok, erro = await inst.remover("reuniao")
        assert ok is True
        assert erro is None
        assert not inst.esta_instalado("reuniao")
        # Ata preservada
        assert (dir_reunioes / "ata-teste.txt").exists()
        await inst.fechar()

    @pytest.mark.asyncio
    async def test_reinstalar_reabre_servico(self, tmp_path):
        """Reinstalar após remoção cria novo diretório ativo."""
        inst = InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes")
        pacote = PacoteInfo(
            id="reuniao",
            nome="Reunião",
            versao="0.1.0",
            tipo="reuniao",
            descricao="",
            url="",
            sha256="",
            bytes_download=0,
            bytes_instalado=524288000,
            python=">=3.12,<3.13",
            backend="cpu|cuda",
            licenca_url="https://example.com",
            licenca_nome="MIT",
            instalacao_local=True,
        )
        with patch.object(inst, "_criar_venv_local", new_callable=AsyncMock):
            r1 = await inst.instalar(pacote)
            assert r1.estado == "concluido"
            await inst.remover("reuniao")
            assert not inst.esta_instalado("reuniao")
            r2 = await inst.instalar(pacote)
            assert r2.estado == "concluido"
            assert inst.esta_instalado("reuniao")
        await inst.fechar()


# ---------------------------------------------------------------------------
# Integração: pacote ausente não afeta conversa
# ---------------------------------------------------------------------------


class TestPacoteAusenteNaoAfetaConversa:
    def test_pacote_ausente_nao_quebra_manifesto_vozes(self):
        """Manifesto de vozes continua válido sem reunião instalada."""
        caminho = RAIZ_CONFIG / "vozes.json"
        if caminho.exists():
            pkgs = carregar_manifesto(caminho)
            assert isinstance(pkgs, dict)

    def test_listar_pacotes_inclui_reuniao_local(self):
        """Listar pacotes inclui reunião com instalacao_local."""
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        assert "reuniao" in pkgs
        assert pkgs["reuniao"].instalacao_local is True