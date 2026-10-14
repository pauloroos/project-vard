import json
import subprocess
import sys
from pathlib import Path

import pytest

from vard import tarefas

RAIZ = Path(__file__).resolve().parent.parent


def test_nova_numera_em_sequencia(loja):
    a = tarefas.nova("codex", "demo", "fazer x")
    b = tarefas.nova("agente_remoto", "", "como está o card 42?")
    assert (a.n, b.n) == (1, 2)
    assert [t.n for t in tarefas.listar()] == [1, 2]
    assert tarefas.obter(2).pedido == "como está o card 42?"


@pytest.mark.parametrize("idade,origem", [(0, "telegram"), (119, "telegram"), (120, "voz"), (180, "voz"), (-10, "voz")])
def test_nova_detecta_marca_telegram_recente(loja, monkeypatch, idade, origem):
    marca = loja.parent / "ultimo-telegram.json"
    marca.write_text(json.dumps({"ts": 1000 - idade}), encoding="utf-8")
    monkeypatch.setenv("VARD_MARCA_TELEGRAM", str(marca))
    monkeypatch.setattr(tarefas.time, "time", lambda: 1000)
    t = tarefas.nova("delegada", "", "data de hoje", agente="claude")
    assert t.origem == origem
    assert tarefas.obter(t.n).origem == origem


@pytest.mark.parametrize("conteudo", [None, "{", "{}", '[]', '{"ts": null}', '{"ts": "ontem"}'])
def test_marca_ausente_ou_invalida_nao_impede_tarefa(loja, monkeypatch, conteudo):
    marca = loja.parent / "ultimo-telegram.json"
    if conteudo is not None:
        marca.write_text(conteudo, encoding="utf-8")
    monkeypatch.setenv("VARD_MARCA_TELEGRAM", str(marca))
    assert tarefas.nova("agente_remoto", "", "oi").origem == "voz"


def test_marca_padrao_e_agenda_preservada(loja, monkeypatch):
    monkeypatch.delenv("VARD_MARCA_TELEGRAM", raising=False)
    monkeypatch.setattr(tarefas, "PASTA", loja.parent)
    (loja.parent / "ultimo-telegram.json").write_text(json.dumps({"ts": 1000}), encoding="utf-8")
    monkeypatch.setattr(tarefas.time, "time", lambda: 1000)
    assert tarefas.nova("agente_remoto", "", "oi").origem == "telegram"
    assert tarefas.nova("manha", "", "rotina", origem="agenda").origem == "agenda"


def test_tarefa_antiga_sem_origem_continua_valida(loja):
    loja.write_text(json.dumps({"proximo": 2, "tarefas": [
        {"n": 1, "ferramenta": "agente_remoto", "repo": "", "pedido": "oi"}]}), encoding="utf-8")
    assert tarefas.obter(1).origem == "voz"


def test_ferramenta_desconhecida_recusada(loja):
    with pytest.raises(ValueError):
        tarefas.nova("cursor", "demo", "x")


def test_atualizar_muda_estado_e_hora(loja):
    t = tarefas.nova("codex", "demo", "x")
    u = tarefas.atualizar(t.n, estado="rodando", terminal="term_1")
    assert u.estado == "rodando" and u.terminal == "term_1"
    assert tarefas.obter(t.n).estado == "rodando"


def test_estado_e_campo_invalidos_recusados(loja):
    t = tarefas.nova("codex", "demo", "x")
    with pytest.raises(ValueError):
        tarefas.atualizar(t.n, estado="dormindo")
    with pytest.raises(ValueError):
        tarefas.atualizar(t.n, senha="x")
    with pytest.raises(KeyError):
        tarefas.atualizar(99, estado="rodando")


def test_arquivo_estragado_nao_e_sobrescrito(loja):
    loja.write_text("{isto não é json", encoding="utf-8")
    with pytest.raises(ValueError):
        tarefas.nova("codex", "demo", "x")
    assert loja.read_text(encoding="utf-8") == "{isto não é json"


