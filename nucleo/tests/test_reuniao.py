"""T7b — Teste da função retomar() em nucleo/vard/reuniao.py.

Verifica que retomar() inicia novo segmento após voltar do modo jogo,
sem reabrir arquivo anterior, registrando vínculo/intervalo no log.
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Adiciona o caminho do núcleo para importar o módulo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vard.reuniao import retomar, FRASE_INICIO


class FakeResponse:
    """Resposta falsa para simular o serviço 4720."""
    def __init__(self, data=None, status_code=200):
        self.data = data or {}
        self.status_code = status_code

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_retomar_com_intervalo_registra_vinculo():
    """retomar() com resposta válida deve retornar mensagem com intervalo."""
    with patch("vard.reuniao._post") as mock_post:
        mock_post.return_value = {"intervalo_s": 45}
        resultado = retomar(pasta_anterior="/dados/reuniao/2026-10-15")
        assert "Novo segmento iniciado" in resultado
        assert "45s sem gravação" in resultado
        mock_post.assert_called_once_with(
            "/retomar", {"pasta_anterior": "/dados/reuniao/2026-10-15"}
        )


def test_retomar_sem_pasta_anterior():
    """retomar() sem pasta_anterior deve chamar /retomar sem payload."""
    with patch("vard.reuniao._post") as mock_post:
        mock_post.return_value = {}
        resultado = retomar()
        assert FRASE_INICIO in resultado
        mock_post.assert_called_once_with("/retomar", None)


def test_retomar_fallback_quando_404():
    """retomar() deve fazer fallback para /iniciar se /retomar não existir."""
    from vard.reuniao import Frase

    with patch("vard.reuniao._post") as mock_post:
        # Primeira chamada (/retomar) falha com 404; segunda (/iniciar) succeeds
        mock_post.side_effect = [Frase("404 not found"), {"ok": True}]
        resultado = retomar(pasta_anterior="/tmp/reuniao")
        assert FRASE_INICIO in resultado
        assert "novo segmento pós-jogo" in resultado
        assert mock_post.call_count == 2


def test_retomar_nao_reabre_arquivo_anterior():
    """retomar() nunca deve passar caminho de arquivo anterior para append."""
    with patch("vard.reuniao._post") as mock_post:
        mock_post.return_value = {"intervalo_s": 10}
        retomar(pasta_anterior="/dados/antigo")
        # O payload é apenas a pasta_anterior, nunca um arquivo específico
        call_args = mock_post.call_args
        assert call_args[0][0] == "/retomar"
        payload = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("json")
        # Payload deve ser dict com pasta_anterior ou None, nunca path de arquivo
        if payload is not None:
            assert isinstance(payload, dict)
            assert "arquivo" not in payload
            assert "caminho_arquivo" not in payload