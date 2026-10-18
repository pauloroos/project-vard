"""Testes do acessor de credenciais (cofre generalizado).

Prova a validação de alvo, recusa de valores inválidos e isolamento
entre entradas sem depender do cofre Windows real (dublê do CredWriteW/CredReadW).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vard import credenciais


class TestValidacaoAlvo:
    def test_alvo_valido_provedor(self):
        assert credenciais._validar_alvo("provedor", "suad") == "vard:provedor:suad"

    def test_alvo_valido_voz(self):
        assert credenciais._validar_alvo("voz", "kokoro-local") == "vard:voz:kokoro-local"

    def test_alvo_valido_mcp(self):
        assert credenciais._validar_alvo("mcp", "filesystem") == "vard:mcp:filesystem"

    def test_tipo_desconhecido_recusado(self):
        with pytest.raises(ValueError, match="tipo de credencial desconhecido"):
            credenciais._validar_alvo("agente", "claude")

    def test_id_vazio_recusado(self):
        with pytest.raises(ValueError, match="id deve ter"):
            credenciais._validar_alvo("provedor", "")

    def test_id_longo_recusado(self):
        with pytest.raises(ValueError, match="id deve ter"):
            credenciais._validar_alvo("provedor", "a" * 129)

    def test_id_com_caractere_invalido_recusado(self):
        with pytest.raises(ValueError, match="só aceita"):
            credenciais._validar_alvo("provedor", "com espaço")
        with pytest.raises(ValueError, match="só aceita"):
            credenciais._validar_alvo("provedor", "com/barra")
        with pytest.raises(ValueError, match="só aceita"):
            credenciais._validar_alvo("provedor", "com@arroba")

    def test_id_com_hifen_sublinhado_ponto_aceito(self):
        assert credenciais._validar_alvo("provedor", "meu-provedor_1.0") == "vard:provedor:meu-provedor_1.0"


class TestValidacaoValor:
    def test_valor_vazio_recusado(self):
        with pytest.raises(ValueError, match="valor deve ter"):
            credenciais.gravar("provedor", "x", "")

    def test_valor_longo_recusado(self):
        with pytest.raises(ValueError, match="valor deve ter"):
            credenciais.gravar("provedor", "x", "a" * 4097)

    def test_valor_com_controle_recusado(self):
        with pytest.raises(ValueError, match="controle"):
            credenciais.gravar("provedor", "x", "teste\n")
        with pytest.raises(ValueError, match="controle"):
            credenciais.gravar("provedor", "x", "teste\0")


class TestDuasEntradasIsoladas:
    @patch("vard.credenciais._gravar_windows")
    def test_entradas_isoladas(self, mock_invocar):
        """Duas entradas diferentes não interferem entre si."""
        mock_invocar.return_value = ""
        credenciais.gravar("provedor", "a", "va")
        credenciais.gravar("provedor", "b", "vb")
        # Verifica que ambas foram chamadas com alvos distintos
        chamadas = [c.args for c in mock_invocar.call_args_list]
        assert ("vard:provedor:a", "va") in chamadas
        assert ("vard:provedor:b", "vb") in chamadas


class TestReferenciaInvalidaRecusada:
    def test_tipo_invalido_na_existe(self):
        assert credenciais.existe("desconhecido", "x") is False

    def test_id_invalido_na_existe(self):
        assert credenciais.existe("provedor", "") is False

    def test_tipo_invalido_no_apagar(self):
        with pytest.raises(ValueError, match="tipo de credencial desconhecido"):
            credenciais.apagar("desconhecido", "x")


class TestCofreIndisponivelSemValorNoErro:
    @patch("vard.credenciais._gravar_windows")
    def test_erro_nao_vaza_detalhes(self, mock_invocar):
        mock_invocar.side_effect = RuntimeError("falha no cofre (detalhes suprimidos)")
        with pytest.raises(RuntimeError, match="cofre"):
            credenciais.gravar("provedor", "x", "valor")
        # O erro não deve conter palavras sensíveis
        try:
            credenciais.gravar("provedor", "x", "valor")
        except RuntimeError as e:
            msg = str(e).lower()
            assert "key" not in msg
            assert "token" not in msg
            assert "password" not in msg


class TestMigracaoFalhaPreservaOriginal:
    """Se a gravação falhar, o valor original não é perdido.

    Na implementação real, isso é garantido pelo Rust (migrar_legados
    confirma leitura antes de remover do JSON). Aqui testamos que o
    Python propaga a exceção sem silenciar.
    """
    @patch("vard.credenciais._gravar_windows")
    def test_falha_propaga_excecao(self, mock_invocar):
        mock_invocar.side_effect = RuntimeError("falha no cofre")
        with pytest.raises(RuntimeError):
            credenciais.gravar("provedor", "x", "valor")

class TestLeituraDiretaDoCofreWindows:
    """O núcleo lê o cofre do Windows direto (CredReadW): o app não tem modo --cofre."""

    @patch("vard.credenciais._ler_windows")
    def test_ler_usa_o_alvo_do_app(self, mock_ler):
        mock_ler.return_value = "valor-ficticio"
        assert credenciais.ler_para_uso_interno("provedor", "lm1") == "valor-ficticio"
        mock_ler.assert_called_once_with("vard:provedor:lm1")

    @patch("vard.credenciais._ler_windows")
    def test_existe_sem_expor_valor(self, mock_ler):
        mock_ler.return_value = None
        assert credenciais.existe("provedor", "lm1") is False
        mock_ler.return_value = "x"
        assert credenciais.existe("provedor", "lm1") is True

    def test_segredo_do_keyring_em_utf16_e_utf8(self):
        assert credenciais._decodificar("sk-ficticio".encode("utf-16-le")) == "sk-ficticio"
        assert credenciais._decodificar("sk-ficticio".encode("utf-8")) == "sk-ficticio"

    def test_referencia_com_tipo_e_id(self):
        assert credenciais.separar_referencia("provedor:lm1", "provedor") == ("provedor", "lm1")
        assert credenciais.separar_referencia("lm1", "provedor") == ("provedor", "lm1")


class TestCofreFalsoDosTestes:
    """O conftest troca o cofre do Windows por um dicionário: nenhum teste lê ou grava o cofre real."""

    def test_gravar_ler_e_apagar_no_dublê(self, cofre_falso):
        credenciais.gravar("canal", "telegram", "123:ficticio")
        assert cofre_falso == {"vard:canal:telegram": "123:ficticio"}
        assert credenciais.ler_para_uso_interno("canal", "telegram") == "123:ficticio"
        credenciais.apagar("canal", "telegram")
        assert credenciais.existe("canal", "telegram") is False

    def test_tipo_canal_aceito(self):
        assert credenciais._validar_alvo("canal", "telegram") == "vard:canal:telegram"
