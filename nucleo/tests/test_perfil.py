"""Perfil do agente (T14a): arquivo, migração da persona.md e montagem da persona."""
import json
import logging

from vard import config as vconfig
from vard import perfil
from vard import habilidades
import pytest

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


@pytest.mark.parametrize("ligada", [None, False, True])
def test_persona_so_orienta_com_habilidade_do_usuario_ligada(monkeypatch, ligada):
    monkeypatch.setattr(perfil, "_bloco_produto", lambda: "")
    if ligada is not None:
        habilidades.gravar_habilidades({"versao": 1, "habilidades": [{
            "id": "rotina-dia", "nome": "Planejar", "quando": ["bom dia"],
            "instrucoes": "Consultar agenda.", "ligada": ligada, "situacao": "treinada",
            "criada_em": "2026-10-17T12:00:00Z", "validada_em": None,
        }]})
    texto = perfil.montar_persona(perfil.Perfil(), "Aurora", "")
    assert ("listar_habilidades" in texto) is (ligada is True)
    if ligada:
        assert "antes de agir" in texto
        assert "se a ferramenta estiver disponível" in texto


@pytest.mark.parametrize("desligada", [False, True])
def test_persona_orienta_com_fabrica_personalizada_ligada(monkeypatch, desligada):
    monkeypatch.setattr(perfil, "_bloco_produto", lambda: "")
    habilidades.gravar_habilidades({"versao": 1, "habilidades": [], "desligadas": ["conversa"] if desligada else [],
        "fabrica": {"conversa": {"instrucoes": "Responda curto."}}})
    texto = perfil.montar_persona(perfil.Perfil(), "Aurora", "")
    assert ("listar_habilidades" in texto) is (not desligada)


def test_persona_com_habilidades_invalidas_preserva_perfil(monkeypatch):
    monkeypatch.setattr(perfil, "_bloco_produto", lambda: "")
    arq = habilidades.caminho()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("{quebrado", encoding="utf-8")
    texto = perfil.montar_persona(perfil.Perfil(instrucoes=INSTRUCOES), "Aurora", "")
    assert INSTRUCOES in texto
    assert "listar_habilidades" not in texto


def test_perfil_json_invalido_cai_no_padrao_e_avisa(caplog):
    arq = vconfig.arquivo_config("perfil.json")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("{isso nao e json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        p = perfil.ler()
    assert p == perfil.Perfil()
    assert arq.exists(), "o arquivo ilegível fica no lugar, para o usuário"
    assert any("perfil" in r.getMessage().lower() for r in caplog.records), "o aviso é registrado"


def test_perfil_json_em_branco_ainda_migra_persona_md():
    """Um perfil.json salvo com todos os campos vazios não esconde a persona.md do usuário."""
    _persona_md("Você é a Aurora, assistente de Fulano.")
    perfil.gravar(perfil.Perfil())
    assert perfil.ler().instrucoes == "Você é a Aurora, assistente de Fulano."


def test_bloco_do_produto_usa_nome_e_usuario_reais():
    texto = perfil.montar_persona(perfil.Perfil(), "Aurora", "Beltrano")
    assert "Você é o Vard, assistente de Fulano" not in texto
    assert "Você é Aurora, assistente de Beltrano." in texto
