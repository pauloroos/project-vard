import logging
from pathlib import Path

import httpx
import pytest
import respx

from vard import avisos, tarefas

TOKEN = "123456:SEGREDO-do-bot"


@pytest.fixture(autouse=True)
def _telegram_sempre(monkeypatch):
    """Os testes antigos medem o envio em si; a regra de quando enviar tem testes próprios (_avisar_com)."""
    monkeypatch.setattr(avisos, "_conf_oficina", lambda: {"telegram": "sempre"})


def tarefa(**kw):
    base = dict(n=3, ferramenta="codex", repo="demo", pedido="x", estado="terminou", resumo="paginação pronta")
    return tarefas.Tarefa(**{**base, **kw})


def test_evento_tem_o_formato_do_widget():
    assert avisos.evento(tarefa()) == {"tipo": "tarefa", "n": 3, "estado": "terminou",
                                       "resumo": "A tarefa 3 no Codex terminou: paginação pronta.",
                                       "ferramenta": "codex"}


def test_frases_por_ferramenta():
    assert avisos.frase(tarefa(ferramenta="agente_remoto", repo="", resumo="o card está em revisão")) == \
        "O agente remoto respondeu: o card está em revisão."
    assert avisos.frase(tarefa(estado="esperando", resumo="posso rodar os testes?")) == \
        "A tarefa 3 no Codex está esperando sua resposta: posso rodar os testes?"
    assert avisos.frase(tarefa(estado="travou", resumo="")) == "A tarefa 3 no Codex está parada há mais de 10 minutos."
    assert avisos.frase(tarefa(ferramenta="manha", repo="")) == "O resumo do dia está pronto."


def test_frase_de_bloqueio_manda_responder_no_orca():
    t = tarefa(estado="esperando", resumo="pede confirmação de confiança", bloqueio="agent-trust-workspace")
    assert avisos.frase(t) == "A tarefa 3 no Codex precisa que você responda no Orca."


def test_evento_da_manha_leva_o_texto(loja):
    arq = tarefas.arquivo_resultado(7)
    arq.write_text("Bom dia, Fulano. Três reuniões hoje.", encoding="utf-8")
    ev = avisos.evento(tarefa(n=7, ferramenta="manha", repo="", resultado=str(arq), resumo="O resumo do dia está pronto."))
    assert ev["texto"] == "Bom dia, Fulano. Três reuniões hoje." and ev["resumo"] == "O resumo do dia está pronto."


@respx.mock
def test_falha_do_telegram_nao_vaza_token(caplog):
    respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
        side_effect=httpx.ConnectError(f"falhou https://api.telegram.org/bot{TOKEN}/sendMessage"))
    with caplog.at_level(logging.DEBUG, logger="vard"):
        assert avisos.telegram("oi", token=TOKEN, chat_id="42") is False
    assert TOKEN not in caplog.text and "SEGREDO" not in caplog.text


def test_telegram_sem_token_nem_chama():
    assert avisos.telegram("oi", token="", chat_id="42") is False


@respx.mock
def test_telegram_ok_corta_em_4000():
    rota = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True}))
    assert avisos.telegram("x" * 5000, token=TOKEN, chat_id="42") is True
    assert len(rota.calls[0].request.content.decode()) < 4200


@respx.mock
def test_publicar_na_ponte_sem_origin():
    rota = respx.post("http://127.0.0.1:4700/events/publicar").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert avisos.publicar({"tipo": "tarefa", "n": 1, "estado": "terminou", "resumo": "ok"}) is True
    assert "origin" not in {k.lower() for k in rota.calls[0].request.headers}


