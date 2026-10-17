"""Detecção das CLIs e validação do cadastro cli-* do painel (T17a da 0.8).

A detecção só olha o PATH e roda `--version` (e `agy models` para a lista do
agy): nunca prompt, nunca caminho absoluto na resposta. Os executáveis usados
aqui são FALSOS, criados numa pasta temporária; nenhuma CLI real é chamada.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import guarda_pc
import server
from vard.cerebro import cli_deteccao


def _liberar_dubles(monkeypatch, pasta: Path) -> None:
    """Guarda: executa só os .cmd falsos deste tmp, revisados abaixo; o resto segue bloqueado."""
    original = guarda_pc.verificar_comando
    raiz = pasta.resolve()

    def verificado(args, kwargs):
        partes = ([os.fspath(a) for a in args] if isinstance(args, (list, tuple))
                  else shlex.split(str(args), posix=False))
        if partes:
            alvo = Path(str(kwargs.get("executable") or partes[0]).strip('"')).resolve()
            if alvo.suffix.lower() in {".cmd", ".bat"} and alvo.parent == raiz:
                return
        original(args, kwargs)

    monkeypatch.setattr(guarda_pc, "verificar_comando", verificado)


@pytest.fixture
def pasta_bin(tmp_path: Path, monkeypatch):
    """PATH contendo só a pasta temporária, mais o registro das execuções falsas."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    registro = tmp_path / "execucoes.txt"
    monkeypatch.setenv("PATH", str(bin_dir))
    _liberar_dubles(monkeypatch, bin_dir)
    return bin_dir, registro


def _falso_claude(bin_dir: Path, registro: Path) -> None:
    """claude.cmd falso: registra os argumentos e responde a versão."""
    (bin_dir / "claude.cmd").write_text(
        "@echo off\r\n"
        f'echo %*>>"{registro}"\r\n'
        "echo 1.2.3-falso\r\n",
        encoding="ascii",
    )


def _falso_agy(bin_dir: Path, registro: Path) -> None:
    """agy.cmd falso: registra os argumentos, lista modelos em `models` e responde a versão."""
    (bin_dir / "agy.cmd").write_text(
        "@echo off\r\n"
        f'echo %*>>"{registro}"\r\n'
        'if "%1"=="models" (\r\n'
        "  echo gemini-3.8-flash-low\r\n"
        "  echo gemini-3.8-pro\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        "echo 0.9.0-falso\r\n",
        encoding="ascii",
    )


def _falso_agy_real(bin_dir: Path, registro: Path) -> None:
    """agy.cmd falso no formato real do `agy models`: cabeçalho e linhas `id<TAB>Nome`."""
    (bin_dir / "agy.cmd").write_text(
        "@echo off\r\n"
        f'echo %*>>"{registro}"\r\n'
        'if not "%1"=="models" goto versao\r\n'
        "echo Fetching available models...\r\n"
        "echo gemini-3.8-flash-low\tGemini 3.8 Flash (Low)\r\n"
        "echo claude-opus-5-5-high\tClaude Opus 5.5 (High)\r\n"
        "exit /b 0\r\n"
        ":versao\r\n"
        "echo 1.4.0-falso\r\n",
        encoding="ascii",
    )


