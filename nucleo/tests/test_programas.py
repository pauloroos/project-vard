from pathlib import Path

from vard import programas


def test_normalizar_url_nome_conhecido():
    assert programas.normalizar_url("youtube") == "https://youtube.com"
    assert programas.normalizar_url("YouTube") == "https://youtube.com"


def test_normalizar_url_dominio_sem_esquema():
    assert programas.normalizar_url("app.exemplo.com") == "https://app.exemplo.com"


def test_sites_embutidos_sao_publicos():
    # Guarda contra dado pessoal voltando para o código: só sites públicos, conhecidos.
    assert set(programas.SITES) == {"youtube", "gmail", "github", "whatsapp", "chatgpt", "claude"}


def test_sites_do_usuario_sobrescrevem_e_estendem(tmp_path: Path):
    arq = tmp_path / "programas.toml"
    arq.write_text(
        '[sites]\nyoutube = "https://meu.exemplo.com/youtube"\nmeuapp = "https://app.exemplo.com"\n',
        encoding="utf-8",
    )
    sites = programas.carregar_sites(arq)
    assert sites == {"youtube": "https://meu.exemplo.com/youtube", "meuapp": "https://app.exemplo.com"}
    assert programas.normalizar_url("youtube", sites) == "https://meu.exemplo.com/youtube"
    assert programas.normalizar_url("MeuApp", sites) == "https://app.exemplo.com"
    assert programas.normalizar_url("github", sites) == "https://github.com"


def test_sites_do_usuario_sem_arquivo_vira_vazio(tmp_path: Path):
    assert programas.carregar_sites(tmp_path / "nao-existe.toml") == {}
    assert programas.normalizar_url("youtube") == "https://youtube.com"


def test_sites_do_usuario_normaliza_acentos(tmp_path: Path):
    arq = tmp_path / "programas.toml"
    arq.write_text('[sites]\n"meu aplicativo" = "https://app.exemplo.com"\n', encoding="utf-8")
    sites = programas.carregar_sites(arq)
    assert programas.normalizar_url("Meu Aplicativo", sites) == "https://app.exemplo.com"


def test_normalizar_url_completa_passa_intacta():
    assert programas.normalizar_url("http://127.0.0.1:4700/?mute=1") == "http://127.0.0.1:4700/?mute=1"


def test_normalizar_url_texto_livre_vira_busca():
    assert programas.normalizar_url("previsão do tempo manaus") == (
        "https://www.google.com/search?q=previs%C3%A3o+do+tempo+manaus"
    )


def test_resolver_programa_por_apelido():
    assert programas.resolver_programa("vscode", {"vscode": "code"}) == "code"
    assert programas.resolver_programa("VS Code", {"vs code": "code"}) == "code"


def test_resolver_programa_no_path(monkeypatch):
    monkeypatch.setattr(programas.shutil, "which", lambda n: r"X:\x\notepad.exe" if n == "notepad" else None)
    assert programas.resolver_programa("notepad", {}) == r"X:\x\notepad.exe"


def test_resolver_programa_desconhecido(monkeypatch):
    monkeypatch.setattr(programas.shutil, "which", lambda n: None)
    monkeypatch.setattr(programas, "_atalho_menu_iniciar", lambda n: None)
    assert programas.resolver_programa("programa que não existe", {}) is None


def test_carregar_apelidos(tmp_path: Path):
    arq = tmp_path / "programas.toml"
    arq.write_text('[apelidos]\nvscode = "code"\nchrome = "chrome"\n', encoding="utf-8")
    assert programas.carregar_apelidos(arq) == {"vscode": "code", "chrome": "chrome"}


def test_carregar_apelidos_normaliza_acentos(tmp_path: Path):
    arq = tmp_path / "programas.toml"
    arq.write_text('[apelidos]\n"calculadora científica" = "calc"\n', encoding="utf-8")
    assert programas.resolver_programa("Calculadora Cientifica", programas.carregar_apelidos(arq)) == "calc"


def test_carregar_apelidos_sem_arquivo_vira_vazio(tmp_path: Path):
    assert programas.carregar_apelidos(tmp_path / "nao-existe.toml") == {}


def test_atalho_menu_iniciar_acha_lnk(tmp_path: Path, monkeypatch):
    raiz = tmp_path / "Microsoft/Windows/Start Menu/Programs"
    raiz.mkdir(parents=True)
    (raiz / "Visual Studio Code.lnk").write_bytes(b"")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    assert programas._atalho_menu_iniciar("visual studio code") == str(raiz / "Visual Studio Code.lnk")
    assert programas._atalho_menu_iniciar("nada") is None