def test_avisar_nunca_levanta(monkeypatch):
    def explode(ev, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(avisos, "publicar", explode)
    avisos.avisar(tarefa())       # não pode levantar


@respx.mock
def test_resumo_curto_usa_o_gemma():
    respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(return_value=httpx.Response(
        200, json={"choices": [{"message": {"content": "O card 42 está em revisão."}}]}))
    assert avisos.resumo_curto("texto longo da o agente remoto...", chave="k") == "O card 42 está em revisão."


@respx.mock
def test_resumo_curto_sem_gemma_usa_a_primeira_frase():
    respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(side_effect=httpx.ConnectError("x"))
    assert avisos.resumo_curto("O card 42 está em revisão. Depois vejo o resto.", chave="k") == \
        "O card 42 está em revisão."


def test_limpar_markdown():
    assert avisos.limpar_markdown("A cotação é **R$ 4,99** (*talvez*) e `x` [site](http://a.b)") == \
        "A cotação é R$ 4,99 (talvez) e x site"
    assert avisos.limpar_markdown("# Título\n- um\n* dois\n1. três\n> citação\n__forte__ e _leve_") == \
        "Título\num\ndois\ntrês\ncitação\nforte e leve"
    assert avisos.limpar_markdown("snake_case_name e 2*3") == "snake_case_name e 2*3"
    assert avisos.limpar_markdown("```py\nprint(1)\n```") == "print(1)"


def test_frase_e_evento_saem_sem_markdown():
    t = tarefa(ferramenta="pesquisa", repo="", resumo="O dólar está em **R$ 4,99**")
    assert "*" not in avisos.frase(t) and "*" not in avisos.evento(t)["resumo"]


def test_texto_da_manha_sai_sem_markdown(loja):
    arq = tarefas.arquivo_resultado(8)
    arq.write_text("## Agenda\n- **9h** reunião", encoding="utf-8")
    t = tarefa(n=8, ferramenta="manha", repo="", resultado=str(arq))
    assert avisos.evento(t)["texto"] == "Agenda\n9h reunião" and "*" not in avisos.texto_telegram(t)


@respx.mock
def test_resumo_curto_sem_markdown():
    respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(return_value=httpx.Response(
        200, json={"choices": [{"message": {"content": "O card **42** está em revisão."}}]}))
    assert avisos.resumo_curto("texto", chave="k") == "O card 42 está em revisão."


def test_avisar_devolve_false_quando_nada_chegou(monkeypatch):
    monkeypatch.setattr(avisos, "publicar", lambda ev, **k: False)
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {})
    assert avisos.avisar(tarefa()) is False
    monkeypatch.setattr(avisos, "publicar", lambda ev, **k: True)
    assert avisos.avisar(tarefa()) is True


def test_frase_e_evento_da_ata():
    pronta = tarefa(ferramenta="ata", repo="2026-10-13_1500", pedido="ata", resumo="Orçamento fechado em 45 mil.")
    assert avisos.frase(pronta) == "A ata da reunião de 13/10 está pronta."
    assert avisos.frase(tarefa(ferramenta="ata", repo="2026-10-13_1500", pedido="relatorio")) == \
        "O relatório da reunião de 13/10 está pronto."
    falhou = tarefa(ferramenta="ata", repo="2026-10-13_1500", pedido="ata", estado="falhou", resumo="O Gemma local não respondeu.")
    assert avisos.frase(falhou) == "Não consegui gerar a ata: O Gemma local não respondeu."
    assert avisos.evento(pronta) == {"tipo": "reuniao", "estado": "ata_pronta", "duracao_s": 0, "pasta": "2026-10-13_1500",
                                     "resumo": "A ata da reunião de 13/10 está pronta."}
    ev = avisos.evento(falhou)
    assert ev["estado"] == "erro" and ev["pasta"] == "2026-10-13_1500" and ev["tipo"] == "reuniao"


def test_evento_da_ata_usa_so_o_nome_da_pasta():
    ev = avisos.evento(tarefa(ferramenta="ata", repo=r"X:\x\reunioes\2026-10-13_1500", pedido="ata"))
    assert ev["pasta"] == "2026-10-13_1500"