class TestDetectar:
    def test_modelos_do_agy_guardam_so_o_id(self, pasta_bin):
        bin_dir, registro = pasta_bin
        _falso_agy_real(bin_dir, registro)
        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}
        assert itens["cli-agy"]["modelos"] == ["gemini-3.8-flash-low", "claude-opus-5-5-high"]

    def test_detectar_sem_cli_instalada(self, pasta_bin):
        itens = cli_deteccao.detectar()
        assert [i["tipo"] for i in itens] == ["cli-claude", "cli-agy", "cli-codex", "cli-opencode"]
        for item in itens:
            assert set(item) == {"tipo", "instalada", "versao", "modelos"}
            assert item["instalada"] is False
            assert item["versao"] == ""
            assert item["modelos"] == []

    def test_detectar_com_claude_e_agy_falsos_no_path(self, pasta_bin):
        bin_dir, registro = pasta_bin
        _falso_claude(bin_dir, registro)
        _falso_agy(bin_dir, registro)

        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}

        assert itens["cli-claude"]["instalada"] is True
        assert itens["cli-claude"]["versao"] == "1.2.3-falso"
        assert itens["cli-claude"]["modelos"] == cli_deteccao.MODELOS_SUGERIDOS["cli-claude"]
        assert itens["cli-agy"]["instalada"] is True
        assert itens["cli-agy"]["versao"] == "0.9.0-falso"
        assert itens["cli-agy"]["modelos"] == ["gemini-3.8-flash-low", "gemini-3.8-pro"]

    def test_detectar_nao_roda_prompt(self, pasta_bin):
        bin_dir, registro = pasta_bin
        _falso_claude(bin_dir, registro)
        _falso_agy(bin_dir, registro)

        cli_deteccao.detectar()

        linhas = {l.strip() for l in registro.read_text(encoding="utf-8").splitlines() if l.strip()}
        assert linhas == {"--version", "models"}          # nada de -p/--print/prompt

    def test_resposta_sem_caminho_absoluto(self, pasta_bin, tmp_path):
        bin_dir, registro = pasta_bin
        _falso_claude(bin_dir, registro)
        _falso_agy(bin_dir, registro)

        itens = cli_deteccao.detectar()
        texto = json.dumps(itens, ensure_ascii=False)

        assert str(bin_dir) not in texto
        assert str(tmp_path) not in texto
        assert re.search(r"[A-Za-z]:\\", texto) is None
        assert "caminho" not in texto.lower() and "path" not in texto.lower()

    def test_detectar_ignora_cli_que_nao_responde(self, pasta_bin):
        bin_dir, registro = pasta_bin
        # claude.cmd que falha (não devolve versão): segue instalada, sem versão
        (bin_dir / "claude.cmd").write_text(
            "@echo off\r\n" f'echo %*>>"{registro}"\r\n' "exit /b 1\r\n",
            encoding="ascii",
        )
        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}
        assert itens["cli-claude"]["instalada"] is True
        assert itens["cli-claude"]["versao"] == ""

    def test_detectar_cenario_misto_so_uma_instalada(self, pasta_bin):
        """Só uma CLI no PATH: ela responde, a outra permanece não instalada."""
        bin_dir, registro = pasta_bin
        _falso_agy(bin_dir, registro)

        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}

        assert itens["cli-agy"]["instalada"] is True
        assert itens["cli-agy"]["versao"] == "0.9.0-falso"
        assert itens["cli-claude"] == {"tipo": "cli-claude", "instalada": False,
                                       "versao": "", "modelos": []}
        # a CLI ausente nunca é executada: só os dois comandos do agy no registro
        linhas = [l.strip() for l in registro.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert sorted(linhas) == ["--version", "models"]


def test_rota_cli_detectar(pasta_bin):
    bin_dir, registro = pasta_bin
    _falso_agy(bin_dir, registro)
    cliente = TestClient(server.app, base_url="http://127.0.0.1:4700")

    r = cliente.get("/cli/detectar")

    assert r.status_code == 200
    itens = {i["tipo"]: i for i in r.json()}
    assert itens["cli-agy"]["instalada"] is True
    assert itens["cli-claude"]["instalada"] is False


class TestValidarProvedorCli:
    def _entrada(self, **extra) -> dict:
        base = {"id": "claude-1", "nome": "Claude Code", "tipo": "cli-claude", "modelo": "claude-sonnet-5-5"}
        base.update(extra)
        return base

    def test_padroes_yolo_enxuto_e_esforco(self):
        p = cli_deteccao.validar_provedor_cli(self._entrada())
        assert p["yolo"] is True
        assert p["enxuto"] is False
        assert p["esforco"] is None

    def test_campos_opcionais_respeitados(self):
        p = cli_deteccao.validar_provedor_cli(self._entrada(yolo=False, enxuto=True, esforco="alto"))
        assert (p["yolo"], p["enxuto"], p["esforco"]) == (False, True, "alto")

    def test_recusa_url_base(self):
        with pytest.raises(ValueError, match="url_base"):
            cli_deteccao.validar_provedor_cli(self._entrada(url_base="http://127.0.0.1:1234"))

    def test_recusa_credencial(self):
        with pytest.raises(ValueError, match="credencial"):
            cli_deteccao.validar_provedor_cli(self._entrada(credencial_ref="provedor:x"))

    def test_recusa_tipo_nao_cli(self):
        with pytest.raises(ValueError, match="tipo"):
            cli_deteccao.validar_provedor_cli(self._entrada(tipo="local", url_base="http://x"))

    def test_exige_modelo(self):
        with pytest.raises(ValueError, match="modelo"):
            cli_deteccao.validar_provedor_cli(self._entrada(modelo="   "))

    def test_recusa_yolo_nao_booleano(self):
        with pytest.raises(ValueError, match="yolo"):
            cli_deteccao.validar_provedor_cli(self._entrada(yolo="sim"))

    def test_recusa_cli_codex_como_cerebro(self):
        """Codex é detectável mas não pode ser cérebro ativo (só tarefas delegadas)."""
        with pytest.raises(ValueError, match="tipo"):
            cli_deteccao.validar_provedor_cli(self._entrada(tipo="cli-codex"))

    def test_recusa_cli_opencode_como_cerebro(self):
        """OpenCode é detectável mas não pode ser cérebro ativo (só tarefas delegadas)."""
        with pytest.raises(ValueError, match="tipo"):
            cli_deteccao.validar_provedor_cli(self._entrada(tipo="cli-opencode"))


class TestDetectarCodexOpenCode:
    """Detecção de Codex e OpenCode (Rodada 4): só detecção, não cadastro."""

    def _falso_codex(self, bin_dir: Path, registro: Path) -> None:
        (bin_dir / "codex.cmd").write_text(
            "@echo off\r\n"
            f'echo %*>>"{registro}"\r\n'
            "echo 0.1.2504-falso\r\n",
            encoding="ascii",
        )

    def _falso_opencode(self, bin_dir: Path, registro: Path) -> None:
        (bin_dir / "opencode.cmd").write_text(
            "@echo off\r\n"
            f'echo %*>>"{registro}"\r\n'
            "echo 0.3.2-falso\r\n",
            encoding="ascii",
        )

    def test_detectar_codex_instalado(self, pasta_bin):
        bin_dir, registro = pasta_bin
        self._falso_codex(bin_dir, registro)
        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}
        assert itens["cli-codex"]["instalada"] is True
        assert itens["cli-codex"]["versao"] == "0.1.2504-falso"
        assert itens["cli-codex"]["modelos"] == []

    def test_detectar_opencode_instalado(self, pasta_bin):
        bin_dir, registro = pasta_bin
        self._falso_opencode(bin_dir, registro)
        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}
        assert itens["cli-opencode"]["instalada"] is True
        assert itens["cli-opencode"]["versao"] == "0.3.2-falso"
        assert itens["cli-opencode"]["modelos"] == []

    def test_detectar_codex_e_opencode_sem_instalacao(self, pasta_bin):
        itens = {i["tipo"]: i for i in cli_deteccao.detectar()}
        assert itens["cli-codex"]["instalada"] is False
        assert itens["cli-opencode"]["instalada"] is False
