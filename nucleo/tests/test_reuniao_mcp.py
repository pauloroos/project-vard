import asyncio

import httpx
import respx

import reuniao_mcp
from vard import mesa_cliente

NOMES = {"reuniao_iniciar", "reuniao_encerrar", "reuniao_status", "reuniao_ata", "reuniao_falante", "reuniao_guardar"}


def test_as_seis_ferramentas_existem():
    assert {t.name for t in asyncio.run(reuniao_mcp.mcp.list_tools())} == NOMES


@respx.mock
def test_iniciar_com_4720_fora_devolve_frase():
    respx.post("http://127.0.0.1:4720/iniciar").mock(side_effect=httpx.ConnectError("x"))
    assert reuniao_mcp.reuniao_iniciar() == "O modo reunião não está instalado."


@respx.mock
def test_status_e_encerrar_passam_pelo_cliente():
    respx.get("http://127.0.0.1:4720/status").mock(return_value=httpx.Response(200, json={"ativa": True, "duracao_s": 60, "falas": 1}))
    assert reuniao_mcp.reuniao_status() == "Reunião em andamento há 1 minuto, 1 fala."
    respx.post("http://127.0.0.1:4720/encerrar").mock(return_value=httpx.Response(409, json={"ok": False, "erro": "inativa"}))
    assert reuniao_mcp.reuniao_encerrar() == "Não há reunião em andamento."


def test_falante_vazio_recusa_sem_rede():
    r = reuniao_mcp.reuniao_falante(0, "")
    assert isinstance(r, str) and "falante" in r


def test_por_stdio_a_recusa_chega_como_texto():
    texto = mesa_cliente.chamar_ferramenta("reuniao_falante", {"n": 0, "nome": ""}, script="reuniao_mcp.py")
    assert "falante" in texto

def test_ata_chama_abrir_ata_com_qual_e_tipo(monkeypatch):
    from vard import reuniao
    vistos = []
    monkeypatch.setattr(reuniao, "abrir_ata", lambda qual, tipo, **kw: vistos.append((qual, tipo)) or "Gerando a ata da reunião de 13/10, aviso quando ficar pronta.")
    assert reuniao_mcp.reuniao_ata("relatorio", "2026-10-13").startswith("Gerando a ata")
    assert vistos == [("2026-10-13", "relatorio")]


def test_ata_com_tipo_ruim_devolve_frase():
    assert reuniao_mcp.reuniao_ata("resumo", "ultima") == "Posso gerar ata ou relatório."


def test_guardar_sem_ata_devolve_a_frase(monkeypatch, tmp_path):
    from vard import reuniao
    (tmp_path / "2026-10-13_1500").mkdir()
    monkeypatch.setattr(reuniao, "RAIZ_REUNIOES", tmp_path)
    monkeypatch.setattr(reuniao, "pasta_por_pedido", lambda qual: "2026-10-13_1500")
    assert reuniao_mcp.reuniao_guardar("ultima") == "Gere a ata antes de guardar na memória."