@respx.mock
def test_telegram_documento_manda_o_pdf_por_sendDocument(tmp_path):
    pdf = tmp_path / "ata.pdf"
    pdf.write_bytes(b"%PDF-1.4 conteudo")
    rota = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument").mock(
        return_value=httpx.Response(200, json={"ok": True}))
    assert avisos.telegram_documento(pdf, "A ata está pronta." + "x" * 2000, token=TOKEN, chat_id="42") is True
    corpo = rota.calls[0].request.content
    assert b"multipart/form-data" in rota.calls[0].request.headers["content-type"].encode()
    assert b'name="document"; filename="ata.pdf"' in corpo and b"%PDF-1.4 conteudo" in corpo and b'name="chat_id"' in corpo
    legenda = corpo.split(b'name="caption"')[1].split(b"\r\n--")[0].strip()
    assert len(legenda.decode()) <= 1000


def test_telegram_documento_sem_token_ou_sem_arquivo(tmp_path):
    pdf = tmp_path / "ata.pdf"
    pdf.write_bytes(b"%PDF")
    assert avisos.telegram_documento(pdf, "x", token="", chat_id="42") is False
    assert avisos.telegram_documento(tmp_path / "nao-existe.pdf", "x", token=TOKEN, chat_id="42") is False


@respx.mock
def test_falha_do_telegram_documento_nao_vaza_token(tmp_path, caplog):
    pdf = tmp_path / "ata.pdf"
    pdf.write_bytes(b"%PDF")
    respx.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument").mock(
        side_effect=httpx.ConnectError(f"falhou https://api.telegram.org/bot{TOKEN}/sendDocument"))
    with caplog.at_level(logging.DEBUG, logger="vard"):
        assert avisos.telegram_documento(pdf, "x", token=TOKEN, chat_id="42") is False
    assert TOKEN not in caplog.text and "SEGREDO" not in caplog.text


@respx.mock
def test_avisar_da_ata_manda_o_documento_com_o_lembrete(tmp_path, monkeypatch):
    pdf = tmp_path / "ata.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {"telegram": {"token": TOKEN, "chat_id": "42"}})
    respx.post("http://127.0.0.1:4700/events/publicar").mock(return_value=httpx.Response(200, json={"ok": True}))
    doc = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument").mock(return_value=httpx.Response(200, json={"ok": True}))
    msg = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    t = tarefa(ferramenta="ata", repo="2026-10-13_1500", pedido="ata", resultado=str(pdf), resumo="Orçamento fechado.")
    assert avisos.avisar(t) is True
    assert doc.called and not msg.called
    assert "avise os participantes que a reunião foi transcrita".encode() in doc.calls[0].request.content


@respx.mock
def test_avisar_da_ata_sem_pdf_cai_na_mensagem(tmp_path, monkeypatch):
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {"telegram": {"token": TOKEN, "chat_id": "42"}})
    respx.post("http://127.0.0.1:4700/events/publicar").mock(return_value=httpx.Response(200, json={"ok": True}))
    msg = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    t = tarefa(ferramenta="ata", repo="2026-10-13_1500", pedido="ata", resultado=str(tmp_path / "sumiu.pdf"))
    assert avisos.avisar(t) is True and msg.called


def _ata_com_pdf(tmp_path, tamanho=20):
    pdf = tmp_path / "ata.pdf"
    pdf.write_bytes(b"%PDF" + b"x" * tamanho)
    return tarefa(ferramenta="ata", repo="2026-10-13_1500", pedido="ata", resultado=str(pdf), resumo="Orçamento fechado.")


@respx.mock
def test_ata_documento_falhou_cai_na_mensagem_com_o_caminho(tmp_path, monkeypatch):
    t = _ata_com_pdf(tmp_path)
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {"telegram": {"token": TOKEN, "chat_id": "42"}})
    respx.post("http://127.0.0.1:4700/events/publicar").mock(return_value=httpx.Response(200, json={"ok": True}))
    doc = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument").mock(return_value=httpx.Response(502))
    msg = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert avisos.avisar(t) is True
    assert doc.called and msg.called
    texto = msg.calls[0].request.content.decode()
    assert "O PDF está em" in texto and "ata.pdf" in texto and "avise os participantes" in texto


