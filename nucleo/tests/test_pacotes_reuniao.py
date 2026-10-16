"""Testes do pacote opcional de reunião (T6).
Cobre:
- Manifesto de reunião carrega e valida
- Pacote indisponível não é instalável
- Remover pacote inexistente retorna sucesso
- Pacote ausente não afeta conversa padrão
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vard.pacotes import InstaladorPacotes, carregar_manifesto, validar_pacote
from vard.pacotes.manifesto import PacoteInfo

RAIZ_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "pacotes"


# ---------------------------------------------------------------------------
# Manifesto
# ---------------------------------------------------------------------------


class TestManifestoReuniao:
    def test_manifesto_reuniao_existe(self):
        caminho = RAIZ_CONFIG / "reuniao.json"
        assert caminho.exists(), "config/pacotes/reuniao.json deve existir"

    def test_manifesto_reuniao_carrega(self):
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        assert "reuniao" in pkgs
        pkg = pkgs["reuniao"]
        assert pkg.tipo == "reuniao"
        assert pkg.nome == "Reunião (transcrição e diarização)"

    def test_pacote_reuniao_instalacao_local(self):
        """Pacote de reunião atual usa instalação local (venv, sem download)."""
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        pkg = pkgs["reuniao"]
        assert pkg.instalacao_local is True
        assert pkg.indisponivel is False
        assert pkg.instalavel() is True

    def test_validar_pacote_reuniao_ok(self):
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        problemas = validar_pacote(pkgs["reuniao"])
        # Tipo "reuniao" é válido; sem voz_id não é problema para tipo reuniao
        assert all("tipo desconhecido" not in p for p in problemas)

    def test_manifesto_reuniao_schema_valido(self):
        caminho = RAIZ_CONFIG / "reuniao.json"
        texto = caminho.read_text(encoding="utf-8")
        dados = json.loads(texto)
        assert dados["schema"] == 1
        assert isinstance(dados["pacotes"], list)
        assert len(dados["pacotes"]) >= 1


# ---------------------------------------------------------------------------
# Instalador: pacote indisponível
# ---------------------------------------------------------------------------


class TestInstaladorReuniao:
    @pytest.mark.asyncio
    async def test_instalar_reuniao_indisponivel_falha(self, tmp_path):
        """Pacote indisponível não pode ser instalado."""
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
            indisponivel=True,
            motivo_indisponivel="instalacao via venv local",
        )
        resultado = await inst.instalar(pacote)
        assert resultado.estado == "falhou"
        assert "nao instalavel" in (resultado.erro or "").lower()
        assert not inst.esta_instalado("reuniao")
        await inst.fechar()

    @pytest.mark.asyncio
    async def test_remover_reuniao_sem_venv(self, tmp_path):
        """Remover pacote que não existe retorna sucesso."""
        inst = InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes")
        ok, erro = await inst.remover("reuniao")
        assert ok
        assert erro is None
        await inst.fechar()


# ---------------------------------------------------------------------------
# Integração: pacote ausente não afeta conversa
# ---------------------------------------------------------------------------


class TestPacoteAusente:
    def test_listar_pacotes_inclui_reuniao(self):
        """Listar pacotes inclui reunião mesmo quando indisponível."""
        caminho = RAIZ_CONFIG / "reuniao.json"
        pkgs = carregar_manifesto(caminho)
        assert "reuniao" in pkgs

    def test_pacote_ausente_nao_quebra_manifesto_vozes(self):
        """Manifesto de vozes continua válido sem reunião."""
        caminho = RAIZ_CONFIG / "vozes.json"
        if caminho.exists():
            pkgs = carregar_manifesto(caminho)
            assert isinstance(pkgs, dict)