"""Monitor de recursos do Vard (0.9.4 leve): prova da rota /recursos com processos falsos."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class ProcessoFalso:
    """Dublê de psutil.Process para testes sem dependência de processos reais."""

    def __init__(self, pid: int, nome: str = "vard.exe", rss_mb: float = 100.0, cpu: float = 5.0):
        self.pid = pid
        self._nome = nome
        self._rss = int(rss_mb * 1024 * 1024)
        self._cpu = cpu
        self._filhos: list[ProcessoFalso] = []

    def status(self) -> str:
        return "running"

    def memory_info(self):
        class MemInfo:
            rss = self._rss
        return MemInfo()

    def cpu_percent(self, interval: float = 0.0) -> float:
        return self._cpu

    def children(self, recursive: bool = False):
        return list(self._filhos)


@pytest.fixture
def pids_registrados(tmp_path: Path, monkeypatch):
    """Cria pasta pids/ fictícia e aponta config.pasta_dados() para ela."""
    pasta_pids = tmp_path / "pids"
    pasta_pids.mkdir()
    (pasta_pids / "widget.pid").write_text("1001\n", encoding="utf-8")
    (pasta_pids / "nucleo.pid").write_text("2001\n", encoding="utf-8")
    (pasta_pids / "voz.pid").write_text("3001\n", encoding="utf-8")

    from vard import config as modulo_config
    monkeypatch.setattr(modulo_config, "pasta_dados", lambda: tmp_path)
    return pasta_pids


@pytest.fixture
def processos_falsos(monkeypatch):
    """Substitui psutil.Process por dublês controláveis."""
    from vard import recursos as mod_recursos

    mapa = {
        1001: ProcessoFalso(1001, "vard.exe", rss_mb=200.0, cpu=3.0),
        2001: ProcessoFalso(2001, "python.exe", rss_mb=150.0, cpu=2.0),
        3001: ProcessoFalso(3001, "python.exe", rss_mb=500.0, cpu=1.0),
    }

    def processo_seguro(pid: int):
        return mapa.get(pid)

    monkeypatch.setattr(mod_recursos, "_processo_seguro", processo_seguro)
    # Desativa detecção de XTTS e externos para isolar o teste
    monkeypatch.setattr(mod_recursos, "_detectar_xtts_carregado", lambda pids: False)
    monkeypatch.setattr(mod_recursos, "_detectar_externos", lambda: [])
    return mapa


def test_coletar_recursos_retorna_componentes(pids_registrados, processos_falsos):
    from vard import recursos as mod_recursos

    resultado = mod_recursos.coletar_recursos()
    assert "componentes" in resultado
    assert "total_memoria_mb" in resultado
    nomes = [c["nome"] for c in resultado["componentes"]]
    assert "Widget" in nomes
    assert "Núcleo" in nomes
    assert "Voz" in nomes
    assert resultado["total_memoria_mb"] > 0


def test_coletar_recursos_sem_pids_registrados(tmp_path, monkeypatch):
    """Sem pasta pids/, devolve estrutura válida com componentes vazios."""
    from vard import config as modulo_config
    from vard import recursos as mod_recursos

    monkeypatch.setattr(modulo_config, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(mod_recursos, "_detectar_xtts_carregado", lambda pids: False)
    monkeypatch.setattr(mod_recursos, "_detectar_externos", lambda: [])

    resultado = mod_recursos.coletar_recursos()
    assert isinstance(resultado["componentes"], list)
    assert resultado["total_memoria_mb"] >= 0


def test_rota_recursos_no_servidor(pids_registrados, processos_falsos):
    """Prova integrada: GET /recursos devolve 200 com JSON válido."""
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as c:
        r = c.get("/recursos", headers={"host": "127.0.0.1"})
        assert r.status_code == 200
        dados = r.json()
        assert "componentes" in dados
        assert "total_memoria_mb" in dados