@respx.mock
def test_ata_acima_do_limite_so_manda_mensagem(tmp_path, monkeypatch):
    t = _ata_com_pdf(tmp_path, tamanho=100)
    monkeypatch.setattr(avisos, "LIMITE_DOCUMENTO", 50)
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {"telegram": {"token": TOKEN, "chat_id": "42"}})
    respx.post("http://127.0.0.1:4700/events/publicar").mock(return_value=httpx.Response(200, json={"ok": True}))
    doc = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument").mock(return_value=httpx.Response(200, json={"ok": True}))
    msg = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert avisos.avisar(t) is True and msg.called and not doc.called


def test_telegram_documento_acima_do_limite_nem_le_o_arquivo(tmp_path, monkeypatch):
    t = _ata_com_pdf(tmp_path, tamanho=100)
    monkeypatch.setattr(avisos, "LIMITE_DOCUMENTO", 50)
    assert avisos.telegram_documento(Path(t.resultado), "x", token=TOKEN, chat_id="42") is False


def test_httpx_e_httpcore_nao_logam_em_info():
    assert logging.getLogger("httpx").level == logging.WARNING and logging.getLogger("httpcore").level == logging.WARNING


def _deleg(**kw):
    return tarefas.Tarefa(**{"n": 12, "ferramenta": "delegada", "repo": "", "pedido": "x", "agente": "claude", **kw})


def test_frase_delegada():
    assert avisos.frase(_deleg(estado="terminou", resumo="A ABC-12 é a mais importante.")) == \
        "O Claude respondeu: A ABC-12 é a mais importante."
    assert avisos.frase(_deleg(estado="esperando", bloqueio="login", terminal="t1", agente="codex")) == \
        "A consulta 12 precisa que você entre no Codex: responda no terminal, aba Vard #12 no Orca."
    assert avisos.frase(_deleg(estado="esperando", bloqueio="login", agente="codex")) == \
        "A consulta 12 precisa que você entre no Codex: abra um terminal e faça o login."
    assert avisos.frase(_deleg(estado="esperando", bloqueio="conector", agente="codex",
                               resumo="reconecte o Linear no ChatGPT", link="https://chatgpt.com/x")) == \
        "O Codex precisa que você reconecte o Linear no ChatGPT; mandei o link no Telegram. Depois diga: tenta de novo a consulta 12."
    assert avisos.frase(_deleg(estado="falhou", resumo="o Claude não respondeu em 3 minutos")) == \
        "Não consegui perguntar ao Claude: o Claude não respondeu em 3 minutos."


def test_evento_delegada_leva_agente():
    ev = avisos.evento(_deleg(estado="terminou", resumo="ok"))
    assert (ev["tipo"], ev["ferramenta"], ev["agente"]) == ("tarefa", "delegada", "claude")


def test_telegram_delegada_corta_e_aponta_o_resultado(tmp_path, config_usuario):
    arq = tmp_path / "12.md"
    arq.write_text("RESUMO: ok\n" + "linha **negrito**\n" * 300, encoding="utf-8")
    txt = avisos.texto_telegram(_deleg(estado="terminou", resumo="ok", resultado=str(arq)))
    assert txt.startswith("O Claude respondeu: ok.\n\nlinha negrito") and "**" not in txt and "RESUMO:" not in txt
    assert txt.endswith('Texto completo: diga "resultado da tarefa 12".') and len(txt) < 1700


def test_telegram_delegada_curta_nao_tem_nota(tmp_path, config_usuario):
    arq = tmp_path / "12.md"
    arq.write_text("RESUMO: ok\nSó isso.", encoding="utf-8")
    assert avisos.texto_telegram(_deleg(estado="terminou", resumo="ok", resultado=str(arq))) == \
        "O Claude respondeu: ok.\n\nSó isso."