def test_chave_nova_no_arquivo_e_ignorada(loja):
    loja.write_text(json.dumps({"proximo": 2, "tarefas": [
        {"n": 1, "ferramenta": "agente_remoto", "repo": "", "pedido": "oi", "campo_do_futuro": 1}]}), encoding="utf-8")
    assert tarefas.obter(1).pedido == "oi"


def test_aberta():
    assert tarefas.Tarefa(1, "codex", "demo", "x", estado="terminou").aberta
    assert not tarefas.Tarefa(2, "agente_remoto", "", "x", estado="terminou").aberta
    assert tarefas.Tarefa(3, "agente_remoto", "", "x", estado="rodando").aberta
    assert not tarefas.Tarefa(4, "codex", "demo", "x", estado="aprovada").aberta


def test_resumir_pega_a_primeira_frase_e_corta():
    assert tarefas.resumir("Feito o ajuste no filtro. Depois rodei os testes.") == "Feito o ajuste no filtro."
    assert len(tarefas.resumir("x" * 500, 50)) == 50


def test_trava_entre_processos(tmp_path):
    arq = tmp_path / "t.json"
    codigo = ("import time; from pathlib import Path; from vard import tarefas\n"
              f"with tarefas.trava(Path(r'{arq}')):\n    print('pegou', flush=True); time.sleep(3)\n")
    p = subprocess.Popen([sys.executable, "-c", codigo], stdout=subprocess.PIPE, text=True, cwd=RAIZ)
    try:
        assert p.stdout.readline().strip() == "pegou"
        with pytest.raises(TimeoutError):
            with tarefas.trava(arq, espera=0.3):
                pass
    finally:
        p.wait(timeout=15)
    with tarefas.trava(arq, espera=1):
        pass


def test_gravacao_e_atomica_via_os_replace(loja, monkeypatch):
    t = tarefas.nova("codex", "demo", "x")
    antes = loja.read_text(encoding="utf-8")
    chamadas = []

    def falha(origem, destino):
        chamadas.append((origem, destino))
        raise OSError("disco cheio")

    monkeypatch.setattr(tarefas.os, "replace", falha)
    with pytest.raises(OSError):
        tarefas.atualizar(t.n, estado="rodando")
    assert chamadas, "a gravação tem que passar por os.replace"
    assert loja.read_text(encoding="utf-8") == antes          # o arquivo bom ficou intacto
    assert tarefas.obter(t.n).estado == "preparando"


def test_comparar_e_trocar_so_grava_se_o_estado_confere(loja):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="descartada")
    u = tarefas.atualizar(t.n, se_estado="rodando", estado="terminou")
    assert u.estado == "descartada" and tarefas.obter(t.n).estado == "descartada"
    v = tarefas.atualizar(t.n, se_estado="descartada", resumo="ok")
    assert v.resumo == "ok"


def test_criacao_nao_se_altera(loja):
    t = tarefas.nova("codex", "demo", "x")
    with pytest.raises(ValueError):
        tarefas.atualizar(t.n, criada_em="2020-01-01T00:00:00+00:00")


def test_versao_sobe_a_cada_gravacao_e_comparar_por_versao(loja):
    t = tarefas.nova("codex", "demo", "x")
    assert t.versao == 0
    u = tarefas.atualizar(t.n, resumo="a")
    assert u.versao == 1
    # alguém gravou depois de eu ler a versão 1: a minha gravação condicionada à versão 1 não pode passar
    tarefas.atualizar(t.n, resumo="b")
    v = tarefas.atualizar(t.n, se_versao=1, resumo="c")
    assert v.resumo == "b" and tarefas.obter(t.n).resumo == "b"
    w = tarefas.atualizar(t.n, se_versao=2, resumo="c")
    assert w.resumo == "c" and w.versao == 3

def test_ata_e_ferramenta_valida_e_terminada_nao_fica_aberta(loja):
    t = tarefas.nova("ata", "2026-10-13_1500", "ata")
    assert t.ferramenta == "ata" and t.aberta is True
    assert tarefas.Tarefa(n=1, ferramenta="ata", repo="x", pedido="ata", estado="terminou").aberta is False


