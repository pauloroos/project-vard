"""Seam OpenJarvis <-> mesa_mcp: o OpenJarvis lê o stdio do MCP com a codificação do Windows
(cp1252). Sem PYTHONUTF8=1 no filho, título de janela com acento derruba a leitura."""
import pytest

from vard.mesa_cliente import chamar_ferramenta

TITULO = "ÁREA ∅ inexistente 🔍"


def test_acento_e_emoji_atravessam_o_stdio_com_utf8():
    texto = chamar_ferramenta("focar_janela", {"titulo": TITULO}, utf8=True)
    assert "ÁREA" in texto and "🔍" in texto


def test_sem_utf8_o_leitor_cp1252_quebra():
    # Prova da causa (achado C1): é por isso que aplicar-config.ps1 grava PYTHONUTF8=1.
    with pytest.raises(UnicodeDecodeError):
        chamar_ferramenta("focar_janela", {"titulo": TITULO}, utf8=False)
