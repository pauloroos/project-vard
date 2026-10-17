"""Contrato das configurações: disco isolado e HTTP falso, sem serviços reais."""
import json
from pathlib import Path

import pytest


def test_aparencia_usa_hud_e_preserva_campos(monkeypatch, tmp_path):
    from vard import ajustes
    alvo = tmp_path / "hud" / "hud.config.json"
    alvo.parent.mkdir()
    alvo.write_text(json.dumps({"nome": "Aurora", "futuro": {"a": 1}}), encoding="utf-8")
    ajustes.mudar_aparencia("#ff00aa", 0.6)
    assert json.loads(alvo.read_text(encoding="utf-8")) == {
        "nome": "Aurora", "futuro": {"a": 1}, "cor_elementos": "#ff00aa", "opacidade_elementos": 0.6}
    antes = alvo.read_bytes()
    with pytest.raises(ValueError):
        ajustes.mudar_aparencia("rosa", 2)
    assert alvo.read_bytes() == antes
    assert not list(alvo.parent.glob("*.tmp"))


def test_contrato_compartilhado():
    from vard.ajustes import validar_documento
    casos = json.loads((Path(__file__).parents[2] / "tests/fixtures/ajustes/contrato.json").read_text(encoding="utf-8"))
    for caso in casos:
        if caso["valido"]:
            validar_documento(caso["arquivo"], caso["valor"])
        else:
            with pytest.raises(ValueError, match="."):
                validar_documento(caso["arquivo"], caso["valor"])


def test_mcp_confirma_antes_de_efeitos_e_nao_vaza(monkeypatch):
    import configuracoes_mcp as mcp
    from vard import ajustes
    ajustes.cadastrar_provedor({"id": "local", "nome": "Local", "tipo": "lmstudio", "url_base": "http://127.0.0.1:1234/v1", "modelo": "modelo-ficticio"})
    assert "confirmação" in mcp.remover_provedor("local")
    assert len(ajustes.ler_documento("paineis")["provedores"]) == 1
    assert "confirmação" in mcp.escolher_quem_responde("local")
    assert ajustes.ler_documento("paineis")["ativo"] is None
    assert "Quem responde" in mcp.escolher_quem_responde("local", confirmado=True)
    assert ajustes.ler_documento("paineis")["ativo"] == "local"
    assert ajustes.ler_documento("hud")["cerebro"] == "proprio"
    assert "Removi" in mcp.remover_provedor("local", confirmado=True)
    monkeypatch.setattr(ajustes, "mudar_aparencia", lambda *a: (_ for _ in ()).throw(OSError("detalhe privado")))
    assert "detalhe privado" not in mcp.mudar_aparencia("#ffffff", 1)


def test_habilidades_programas_e_perfil_preservam_desconhecidos():
    from vard import ajustes
    ajustes.gravar_documento("perfil", {"versao": 1, "tom": "calmo", "futuro": 3})
    ajustes.gravar_documento("perfil", {**ajustes.ler_documento("perfil"), "tom": "direto"})
    assert ajustes.ler_documento("perfil")["futuro"] == 3
    ajustes.cadastrar_habilidade({"id": "rotina", "nome": "Rotina", "quando": ["começar"], "instrucoes": "Consulte a agenda."})
    ajustes.cadastrar_habilidade({"id": "desligada", "nome": "Desligada", "quando": ["x"], "instrucoes": "x", "ligada": False})
    assert [h["id"] for h in ajustes.listar_habilidades()] == ["rotina"]
    ajustes.editar_habilidade("rotina", {"nome": "Rotina nova"})
    ajustes.marcar_habilidade_validada("rotina")
    assert ajustes.listar_habilidades()[0]["situacao"] == "validada"
    ajustes.cadastrar_programa("editor", "editor.exe")
    ajustes.cadastrar_programa("busca", "https://example.com", site=True)
    assert ajustes.ler_documento("programas")["sites"]["busca"] == "https://example.com"
    ajustes.remover_programa("editor")
    assert ajustes.ler_documento("programas")["apelidos"] == {}


def test_editar_habilidade_preserva_dados_futuros():
    from vard import ajustes
    ajustes.cadastrar_habilidade({"id": "rotina", "nome": "Rotina", "quando": ["começar"], "instrucoes": "Consulte a agenda.", "futuro": 3})
    ajustes.editar_habilidade("rotina", {"nome": "Outra rotina"})
    assert ajustes.listar_habilidades()[0]["futuro"] == 3


def test_mcp_instala_por_http_so_apos_confirmacao(monkeypatch):
    import configuracoes_mcp as mcp
    from vard import ajustes
    chamadas = []
    def http(metodo, rota, corpo=None):
        chamadas.append((metodo, rota, corpo))
        if rota == "/instalaveis":
            return {"itens": [{"id": "cli", "nome": "CLI fictícia", "tamanho_mb": 120}]}
        return {"estado": "instalando"}
    monkeypatch.setattr(ajustes, "http_local", http)
    assert "120" in mcp.instalar("cli")
    assert not any(m == "POST" for m, *_ in chamadas)
    assert "instalando" in mcp.instalar("cli", confirmado=True)
    assert chamadas[-1] == ("POST", "/instalaveis/cli/instalar", {"confirmado": True})


