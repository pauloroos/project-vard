import json
from pathlib import Path

import httpx
import respx

from vard import pesquisa, tarefas

OJ = "http://127.0.0.1:8000"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openjarvis"
RESPOSTA = {"direction": "agent_to_user", "content": "O dólar fechou a R$ 5,10. Fonte: BCB.",
            "created_at": "2026-10-13T10:01:00"}
PERGUNTA = {"id": "m1", "direction": "user_to_agent", "content": "dólar?", "created_at": "2026-10-13T10:00:00"}


@respx.mock
def test_cria_o_agente_e_devolve_a_resposta(loja):
    respx.get(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(200, json={"agents": []}))
    criar = respx.post(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(200, json={"id": "a1"}))
    respx.post(f"{OJ}/v1/managed-agents/a1/messages").mock(return_value=httpx.Response(200, json=PERGUNTA))
    respx.get(f"{OJ}/v1/managed-agents/a1/messages").mock(
        return_value=httpx.Response(200, json={"messages": [RESPOSTA, PERGUNTA]}))
    t = tarefas.nova("pesquisa", "", "dólar?")
    u = pesquisa.executar(t.n, dormir=lambda s: None, espera_s=5)
    corpo = criar.calls[0].request.content.decode()
    assert '"agent_type":"deep_research"' in corpo.replace(" ", "") and "web_search" in corpo
    assert u.estado == "terminou" and u.resumo == "O dólar fechou a R$ 5,10."
    assert "Fonte: BCB" in open(u.resultado, encoding="utf-8").read()


@respx.mock
def test_reusa_o_agente_que_ja_existe(loja):
    respx.get(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(
        200, json={"agents": [{"id": "a9", "name": "vard-pesquisa", "status": "idle"}]}))
    criar = respx.post(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(200, json={"id": "x"}))
    respx.post(f"{OJ}/v1/managed-agents/a9/messages").mock(return_value=httpx.Response(200, json=PERGUNTA))
    respx.get(f"{OJ}/v1/managed-agents/a9/messages").mock(
        return_value=httpx.Response(200, json={"messages": [RESPOSTA, PERGUNTA]}))
    pesquisa.executar(tarefas.nova("pesquisa", "", "x").n, dormir=lambda s: None, espera_s=5)
    assert not criar.called


def test_resposta_antiga_nao_conta():
    velha = {**RESPOSTA, "created_at": "2026-10-13T09:00:00"}
    assert pesquisa.resposta_depois([velha, PERGUNTA], PERGUNTA["created_at"]) is None
    assert pesquisa.resposta_depois([RESPOSTA, PERGUNTA], PERGUNTA["created_at"]).startswith("O dólar")


def test_formato_real_do_openjarvis_created_at_em_segundos():
    envio = json.loads((FIXTURES / "managed-send.json").read_text(encoding="utf-8"))
    msgs = json.loads((FIXTURES / "managed-messages.json").read_text(encoding="utf-8"))["messages"]
    assert isinstance(envio["created_at"], float)
    assert pesquisa.resposta_depois(msgs, envio["created_at"]).startswith("A cotação do dólar")
    assert pesquisa.resposta_depois(msgs, msgs[0]["created_at"]) is None
    assert pesquisa.resposta_depois(msgs, None) is None      # sem created_at da pergunta, resposta antiga não vale


@respx.mock
def test_sem_resposta_no_prazo_vira_falhou(loja):
    respx.get(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(200, json={"agents": [
        {"id": "a1", "name": "vard-pesquisa", "status": "idle"}]}))
    respx.post(f"{OJ}/v1/managed-agents/a1/messages").mock(return_value=httpx.Response(200, json=PERGUNTA))
    u = pesquisa.executar(tarefas.nova("pesquisa", "", "x").n, dormir=lambda s: None, espera_s=0)
    assert u.estado == "falhou" and "15 minutos" in u.resumo


@respx.mock
def test_pergunta_sem_created_at_falha_explicito(loja):
    respx.get(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(200, json={"agents": [
        {"id": "a1", "name": "vard-pesquisa", "status": "idle"}]}))
    respx.post(f"{OJ}/v1/managed-agents/a1/messages").mock(return_value=httpx.Response(200, json={"id": "m"}))
    import pytest
    with pytest.raises(RuntimeError):
        pesquisa.executar(tarefas.nova("pesquisa", "", "x").n, dormir=lambda s: None, espera_s=5)


@respx.mock
def test_pesquisa_descartada_no_meio_nao_ressuscita(loja):
    respx.get(f"{OJ}/v1/managed-agents").mock(return_value=httpx.Response(200, json={"agents": [
        {"id": "a1", "name": "vard-pesquisa", "status": "idle"}]}))
    respx.post(f"{OJ}/v1/managed-agents/a1/messages").mock(return_value=httpx.Response(200, json=PERGUNTA))
    respx.get(f"{OJ}/v1/managed-agents/a1/messages").mock(
        return_value=httpx.Response(200, json={"messages": [RESPOSTA, PERGUNTA]}))
    t = tarefas.nova("pesquisa", "", "x")
    pesquisa.executar(t.n, dormir=lambda s: tarefas.atualizar(t.n, estado="descartada"), espera_s=5)
    assert tarefas.obter(t.n).estado == "descartada"


def test_pesquisa_ja_reivindicada(loja):
    import pytest
    from vard.oficina import JaReivindicada
    t = tarefas.nova("pesquisa", "", "x")
    tarefas.atualizar(t.n, estado="rodando")
    with pytest.raises(JaReivindicada):
        pesquisa.executar(t.n, dormir=lambda s: None, espera_s=0)
