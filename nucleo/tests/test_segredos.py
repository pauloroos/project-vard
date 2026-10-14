import json
from pathlib import Path

import pytest

from vard import segredos


def test_carregar_le_toml(tmp_path: Path):
    arq = tmp_path / "segredos.toml"
    arq.write_text('[omniroute]\nchave = "abc"\n', encoding="utf-8")
    dados = segredos.carregar(arq)
    assert dados["omniroute"]["chave"] == "abc"


def test_carregar_sem_arquivo_explica(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as exc:
        segredos.carregar(tmp_path / "nao-existe.toml")
    assert "segredos.toml" in str(exc.value)


def test_escrever_mcp_json_tem_os_servidores_locais(tmp_path: Path):
    repo = Path("X:/vard/nucleo")
    destino = tmp_path / "mcp.json"
    segredos.escrever_mcp_json({"omniroute": {"chave": "x"}}, repo, destino)
    lista = json.loads(destino.read_text(encoding="utf-8"))
    assert [s["name"] for s in lista] == list(segredos.SERVIDORES_LOCAIS)
    oficina = [s for s in lista if s["name"] == "oficina"][0]
    assert oficina["command"] == "uv"
    assert oficina["args"] == ["run", "--project", str(repo), "python", str(repo / "oficina_mcp.py")]


def test_mcp_json_nunca_leva_o_token(tmp_path: Path):
    destino = tmp_path / "mcp.json"
    segredos.escrever_mcp_json({"ai_memory": {"url": "http://h/mcp", "token": "SEGREDO123"}}, Path("X:/vard/nucleo"), destino)
    texto = destino.read_text(encoding="utf-8")
    assert "SEGREDO123" not in texto
    assert [s["name"] for s in json.loads(texto)] == ["mesa", "oficina", "consulta", "memoria", "reuniao"]


def test_chave_lmstudio_le_a_secao():
    assert segredos.chave_lmstudio({"lmstudio": {"chave": "k"}}) == "k"


def test_chave_lmstudio_ausente_vira_vazio():
    assert segredos.chave_lmstudio({"omniroute": {"chave": "x"}}) == ""


def test_chaves_telegram(tmp_path: Path):
    arq = tmp_path / "segredos.toml"
    arq.write_text('[telegram]\ntoken = "t"\nchat_id = "123"\n', encoding="utf-8")
    dados = segredos.carregar(arq)
    assert segredos.chave_telegram(dados) == "t" and segredos.chat_id_telegram(dados) == "123"
    assert segredos.chat_id_telegram({}) == ""


def test_gravar_preserva_o_resto(tmp_path: Path):
    arq = tmp_path / "segredos.toml"
    arq.write_text('[telegram]\ntoken = "t"\nchat_id = "1"\n', encoding="utf-8")
    segredos.gravar("coolify.exemplo", "token", "abc", arq)
    segredos.gravar("coolify.exemplo", "url", "https://painel/", arq)
    segredos.gravar("coolify.exemplo", "token", "novo", arq)
    dados = segredos.carregar(arq)
    assert dados["telegram"] == {"token": "t", "chat_id": "1"}
    assert segredos.coolify(dados) == {"exemplo": {"url": "https://painel", "token": "novo"}}


def test_gravar_em_valor_que_nao_e_secao_recusa(tmp_path: Path):
    arq = tmp_path / "segredos.toml"
    arq.write_text('a = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        segredos.gravar("a.b", "c", "v", arq)


def test_leitores_novos_com_padrao_vazio():
    assert segredos.coolify({}) == {}
    assert segredos.remoto_ssh({}) == ("", "")
    assert segredos.remoto_ssh({"remoto": {"ssh_chave": "k", "ssh_destino": "u@h"}}) == ("k", "u@h")
    assert segredos.ai_memory({"ai_memory": {"url": "http://h/mcp", "token": "t"}}) == ("http://h/mcp", "t")
    assert segredos.google({}) == ("", "")
    assert segredos.url_omniroute({}) == ""
    assert segredos.url_omniroute({"omniroute": {"url": "https://roteador.exemplo.com"}}) == "https://roteador.exemplo.com"


def test_url_omniroute_com_segredos_ausente_e_vazio():
    # Arquivo não criado em pasta isolada: integração não configurada, sem lançar.
    assert segredos.url_omniroute() == ""


def test_huggingface_le_o_token_e_ausente_vira_vazio():
    assert segredos.huggingface({"huggingface": {"token": "hf_x"}}) == "hf_x"
    assert segredos.huggingface({}) == ""
