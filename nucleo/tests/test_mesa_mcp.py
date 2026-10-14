import importlib
from pathlib import Path

import mesa_mcp
from vard import janelas


def test_abrir_url_normaliza_e_chama_startfile(monkeypatch):
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
    r = mesa_mcp.abrir_url("youtube")
    assert abertos == ["https://youtube.com"]
    assert "youtube.com" in r


def test_abrir_url_vazia_pede_o_site(monkeypatch):
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
    assert mesa_mcp.abrir_url("   ") == "Diga qual site abrir."
    assert abertos == []


def test_abrir_programa_vazio_pede_o_programa(monkeypatch):
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
    assert mesa_mcp.abrir_programa("") == "Diga qual programa abrir."
    assert abertos == []


def test_abrir_programa_desconhecido_explica(monkeypatch):
    monkeypatch.setattr(mesa_mcp.programas, "resolver_programa", lambda n, a: None)
    r = mesa_mcp.abrir_programa("xyz")
    assert "não encontrei" in r.lower()


def test_abrir_programa_conhecido(monkeypatch):
    chamados = []
    monkeypatch.setattr(mesa_mcp.programas, "resolver_programa", lambda n, a: "code")
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: chamados.append(alvo))
    r = mesa_mcp.abrir_programa("vscode")
    assert chamados == ["code"] and "vscode" in r


def test_focar_janela_inexistente(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [])
    assert "nenhuma janela" in mesa_mcp.focar_janela("qualquer").lower()


def test_focar_janela_existente(monkeypatch):
    j = janelas.Janela(7, "YouTube - Google Chrome", "chrome.exe")
    focadas = []
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [j])
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda x: focadas.append(x) or True)
    assert "YouTube" in mesa_mcp.focar_janela("youtube") and focadas == [j]


def test_focar_janela_recusada(monkeypatch):
    j = janelas.Janela(7, "YouTube - Google Chrome", "chrome.exe")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [j])
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda x: False)
    assert "recusou" in mesa_mcp.focar_janela("youtube")


class _Mss:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def shot(self, output): Path(output).write_bytes(b"png"); return output


def test_print_da_tela_grava_png_na_pasta_de_prints(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path / "prints")
    monkeypatch.setattr(mesa_mcp.mss, "mss", lambda: _Mss())
    r = mesa_mcp.print_da_tela()
    gravados = list((tmp_path / "prints").glob("tela-*.png"))
    assert len(gravados) == 1 and str(gravados[0]) in r


def test_print_da_tela_ignora_pasta_e_extensao_do_caminho(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path / "prints")
    monkeypatch.setattr(mesa_mcp.mss, "mss", lambda: _Mss())
    mesa_mcp.print_da_tela("X:/qualquer/coisa.docx")
    assert (tmp_path / "prints" / "coisa.png").exists()
    assert not Path("X:/qualquer/coisa.docx").exists()


def test_print_da_tela_nao_sobrescreve(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path)
    monkeypatch.setattr(mesa_mcp.mss, "mss", lambda: _Mss())
    (tmp_path / "x.png").write_bytes(b"antigo")
    mesa_mcp.print_da_tela("x.png"); mesa_mcp.print_da_tela("x.png")
    assert (tmp_path / "x.png").read_bytes() == b"antigo"
    assert (tmp_path / "x-2.png").exists() and (tmp_path / "x-3.png").exists()


def test_fechar_janela_existente_e_inexistente(monkeypatch):
    j = janelas.Janela(7, "Bloco de notas", "notepad.exe")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [j])
    monkeypatch.setattr(mesa_mcp.janelas, "fechar", lambda x: True)
    assert "Pedi para fechar" in mesa_mcp.fechar_janela("bloco")
    monkeypatch.setattr(mesa_mcp.janelas, "fechar", lambda x: False)
    assert "já não existe" in mesa_mcp.fechar_janela("bloco")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [])
    assert "Nenhuma janela" in mesa_mcp.fechar_janela("bloco")


def test_listar_janelas_vazio_e_truncado(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [])
    assert "Nenhuma janela" in mesa_mcp.listar_janelas()
    muitas = [janelas.Janela(i, f"Janela {i}", "x.exe") for i in range(45)]
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: muitas)
    saida = mesa_mcp.listar_janelas()
    assert saida.count("\n- ") == 39 and "(+5 janelas não listadas)" in saida


def test_ferramenta_nunca_levanta(monkeypatch):
    def explode(): raise RuntimeError("boom")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", explode)
    r = mesa_mcp.listar_janelas()
    assert r.startswith("Não consegui listar as janelas") and "boom" in r


def test_hora_atual_em_portugues():
    import datetime as dt

    r = mesa_mcp.hora_atual()
    assert "Agora são" in r
    assert any(d in r for d in mesa_mcp.DIAS)
    assert str(dt.datetime.now().year) in r


def test_apelidos_e_sites_vem_da_config_do_usuario(tmp_path: Path, monkeypatch):
    """VARD_CONFIG apontando para outra pasta muda o que a mesa resolve (caminho com espaço de propósito)."""
    pasta = tmp_path / "pasta com espaço"
    pasta.mkdir()
    (pasta / "programas.toml").write_text(
        '[apelidos]\nvscode = "code"\n\n[sites]\nmeuapp = "https://app.exemplo.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("VARD_CONFIG", str(pasta))
    abertos: list[str] = []
    try:
        importlib.reload(mesa_mcp)
        monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
        r_programa = mesa_mcp.abrir_programa("vscode")
        r_site = mesa_mcp.abrir_url("meuapp")
    finally:
        # Volta para a config vazia do isolamento de testes para não contaminar os próximos.
        monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
        importlib.reload(mesa_mcp)
    assert abertos == ["code", "https://app.exemplo.com"]
    assert "vscode" in r_programa and "app.exemplo.com" in r_site