def test_mcp_nao_aceita_segredo_nem_o_devolve():
    import configuracoes_mcp as mcp
    from vard import ajustes
    assert "chave na tela de Configurações" in mcp.cadastrar_provedor({"chave": "segredo-ficticio"})
    ajustes.gravar_documento("hud", {"gemini_chave": "segredo-ficticio", "nome": "Aurora"})
    assert "segredo-ficticio" not in mcp.ver_configuracoes()
    assert "gemini_chave" not in mcp.ver_configuracoes()


@pytest.mark.asyncio
async def test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia():
    import sys
    from vard import ajustes
    from vard.cerebro.ferramentas import GerenciadorFerramentas
    gerente = GerenciadorFerramentas()
    try:
        await gerente.adicionar_stdio("configuracoes", sys.executable, [str(Path(__file__).parents[1] / "configuracoes_mcp.py")])
        nomes = {f["nome"] for f in await gerente.listar_todas()}
        assert nomes == {"ver_configuracoes", "mudar_aparencia", "listar_vozes", "escolher_voz", "listar_provedores", "cadastrar_provedor", "editar_provedor", "remover_provedor", "escolher_quem_responde", "testar_provedor", "listar_instalaveis", "instalar", "andamento_instalacao", "listar_habilidades", "cadastrar_habilidade", "editar_habilidade", "excluir_habilidade", "marcar_habilidade_validada", "listar_programas", "cadastrar_programa", "remover_programa"}
        assert await gerente.chamar("configuracoes", "mudar_aparencia", {"cor": "#112233", "opacidade": 0.5}) == "Aparência atualizada."
        assert ajustes.ler_documento("hud")["cor_elementos"] == "#112233"
        assert "confirmação" in await gerente.chamar("configuracoes", "remover_programa", {"nome": "editor"})
    finally:
        await gerente.fechar_tudo()


def test_vozes_de_fabrica_disponiveis_sem_cadastro():
    from vard import ajustes
    dados = ajustes.listar_vozes()
    # Estrutura: dict com "catalogo" (dict por provedor) e "cadastradas" (lista)
    assert isinstance(dados, dict)
    assert "catalogo" in dados and "cadastradas" in dados
    assert isinstance(dados["catalogo"], dict)
    assert isinstance(dados["cadastradas"], list)
    # Catálogo agrupa vozes por provedor; cada valor é lista de dicts ou strings
    todos_ids: set[str] = set()
    todos_nomes: set[str] = set()
    for grupo in dados["catalogo"].values():
        for v in grupo:
            if isinstance(v, dict):
                if "id" in v: todos_ids.add(str(v["id"]))
                if "rotulo" in v: todos_nomes.add(str(v["rotulo"]))
            else:
                todos_ids.add(str(v))
                todos_nomes.add(str(v))
    assert "pf_dora" in todos_ids or any("dora" in n.lower() for n in todos_nomes)
    assert "pt-BR-FranciscaNeural" in todos_ids or any("Francisca" in n for n in todos_nomes)
    assert "Kore" in todos_ids or any("Kore" in n for n in todos_nomes)


def test_remover_programa_inexistente_retorna_mensagem_clara_sem_excecao():
    import configuracoes_mcp as mcp
    resposta = mcp.remover_programa("programa-que-nao-existe", confirmado=True)
    assert "Não achei o programa" in resposta or "não encontrado" in resposta.lower()
    # Não deve levantar exceção; o decorador @_seguro captura, mas a mensagem deve ser específica


def test_programa_cadastrado_chega_a_mesa_sem_reiniciar(monkeypatch):
    import mesa_mcp
    from vard import ajustes
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", abertos.append)
    ajustes.cadastrar_programa("editor", "editor-ficticio.exe")
    mesa_mcp.abrir_programa("editor")
    assert abertos == ["editor-ficticio.exe"]
    ajustes.cadastrar_programa("editor", "outro-ficticio.exe")
    mesa_mcp.abrir_programa("editor")
    assert abertos[-1] == "outro-ficticio.exe"


@pytest.mark.asyncio
async def test_teste_de_provedor_usa_config_salva_sem_expor_chave(monkeypatch):
    import server
    from vard import ajustes
    from vard.primeiro_uso import cerebro
    ajustes.cadastrar_provedor({"id": "nuvem", "nome": "Nuvem", "tipo": "anthropic", "url_base": "https://api.example.com", "modelo": "modelo-ficticio"})
    # Referência salva pela tela: MCP não recebe nem a referência nem a chave.
    cfg = ajustes.ler_documento("paineis")
    cfg["provedores"][0]["credencial_ref"] = "provedor:nuvem"
    ajustes.gravar_documento("paineis", cfg)
    monkeypatch.setattr(server, "_resolver_credencial_cofre", lambda *a: "segredo-ficticio")
    chamadas = []
    async def testar(**kwargs):
        chamadas.append(kwargs)
        return {"ok": True, "detalhe": "segredo-ficticio"}
    monkeypatch.setattr(cerebro, "testar_cerebro", testar)
    resposta = await server.configuracoes_testar_provedor("nuvem")
    assert resposta["ok"] is True
    assert chamadas[0]["chave"] == "segredo-ficticio"
    assert "segredo-ficticio" not in str(resposta)


def test_perfil_python_preserva_campos_futuros():
    from vard import ajustes, perfil
    ajustes.gravar_documento("perfil", {"versao": 1, "tom": "calmo", "futuro": 3})
    perfil.gravar(perfil.Perfil(tom="direto"))
    assert ajustes.ler_documento("perfil")["futuro"] == 3
