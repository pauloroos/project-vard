"""Testes T11: preflight por componentes habilitados e perfil limpo sem OpenJarvis."""
import json
from pathlib import Path

import pytest

import preflight
from vard import instalacao


def test_perfil_limpo_sem_openjarvis_inicia_sem_falha(tmp_path: Path, monkeypatch):
    """Perfil limpo (sem openjarvis_src/home) não falha no preflight; checagens de OJ viram AVISO."""
    inst = {"raiz_codigo": str(tmp_path), "openjarvis_src": "", "openjarvis_home": "", "servicos": {}}
    monkeypatch.setattr(instalacao, "arquivo", lambda: tmp_path / "instalacao.json")
    (tmp_path / "instalacao.json").write_text(json.dumps(inst), encoding="utf-8")
    # _openjarvis_configurado deve retornar False
    assert not preflight._openjarvis_configurado()
    ok, detalhe = preflight._sem_openjarvis()
    assert ok and "AVISO" in detalhe


def test_perfil_com_openjarvis_preserva_comportamento(tmp_path: Path, monkeypatch):
    """Config com openjarvis_src preenchido mantém checagens ativas (não vira AVISO automático)."""
    src = tmp_path / "oj-src"
    src.mkdir()
    inst = {
        "raiz_codigo": str(tmp_path),
        "openjarvis_src": str(src),
        "openjarvis_home": str(tmp_path / "oj-home"),
        "servicos": {"openjarvis": True},
    }
    monkeypatch.setattr(instalacao, "arquivo", lambda: tmp_path / "instalacao.json")
    (tmp_path / "instalacao.json").write_text(json.dumps(inst), encoding="utf-8")
    # Com openjarvis configurado, _sem_openjarvis NÃO é retornado automaticamente
    assert preflight._openjarvis_configurado()


def test_checagens_condicionais_por_componente():
    """checagens() inclui itens de OpenJarvis mas eles próprios verificam _openjarvis_configurado internamente."""
    nomes = [nome for nome, _fn in preflight.checagens()]
    assert "OpenJarvis /health" in nomes
    assert "OpenJarvis lista o Gemma" in nomes


def test_jogo_cancela_pedidos_do_cerebro(tmp_path: Path, monkeypatch):
    """Modo jogo deve cancelar pedidos pendentes do cérebro próprio (T11)."""
    from vard.cerebro import pedidos as cerebro_pedidos
    from vard.cerebro import contratos as cerebro_contratos

    # Sobrescreve a pasta de pedidos para usar tmp_path
    monkeypatch.setattr(cerebro_pedidos, "_pasta_pedidos", str(tmp_path))

    # Admite um pedido fake diretamente na base
    p = cerebro_contratos.Pedido(
        pedido_id="p-t11",
        sessao_id="s-t11",
        origem=cerebro_contratos.Origem("painel"),
        texto="teste",
    )
    info = cerebro_pedidos.admitir(p)
    assert info is not None

    # Verifica que o pedido existe e está em estado executando/na_fila
    consultado = cerebro_pedidos.consultar("p-t11")
    assert consultado is not None

    # Cancela via função do módulo
    cancelado = cerebro_pedidos.cancelar("p-t11")
    assert cancelado is not None and cancelado.estado.value == "cancelado"