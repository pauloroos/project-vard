"""Capacidade do enxuto e reabertura do supervisor (T17b da 0.8).

Regra C5: o enxuto só roda se as ferramentas que a CLI informa no evento de
início da sessão contêm as do cérebro local; se faltar algo, o supervisor
reabre a sessão SEM enxuto e registra o aviso que aparece no /status.
Nenhum executável real roda aqui: a CLI é a cli_viva.py da T16 dentro do tmp
(a guarda do PC real bloqueia claude/agy).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import server
from vard.cerebro import cli_capacidade
from vard.cerebro.cli_processos import ProvedorCli, SupervisorCli

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLI_VIVA = str(FIXTURES_DIR / "cli_viva.py")

# Ferramentas do cérebro local citadas no produto (spec C8): hora e tarefa.
LOCAIS = ["hora_atual", "disparar_tarefa"]


@pytest.fixture(autouse=True)
def avisos_limpos():
    cli_capacidade.limpar_avisos()
    yield
    cli_capacidade.limpar_avisos()


@pytest.fixture
def argv_vivo(monkeypatch) -> List[str]:
    """argv_cli vira a CLI viva da T16; devolve a lista de tipos abertos."""
    import vard.cerebro.cli_processos as mod

    aberturas: List[str] = []

    def _argv(provedor: ProvedorCli, pasta: Path) -> List[str]:
        aberturas.append(provedor.tipo)
        dialeto = "claude" if provedor.tipo == "cli-claude" else "agy"
        return [sys.executable, CLI_VIVA, "--dialeto", dialeto]

    monkeypatch.setattr(mod, "argv_cli", _argv)
    return aberturas


def _provedor_enxuto() -> ProvedorCli:
    return ProvedorCli(id="cli_claude", tipo="cli-claude", modelo="m-teste", yolo=True, enxuto=True)


class TestVerificarEnxuto:
    def test_enxuto_aceito_quando_contem_todas(self):
        ok, faltando = cli_capacidade.verificar_enxuto(
            ferramentas_cli=["Bash", "Read", "Write", "hora_atual", "disparar_tarefa"],
            ferramentas_local=LOCAIS,
        )
        assert ok is True
        assert faltando == []

    def test_enxuto_recusado_lista_o_que_falta(self):
        ok, faltando = cli_capacidade.verificar_enxuto(
            ferramentas_cli=["Bash", "Read"],
            ferramentas_local=LOCAIS,
        )
        assert ok is False
        assert faltando == LOCAIS

    def test_enxuto_com_cli_sem_ferramentas_recusa(self):
        ok, faltando = cli_capacidade.verificar_enxuto(
            ferramentas_cli=[],
            ferramentas_local=["hora_atual"],
        )
        assert ok is False
        assert faltando == ["hora_atual"]


class TestSupervisorEnxuto:
    @pytest.mark.asyncio
    async def test_supervisor_reabre_sem_enxuto_quando_falta(self, tmp_path: Path, argv_vivo):
        """Falta ferramenta local: a sessão é reabre sem enxuto e o aviso é registrado."""
        sup = SupervisorCli(base_dados=tmp_path / "dados", ferramentas_locais=LOCAIS)
        try:
            await sup.canal(_provedor_enxuto(), "sess-enxuto")

            assert len(argv_vivo) == 2                    # abriu enxuto e reabriu sem
            assert len(sup.pids()) == 1                   # só o reaberto vive
            assert sup.enxuto("cli_claude", "sess-enxuto") is False

            avisos = cli_capacidade.avisos()
            assert len(avisos) == 1
            for nome in LOCAIS:
                assert nome in avisos[0]
        finally:
            await sup.encerrar_tudo()

    @pytest.mark.asyncio
    async def test_supervisor_mantem_enxuto_quando_contem_todas(self, tmp_path: Path, argv_vivo):
        """CLI com as ferramentas todas: a sessão segue enxuto, sem reabertura."""
        sup = SupervisorCli(base_dados=tmp_path / "dados", ferramentas_locais=["Bash", "Read"])
        try:
            await sup.canal(_provedor_enxuto(), "sess-ok")

            assert len(argv_vivo) == 1                    # uma abertura só
            assert len(sup.pids()) == 1
            assert sup.enxuto("cli_claude", "sess-ok") is True
            assert cli_capacidade.avisos() == []
        finally:
            await sup.encerrar_tudo()

    @pytest.mark.asyncio
    async def test_enxuto_aceito_preserva_o_evento_de_inicio_para_o_adaptador(self, tmp_path: Path, argv_vivo):
        """A conferência lê o início, mas o adaptador ainda recebe a linha do init."""
        sup = SupervisorCli(base_dados=tmp_path / "dados", ferramentas_locais=["Bash", "Read"])
        try:
            canal = await sup.canal(_provedor_enxuto(), "sess-integro")

            primeira = None
            async for linha in canal.linhas():
                primeira = linha
                break

            assert primeira is not None
            init = json.loads(primeira)
            assert init.get("type") == "system"
            assert init.get("subtype") == "init"
            assert init.get("tools") == ["Bash", "Read", "Write"]
        finally:
            await sup.encerrar_tudo()

    @pytest.mark.asyncio
    async def test_sessao_sem_enxuto_nao_confere_init(self, tmp_path: Path, argv_vivo):
        """enxuto=False (padrão) não abre a conferência: uma abertura e nada de aviso."""
        sup = SupervisorCli(base_dados=tmp_path / "dados", ferramentas_locais=LOCAIS)
        try:
            prov = ProvedorCli(id="cli_claude", tipo="cli-claude", modelo="m-teste", yolo=True)
            await sup.canal(prov, "sess-comum")

            assert len(argv_vivo) == 1
            assert sup.enxuto("cli_claude", "sess-comum") is False
            assert cli_capacidade.avisos() == []
        finally:
            await sup.encerrar_tudo()


@respx.mock
def test_aviso_do_enxuto_aparece_no_status():
    """O aviso registrado pelo supervisor aparece em GET /status."""
    cli_capacidade.registrar_aviso("enxuto recusado em cli_claude: falta hora_atual")
    respx.get("http://127.0.0.1:8000/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    respx.get("http://127.0.0.1:1234/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get("http://127.0.0.1:4720/status").mock(side_effect=httpx.ConnectError("x"))

    cliente = TestClient(server.app, base_url="http://127.0.0.1:4700")
    r = cliente.get("/status")

    assert r.status_code == 200
    assert r.json()["cli_enxuto"]["avisos"] == ["enxuto recusado em cli_claude: falta hora_atual"]
