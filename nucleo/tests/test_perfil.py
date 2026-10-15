"""Perfil do agente (T14a): arquivo, migração da persona.md e montagem da persona."""
import json
import logging

from vard import config as vconfig
from vard import perfil

INSTRUCOES = "Responda em frases curtas e confirme ações feitas."


def _persona_md(texto: str):
    arq = vconfig.arquivo_config("persona.md")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(texto, encoding="utf-8")
    return arq


def test_sem_arquivo_devolve_padrao():
    p = perfil.ler()
    assert p == perfil.Perfil()
    assert p.versao == 1
    assert p.tom == "" and p.personalidade == "" and p.instrucoes == "" and p.sobre_usuario == ""


def test_gravar_e_ler_ida_e_volta():
    p = perfil.Perfil(tom="direto e calmo", personalidade="responde pouco", instrucoes=INSTRUCOES,
                      sobre_usuario="Fulano gosta de respostas curtas.")
    perfil.gravar(p)
    arq = vconfig.arquivo_config("perfil.json")
    assert arq.exists()
    assert perfil.ler() == p
    assert json.loads(arq.read_text(encoding="utf-8"))["versao"] == 1
    assert not list(arq.parent.glob("*.tmp")), "a gravação é atômica e não deixa arquivo temporário"


def test_migra_persona_md_para_instrucoes_sem_apagar():
    arq = _persona_md("Você é a Aurora, assistente de Fulano. Fale português do Brasil.")
    p = perfil.ler()
    assert p.instrucoes == "Você é a Aurora, assistente de Fulano. Fale português do Brasil."
    assert arq.exists(), "o persona.md antigo não é apagado"
    assert "Aurora" in arq.read_text(encoding="utf-8")


def test_nao_migra_se_perfil_existe():
    _persona_md("texto antigo da persona.md")
    perfil.gravar(perfil.Perfil(instrucoes=INSTRUCOES))
    p = perfil.ler()
    assert p.instrucoes == INSTRUCOES


def test_montar_persona_ordem_cabecalho_instrucoes_sobre_bloco_produto():
    p = perfil.Perfil(tom="direto e calmo", personalidade="responde pouco",
                      instrucoes=INSTRUCOES, sobre_usuario="Fulano gosta de café.")
    texto = perfil.montar_persona(p, "Aurora", "Fulano")
    trechos = ["Nome do assistente: Aurora", "Como chamar a pessoa: Fulano", "Tom: direto e calmo",
               "Personalidade: responde pouco", INSTRUCOES, "Fulano gosta de café.", "disparar_tarefa"]
    pos = [texto.index(t) for t in trechos]
    assert all(a < b for a, b in zip(pos, pos[1:])), f"ordem errada: {pos}\n{texto}"
    assert "hora_atual" in texto  # o bloco do produto vem do repositório


def test_montar_persona_sem_usuario_nao_quebra():
    texto = perfil.montar_persona(perfil.Perfil(instrucoes=INSTRUCOES), "Aurora", "")
    assert "Aurora" in texto and INSTRUCOES in texto
    assert "Como chamar a pessoa" not in texto
    assert isinstance(perfil.montar_persona(perfil.Perfil(), "", ""), str)


def test_perfil_json_invalido_cai_no_padrao_e_avisa(caplog):
    arq = vconfig.arquivo_config("perfil.json")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("{isso nao e json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        p = perfil.ler()
    assert p == perfil.Perfil()
    assert arq.exists(), "o arquivo ilegível fica no lugar, para o usuário"
    assert any("perfil" in r.getMessage().lower() for r in caplog.records), "o aviso é registrado"