def test_arquivo_pela_variavel_de_ambiente(tmp_path, monkeypatch):
    alvo = tmp_path / "outro.json"
    monkeypatch.setenv("VARD_TAREFAS_ARQUIVO", str(alvo))
    t = tarefas.nova("agente_remoto", "", "x")
    assert alvo.exists() and tarefas.obter(t.n).pedido == "x"
    assert tarefas.obter(t.n, tmp_path / "vazio.json") is None          # arq explícito vence a variável


def test_nova_aceita_campos_extras(loja):
    t = tarefas.nova("delegada", "", "oi", agente="claude", reserva="agy", modelo="opus")
    assert (t.agente, t.reserva, t.tentativas, t.link, t.modelo) == ("claude", "agy", 0, "", "opus")
    assert tarefas.obter(t.n).agente == "claude"
    for ruim in ({"versao": 3}, {"n": 9}, {"inventado": 1}):
        with pytest.raises(ValueError):
            tarefas.nova("delegada", "", "oi", **ruim)


def test_delegada_terminada_nao_fica_aberta(loja):
    t = tarefas.nova("delegada", "", "oi", agente="claude")
    assert tarefas.atualizar(t.n, estado="esperando").aberta is True
    assert tarefas.atualizar(t.n, estado="terminou").aberta is False


def test_arquivo_resultado_acompanha_a_loja_a_parte(tmp_path, monkeypatch):
    monkeypatch.setattr(tarefas, "PASTA_RESULTADOS", tmp_path / "padrao")
    monkeypatch.delenv("VARD_TAREFAS_ARQUIVO", raising=False)
    assert tarefas.arquivo_resultado(7) == tmp_path / "padrao" / "7.md"
    monkeypatch.setenv("VARD_TAREFAS_ARQUIVO", str(tmp_path / "outra" / "tarefas.json"))
    r = tarefas.arquivo_resultado(7)
    assert r == tmp_path / "outra" / "tarefas" / "7.md" and r.parent.is_dir()


def test_arquivo_resultado_com_arq_explicito(tmp_path, monkeypatch):
    monkeypatch.setattr(tarefas, "PASTA_RESULTADOS", tmp_path / "padrao")
    monkeypatch.setenv("VARD_TAREFAS_ARQUIVO", str(tmp_path / "env" / "tarefas.json"))
    assert tarefas.arquivo_resultado(3, tmp_path / "x" / "t.json") == tmp_path / "x" / "tarefas" / "3.md"
    assert tarefas.arquivo_resultado(3) == tmp_path / "env" / "tarefas" / "3.md"


def test_trocar_so_grava_uma_vez_com_a_mesma_versao(loja):
    t = tarefas.nova("delegada", "", "x", agente="claude")
    a, ok = tarefas.trocar(t.n, se_estado="preparando", se_versao=t.versao, estado="rodando")
    assert ok and a.estado == "rodando" and a.versao == t.versao + 1
    b, ok2 = tarefas.trocar(t.n, se_estado="preparando", se_versao=t.versao, estado="falhou")
    assert not ok2 and b.estado == "rodando" and tarefas.obter(t.n).versao == a.versao
    c, ok3 = tarefas.trocar(t.n, se_estado="rodando", se_versao=t.versao, estado="falhou")
    assert not ok3 and c.estado == "rodando"



def test_adaptador_legado_so_le_sem_regravar(loja):
    # Adaptador legado: tarefa histórica com liv vira agente_remoto só na leitura.
    bruto = '{"proximo": 2, "tarefas": [{"n": 1, "ferramenta": "liv", "repo": "", "pedido": "oi"}]}'
    loja.write_text(bruto, encoding="utf-8")
    assert tarefas.obter(1).ferramenta == "agente_remoto"
    assert loja.read_text(encoding="utf-8") == bruto
    with pytest.raises(ValueError):
        tarefas.nova("liv", "", "nova")  # Legado não é aceito para novas tarefas.
