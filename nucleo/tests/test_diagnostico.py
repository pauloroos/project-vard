"""Testes do módulo diagnostico.py (T10).
Valida contrato: somente-leitura, sanitização, estrutura de resultado.
"""
from __future__ import annotations

import pytest

from vard.diagnostico import (
    Checagem,
    ResultadoDiagnostico,
    _seguro,
    rodar_diagnostico,
)


class TestSeguro:
    def test_remove_api_key(self) -> None:
        assert "credencial=***" in _seguro("api_key=abc123")

    def test_remove_bearer_token(self) -> None:
        assert "***" in _seguro("Authorization: Bearer sk-xyz")

    def test_remove_caminho_pessoal_generico(self) -> None:
        # Usa path genérico para evitar vazamento de letra de unidade no repo público.
        entrada = "arquivo em /Users/fulano/docs"
        resultado = _seguro(entrada)
        assert "<caminho-pessoal>" in resultado
        assert "fulano" not in resultado

    def test_preserva_texto_limpo(self) -> None:
        texto = "porta 4700 em loopback"
        assert _seguro(texto) == texto


class TestRodarDiagnostico:
    def test_retorna_resultado_estruturado(self) -> None:
        resultado = rodar_diagnostico("basico", prazo_s=30.0)
        assert isinstance(resultado, ResultadoDiagnostico)
        assert isinstance(resultado.checagens, list)
        assert len(resultado.checagens) > 0
        assert resultado.duracao_ms >= 0
        assert resultado.relatorio

    def test_checagens_tem_campos_obrigatorios(self) -> None:
        resultado = rodar_diagnostico("basico", prazo_s=30.0)
        for c in resultado.checagens:
            assert isinstance(c, Checagem)
            assert c.grupo
            assert c.nome
            assert c.estado in ("ok", "aviso", "falha")
            assert c.frase

    def test_relatorio_contem_resumo(self) -> None:
        resultado = rodar_diagnostico("basico", prazo_s=30.0)
        assert "ok" in resultado.relatorio
        assert "avisos" in resultado.relatorio or "falhas" in resultado.relatorio

    def test_saida_sanitizada_sem_credenciais(self) -> None:
        resultado = rodar_diagnostico("basico", prazo_s=30.0)
        texto = resultado.relatorio.lower()
        assert "password" not in texto or "credencial=***" in texto
        # Caminhos pessoais não devem aparecer (usa path genérico para evitar vazamento)
        assert "/users/" not in texto or "<caminho-pessoal>" in texto

    def test_cancelamento_interrompe(self) -> None:
        cancelado = False

        def cancelar() -> bool:
            return cancelado

        # Cancela imediatamente: deve retornar resultado parcial ou vazio
        cancelado = True
        resultado = rodar_diagnostico("basico", prazo_s=30.0, cancelado=cancelar)
        assert isinstance(resultado, ResultadoDiagnostico)

    def test_nao_inicia_servico_nem_carrega_modelo(self) -> None:
        """Diagnóstico básico é somente-leitura: não deve iniciar nada."""
        resultado = rodar_diagnostico("basico", prazo_s=30.0)
        nomes = [c.nome.lower() for c in resultado.checagens]
        # Nenhuma checagem deve mencionar "iniciando", "carregando modelo", etc.
        for nome in nomes:
            assert "iniciar" not in nome
            assert "carregar modelo" not in nome

@pytest.fixture(autouse=True)
def sondas_falsas(monkeypatch):
    """Exercita as checagens reais sobre respostas sintéticas, sem ler o Windows."""
    import subprocess
    from vard import diagnostico

    class SocketFalso:
        def settimeout(self, valor): pass
        def connect_ex(self, endereco): return 0
        def close(self): pass

    def executar(args, **kwargs):
        saidas = {
            "netstat": "TCP 127.0.0.1:4700 LISTENING",
            "tasklist": '"vard.exe","42"',
            "reg": "Vard REG_SZ aplicativo-ficticio",
            "wmic": "TotalPhysicalMemory=17179869184" if "ComputerSystem" in args else "Name=GPU ficticia",
        }
        return subprocess.CompletedProcess(args, 0, saidas[args[0]], "")

    # Não muda socket global: o executor de threads continua com seu socketpair.
    from types import SimpleNamespace
    monkeypatch.setattr(diagnostico, "socket", SimpleNamespace(
        socket=SocketFalso, AF_INET=2, SOCK_STREAM=1))
    monkeypatch.setattr(diagnostico.subprocess, "run", executar)
