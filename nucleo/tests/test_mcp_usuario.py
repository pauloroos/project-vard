"""MCPs do usuário (paineis.json) chegam ao mcp.json da sessão da CLI, sem segredo no arquivo."""
import json
import subprocess
import sys
from copy import deepcopy

import pytest

from vard import ajustes
from vard.segredos import SERVIDORES_LOCAIS

SEGREDO_FICTICIO = "valor-ficticio-que-nunca-vai-ao-arquivo"


def _gravar_paineis(mcps):
    doc = deepcopy(ajustes.PAINEIS_PADRAO)
    doc["mcps"] = mcps
    arq = ajustes.caminho("paineis")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _servidores_da_sessao(tmp_path):
    from vard.cerebro.cli_processos import ProvedorCli, _preparar_pasta_sessao
    pasta = _preparar_pasta_sessao(ProvedorCli("cli", "cli-claude"), "sessao", base_dados=tmp_path / "dados-cli")
    texto = (pasta / "mcp.json").read_text(encoding="utf-8")
    return texto, json.loads(texto)["mcpServers"]


def test_sem_paineis_a_sessao_leva_so_os_mcps_locais(tmp_path):
    _, servidores = _servidores_da_sessao(tmp_path)
    assert set(servidores) == set(SERVIDORES_LOCAIS)


def test_mcps_habilitados_do_usuario_chegam_a_sessao(tmp_path):
    _gravar_paineis([
        {"id": "windows-mcp", "nome": "Windows-MCP", "habilitado": True, "command": "uvx", "args": ["windows-mcp", "serve"]},
        {"id": "remoto", "nome": "Remoto", "habilitado": True, "url": "https://exemplo.invalid/mcp"},
        {"id": "desligado", "nome": "Desligado", "habilitado": False, "command": "node", "args": ["srv.js"]},
    ])
    _, servidores = _servidores_da_sessao(tmp_path)
    assert set(SERVIDORES_LOCAIS) <= set(servidores)
    assert servidores["windows-mcp"] == {"command": "uvx", "args": ["windows-mcp", "serve"]}
    assert servidores["remoto"] == {"type": "http", "url": "https://exemplo.invalid/mcp"}
    assert "desligado" not in servidores


def test_stdio_sem_args_vira_lista_vazia(tmp_path):
    _gravar_paineis([{"id": "simples", "nome": "Simples", "habilitado": True, "command": "servidor-mcp"}])
    _, servidores = _servidores_da_sessao(tmp_path)
    assert servidores["simples"] == {"command": "servidor-mcp", "args": []}


def test_mcp_do_usuario_nao_substitui_um_local(tmp_path):
    _gravar_paineis([{"id": "mesa", "nome": "Impostor", "habilitado": True, "command": "outro"}])
    _, servidores = _servidores_da_sessao(tmp_path)
    assert servidores["mesa"]["command"] == sys.executable


def test_paineis_invalido_mantem_so_os_locais(tmp_path):
    arq = ajustes.caminho("paineis")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("{ isto não é json", encoding="utf-8")
    _, servidores = _servidores_da_sessao(tmp_path)
    assert set(servidores) == set(SERVIDORES_LOCAIS)


def test_http_com_credencial_usa_auxiliar_de_cabecalhos_sem_segredo_no_arquivo(tmp_path, monkeypatch):
    from vard import credenciais
    monkeypatch.setattr(credenciais, "ler_para_uso_interno", lambda tipo, id_: SEGREDO_FICTICIO)
    _gravar_paineis([{"id": "api", "nome": "API", "habilitado": True, "url": "https://exemplo.invalid/mcp",
                      "credencial_ref": "mcp:api_ficticia"}])
    texto, servidores = _servidores_da_sessao(tmp_path)
    assert SEGREDO_FICTICIO not in texto
    api = servidores["api"]
    assert api["type"] == "http" and api["url"] == "https://exemplo.invalid/mcp"
    assert "headers" not in api
    auxiliar = api["headersHelper"]
    assert "-m vard.mcp_usuario cabecalhos mcp:api_ficticia" in auxiliar
    assert auxiliar.startswith('"') and "\\" not in auxiliar


@pytest.mark.parametrize("ref", ["mcp:com espaco", "mcp:a;b", "cofre:api", "mcp:", "mcp:a&b", 'mcp:"x"'])
def test_referencia_fora_do_formato_nao_vira_comando(tmp_path, ref):
    _gravar_paineis([{"id": "api", "nome": "API", "habilitado": True, "url": "https://exemplo.invalid/mcp",
                      "credencial_ref": ref}])
    _, servidores = _servidores_da_sessao(tmp_path)
    assert servidores["api"] == {"type": "http", "url": "https://exemplo.invalid/mcp"}


def test_stdio_com_credencial_entra_sem_segredo(tmp_path, monkeypatch):
    from vard import credenciais
    monkeypatch.setattr(credenciais, "ler_para_uso_interno", lambda tipo, id_: SEGREDO_FICTICIO)
    _gravar_paineis([{"id": "local", "nome": "Local", "habilitado": True, "command": "srv",
                      "credencial_ref": "mcp:local"}])
    texto, servidores = _servidores_da_sessao(tmp_path)
    assert servidores["local"] == {"command": "srv", "args": []}
    assert SEGREDO_FICTICIO not in texto


def test_cabecalhos_le_o_cofre_e_monta_bearer(monkeypatch):
    from vard import credenciais, mcp_usuario
    lidos = []
    monkeypatch.setattr(credenciais, "ler_para_uso_interno", lambda tipo, id_: lidos.append((tipo, id_)) or SEGREDO_FICTICIO)
    assert mcp_usuario.cabecalhos("mcp:api") == {"Authorization": f"Bearer {SEGREDO_FICTICIO}"}
    assert mcp_usuario.cabecalhos("provedor:p1") == {"Authorization": f"Bearer {SEGREDO_FICTICIO}"}
    assert lidos == [("mcp", "api"), ("provedor", "p1")]


def test_cabecalhos_sem_credencial_falha_sem_vazar(monkeypatch, capsys):
    from vard import credenciais, mcp_usuario
    monkeypatch.setattr(credenciais, "ler_para_uso_interno", lambda tipo, id_: None)
    assert mcp_usuario.main(["cabecalhos", "mcp:api"]) == 1
    saida = capsys.readouterr()
    assert saida.out == ""
    assert "mcp:api" not in saida.err or "credencial" in saida.err


def test_main_imprime_json_dos_cabecalhos(monkeypatch, capsys):
    from vard import credenciais, mcp_usuario
    monkeypatch.setattr(credenciais, "ler_para_uso_interno", lambda tipo, id_: SEGREDO_FICTICIO)
    assert mcp_usuario.main(["cabecalhos", "mcp:api"]) == 0
    saida = capsys.readouterr()
    assert json.loads(saida.out) == {"Authorization": f"Bearer {SEGREDO_FICTICIO}"}
    assert SEGREDO_FICTICIO not in saida.err


def test_main_recusa_argumentos_invalidos(capsys):
    from vard import mcp_usuario
    assert mcp_usuario.main([]) == 2
    assert mcp_usuario.main(["cabecalhos", "cofre:x"]) == 2
    assert capsys.readouterr().out == ""


def test_auxiliar_roda_como_modulo():
    """O ponto de entrada `-m vard.mcp_usuario` responde; ref inválida sai 2 sem nada no stdout."""
    from pathlib import Path
    nucleo = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "vard.mcp_usuario", "cabecalhos", "cofre:x"],
                       capture_output=True, text=True, timeout=30, cwd=str(nucleo))
    assert r.returncode == 2
    assert r.stdout == ""
