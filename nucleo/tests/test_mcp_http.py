import json

import httpx
import pytest
import respx

from vard.mcp_http import ClienteMCP, ErroMCP

URL = "http://memoria.exemplo.com/mcp"


@respx.mock
def test_iniciar_guarda_a_sessao_e_manda_o_token():
    rota = respx.post(URL).mock(side_effect=[
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}},
                       headers={"Mcp-Session-Id": "s1"}),
        httpx.Response(202),
    ])
    ClienteMCP(URL, "tok").iniciar()
    assert rota.calls[0].request.headers["Authorization"] == "Bearer tok"
    assert rota.calls[1].request.headers["Mcp-Session-Id"] == "s1"
    assert json.loads(rota.calls[1].request.content)["method"] == "notifications/initialized"


@respx.mock
def test_resposta_em_sse():
    corpo = ('event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"content":'
             '[{"type":"text","text":"{\\"global_hits\\": []}"}]}}\n\n')
    respx.post(URL).mock(return_value=httpx.Response(200, text=corpo, headers={"content-type": "text/event-stream"}))
    assert ClienteMCP(URL, "t").chamar("memory_query", {"query": "x"}) == '{"global_hits": []}'


@respx.mock
def test_401_vira_ErroMCP():
    respx.post(URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ErroMCP, match="401"):
        ClienteMCP(URL, "t").chamar("x", {})


@respx.mock
def test_isError_vira_ErroMCP():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {
        "isError": True, "content": [{"type": "text", "text": "project not found"}]}}))
    with pytest.raises(ErroMCP, match="project not found"):
        ClienteMCP(URL, "t").chamar("x", {})


@respx.mock
def test_rede_fora_vira_ErroMCP_sem_vazar_o_token():
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("demorou"))
    with pytest.raises(ErroMCP, match="sem conexão") as e:
        ClienteMCP(URL, "SEGREDO").chamar("x", {})
    assert "SEGREDO" not in str(e.value)


@respx.mock
def test_json_que_nao_e_objeto_vira_ErroMCP():
    respx.post(URL).mock(return_value=httpx.Response(200, json=[1, 2]))
    with pytest.raises(ErroMCP, match="objeto"):
        ClienteMCP(URL, "t").chamar("x", {})