def test_telegram_delegada_conector_tem_link():
    txt = avisos.texto_telegram(_deleg(estado="esperando", bloqueio="conector", agente="codex",
                                       resumo="reconecte o Linear no ChatGPT", link="https://chatgpt.com/x"))
    assert txt.endswith("\n\nhttps://chatgpt.com/x")


def _avisar_com(monkeypatch, conf, **kw):
    envios = []
    monkeypatch.setattr(avisos, "publicar", lambda ev, **k: True)
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {})
    monkeypatch.setattr(avisos.segredos, "chave_telegram", lambda d=None: "tok")
    monkeypatch.setattr(avisos.segredos, "chat_id_telegram", lambda d=None: "1")
    monkeypatch.setattr(avisos, "telegram", lambda texto, **k: envios.append(texto) or True)
    monkeypatch.setattr(avisos, "_conf_oficina", lambda: conf)
    assert avisos.avisar(tarefa(**kw)) is True
    return envios


def _faz(min_):
    import datetime as dt
    return (dt.datetime.now().astimezone() - dt.timedelta(minutes=min_)).isoformat(timespec="seconds")


def test_telegram_auto_tarefa_curta_nao_envia(monkeypatch):
    assert _avisar_com(monkeypatch, {"telegram": "auto"}, criada_em=_faz(1), atualizada_em=_faz(0)) == []


@pytest.mark.parametrize("estado", ["terminou", "falhou", "esperando"])
@pytest.mark.parametrize("ferramenta", ["delegada", "codex", "agente_remoto", "ata"])
def test_telegram_origem_envia_tarefa_curta(monkeypatch, config_usuario, estado, ferramenta):
    assert len(_avisar_com(monkeypatch, {"telegram": "auto"}, origem="telegram", estado=estado,
                          ferramenta=ferramenta, criada_em=_faz(1), atualizada_em=_faz(0))) == 1


@pytest.mark.parametrize("estado", ["terminou", "falhou", "esperando"])
def test_telegram_nunca_bloqueia_origem_telegram(monkeypatch, estado):
    assert _avisar_com(monkeypatch, {"telegram": "nunca"}, origem="telegram", estado=estado,
                       criada_em=_faz(1), atualizada_em=_faz(0)) == []


def test_telegram_auto_tarefa_longa_envia(monkeypatch):
    assert len(_avisar_com(monkeypatch, {"telegram": "auto", "telegram_apos_min": 3}, criada_em=_faz(5), atualizada_em=_faz(0))) == 1


def test_telegram_auto_esperando_envia_mesmo_curta(monkeypatch):
    assert len(_avisar_com(monkeypatch, {"telegram": "auto"}, estado="esperando", criada_em=_faz(0))) == 1


def test_telegram_sempre_envia_e_nunca_nao(monkeypatch):
    assert len(_avisar_com(monkeypatch, {"telegram": "sempre"}, criada_em=_faz(0))) == 1
    assert _avisar_com(monkeypatch, {"telegram": "nunca"}, criada_em=_faz(60), estado="esperando") == []


def test_telegram_auto_mede_ate_a_conclusao_nao_ate_o_aviso(monkeypatch):
    assert _avisar_com(monkeypatch, {"telegram": "auto"}, criada_em=_faz(10), atualizada_em=_faz(9)) == []



def test_aviso_remoto_usa_nome_configurado(monkeypatch):
    monkeypatch.setattr("vard.remoto.nome", lambda: "o assistente de teste")
    assert avisos.frase(tarefa(ferramenta="agente_remoto", repo="", resumo="pronto")) == "O assistente de teste respondeu: pronto."



def test_aviso_manha_sem_config_nao_anuncia_resumo_pronto():
    t = tarefa(ferramenta="manha", repo="", resumo="A rotina da manhã não está configurada.")
    assert avisos.frase(t) == "A rotina da manhã não está configurada."
