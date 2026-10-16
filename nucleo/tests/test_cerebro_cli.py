"""Testes da T15 — adaptador de CLI: dialetos stream-json → eventos do cérebro.

Cobre os 11 testes do plano para os dois dialetos, usando as fixtures da T13
(nucleo/tests/fixtures/cli/*.ndjson) e um canal injetável (sem processo real).
Os prazos são injetados: nenhum teste espera 15 s/180 s de verdade.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from vard.cerebro.cli import DIALETOS, AdaptadorCli, DialetoAgy, DialetoClaude
from vard.cerebro.provedores import ErroProvedor, EventoInferencia

FIXTURES = Path(__file__).parent / "fixtures" / "cli"

DIALETOS_TESTE = [
    pytest.param("claude", "Bash", id="claude"),
    pytest.param("agy", "run_command", id="agy"),
]


def _linhas_fixture(nome: str) -> list[str]:
    texto = (FIXTURES / nome).read_text(encoding="utf-8")
    return [linha for linha in texto.splitlines() if linha.strip()]


def _mensagens(*papéis: tuple[str, str]) -> list[dict[str, Any]]:
    """Monta histórico a partir de pares (role, content)."""
    return [{"role": r, "content": c} for r, c in papéis]


async def _coletar(
    adaptador: AdaptadorCli, mensagens, cancelamento=None, imagem=None
) -> list[EventoInferencia]:
    return [ev async for ev in adaptador.inferir(mensagens, cancelamento=cancelamento, imagem=imagem)]


class CanalFalso:
    """Canal injetável: registra envios, devolve linhas com atraso opcional e bloqueia no fim."""

    def __init__(self, linhas: list[Any] | None = None, *, bloquear_no_fim: bool = True) -> None:
        self.enviados: list[str] = []
        self.interrompecoes = 0
        self._linhas = list(linhas or [])
        self._bloquear = bloquear_no_fim

    async def enviar(self, linha: str) -> None:
        self.enviados.append(linha)

    async def linhas(self):
        for item in self._linhas:
            texto, atraso = item if isinstance(item, tuple) else (item, 0.0)
            if atraso:
                await asyncio.sleep(atraso)
            yield texto
        if self._bloquear:
            await asyncio.Event().wait()

    async def interromper(self) -> None:
        self.interrompecoes += 1


class TestDialetosRegistrados:
    def test_dialetos_registra_claude_e_agy(self) -> None:
        assert set(DIALETOS) == {"claude", "agy"}
        assert isinstance(DIALETOS["claude"], DialetoClaude)
        assert isinstance(DIALETOS["agy"], DialetoAgy)

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    def test_linha_usuario_e_uma_linha_ndjson_no_envelope_certo(self, dialeto: str) -> None:
        linha = DIALETOS[dialeto].linha_usuario("pergunta de teste")
        assert "\n" not in linha
        obj = json.loads(linha)
        envelope = "type" if dialeto == "claude" else "event"
        assert obj[envelope] == "user"
        bloco = obj["message"]["content"][0]
        assert bloco == {"type": "text", "text": "pergunta de teste"}


class TestTurnoComFixtures:
    @pytest.mark.parametrize("dialeto,ferramenta_esperada", DIALETOS_TESTE)
    async def test_texto_em_pedacos_vira_deltas(self, dialeto: str, ferramenta_esperada: str) -> None:
        linhas = _linhas_fixture(f"{dialeto}_texto.ndjson") + _linhas_fixture(f"{dialeto}_fim.ndjson")
        canal = CanalFalso(linhas)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        eventos = await _coletar(adaptador, _mensagens(("user", "ola")))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert textos == ["Olá, ", "como posso ajudar?"]
        assert not any(e.tipo == "chamada" for e in eventos)
        assert eventos[-1].tipo == "fim"

    @pytest.mark.parametrize("dialeto,ferramenta_esperada", DIALETOS_TESTE)
    async def test_uso_de_ferramenta_vira_evento_informativo_nao_chamada(
        self, dialeto: str, ferramenta_esperada: str
    ) -> None:
        linhas = _linhas_fixture(f"{dialeto}_ferramenta.ndjson") + _linhas_fixture(f"{dialeto}_fim.ndjson")
        canal = CanalFalso(linhas)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        eventos = await _coletar(adaptador, _mensagens(("user", "use ferramenta")))
        ferramentas = [e for e in eventos if e.tipo == "ferramenta"]
        assert len(ferramentas) == 1
        assert ferramentas[0].dados["nome"] == ferramenta_esperada
        assert not any(e.tipo == "chamada" for e in eventos)
        assert eventos[-1].tipo == "fim"

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_fim_de_turno(self, dialeto: str) -> None:
        linhas = _linhas_fixture(f"{dialeto}_texto.ndjson") + _linhas_fixture(f"{dialeto}_fim.ndjson")
        canal = CanalFalso(linhas)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        eventos = await _coletar(adaptador, _mensagens(("user", "ola")))
        fim = eventos[-1]
        assert fim.tipo == "fim"
        assert fim.dados.get("num_turns") == 1

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_erro_de_login_vira_cli_sem_login(self, dialeto: str) -> None:
        canal = CanalFalso(_linhas_fixture(f"{dialeto}_erro_login.ndjson"))
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        with pytest.raises(ErroProvedor) as excinfo:
            await _coletar(adaptador, _mensagens(("user", "ola")))
        assert excinfo.value.codigo == "cli_sem_login"

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_linha_nao_json_e_ignorada(self, dialeto: str) -> None:
        banner = (
            "Aviso: atualização disponível para claude-cli"
            if dialeto == "claude"
            else "aviso: nova versão do agy disponível"
        )
        linhas = [banner] + _linhas_fixture(f"{dialeto}_texto.ndjson") + _linhas_fixture(f"{dialeto}_fim.ndjson")
        canal = CanalFalso(linhas)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        eventos = await _coletar(adaptador, _mensagens(("user", "ola")))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert textos == ["Olá, ", "como posso ajudar?"]
        assert eventos[-1].tipo == "fim"

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_ferramentas_iniciais_lidas_do_inicio(self, dialeto: str) -> None:
        esperadas = ["Bash", "Read", "Write"] if dialeto == "claude" else ["run_command", "read_url_content", "write_to_file"]
        dialeto_obj = DIALETOS[dialeto]
        linha_init = _linhas_fixture(f"{dialeto}_inicio.ndjson")[0]
        assert dialeto_obj.ferramentas_iniciais(linha_init) == esperadas
        linha_texto = _linhas_fixture(f"{dialeto}_texto.ndjson")[0]
        assert dialeto_obj.ferramentas_iniciais(linha_texto) is None
        assert dialeto_obj.ferramentas_iniciais("nada aqui") is None
        # init não vaza como evento para o cérebro
        assert dialeto_obj.interpretar(linha_init) == []


class TestPrazosInjetados:
    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_sem_evento_util_em_15s_vira_cli_tempo(self, dialeto: str) -> None:
        nao_util = (
            json.dumps({"type": "hook_started", "hook": "SessionStart"})
            if dialeto == "claude"
            else json.dumps({"event": "hook_started", "hook": "SessionStart"})
        )
        banner = "Aviso: atualização disponível" if dialeto == "claude" else "aviso: nova versão"
        canal = CanalFalso([banner, nao_util], bloquear_no_fim=True)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=0.05, prazo_turno=60.0)
        with pytest.raises(ErroProvedor) as excinfo:
            await _coletar(adaptador, _mensagens(("user", "ola")))
        assert excinfo.value.codigo == "cli_tempo"
        assert "evento" in excinfo.value.detalhe

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_turno_acima_de_180s_vira_cli_tempo(self, dialeto: str) -> None:
        init = _linhas_fixture(f"{dialeto}_inicio.ndjson")[0]
        primeiro_delta = _linhas_fixture(f"{dialeto}_texto.ndjson")[0]
        canal = CanalFalso([(init, 0.0), (primeiro_delta, 0.08)], bloquear_no_fim=True)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=30.0, prazo_turno=0.2)
        with pytest.raises(ErroProvedor) as excinfo:
            await _coletar(adaptador, _mensagens(("user", "ola")))
        assert excinfo.value.codigo == "cli_tempo"
        assert "turno" in excinfo.value.detalhe


class TestContratoDoAdaptador:
    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_so_envia_a_ultima_mensagem_do_usuario(self, dialeto: str) -> None:
        canal = CanalFalso(_linhas_fixture(f"{dialeto}_fim.ndjson"))
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        mensagens = _mensagens(
            ("user", "primeira pergunta"),
            ("assistant", "resposta da CLI"),
            ("user", "segunda pergunta"),
        )
        await _coletar(adaptador, mensagens)
        assert canal.enviados == [DIALETOS[dialeto].linha_usuario("segunda pergunta")]

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_cancelamento_chama_interromper(self, dialeto: str) -> None:
        canal = CanalFalso([], bloquear_no_fim=True)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=30.0, prazo_turno=60.0)
        cancelamento = asyncio.Event()

        async def _cancelar_depois() -> None:
            await asyncio.sleep(0.05)
            cancelamento.set()

        tarefa = asyncio.create_task(_cancelar_depois())
        with pytest.raises(asyncio.CancelledError):
            await _coletar(adaptador, _mensagens(("user", "ola")), cancelamento=cancelamento)
        await tarefa
        assert canal.interrompecoes == 1

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_cancelamento_ja_marcado_antes_do_turno(self, dialeto: str) -> None:
        canal = CanalFalso(_linhas_fixture(f"{dialeto}_fim.ndjson"))
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        cancelamento = asyncio.Event()
        cancelamento.set()
        with pytest.raises(asyncio.CancelledError):
            await _coletar(adaptador, _mensagens(("user", "ola")), cancelamento=cancelamento)
        assert canal.interrompecoes == 1

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_erro_sem_segredo_nem_caminho(self, dialeto: str) -> None:
        veneno = (
            "API Error: 401 authentication required "
            "/home/fulano/.vard/chave=segredo123 Bearer sk-fake-456.ghi"
        )
        if dialeto == "claude":
            linha = json.dumps({
                "type": "result", "stop_reason": None, "session_id": "s",
                "result": veneno, "num_turns": 0, "is_error": True, "api_error_status": 401,
            })
        else:
            linha = json.dumps({
                "event": "result", "result": {
                    "conversation_id": "c", "status": "ERROR", "error": veneno,
                    "response": "", "duration_seconds": 0, "num_turns": 0,
                },
            })
        canal = CanalFalso([linha])
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        with pytest.raises(ErroProvedor) as excinfo:
            await _coletar(adaptador, _mensagens(("user", "ola")))
        assert excinfo.value.codigo == "cli_sem_login"
        mensagem = str(excinfo.value)
        for proibido in ("fulano", "segredo123", "sk-fake", "home", "Bearer"):
            assert proibido not in mensagem

    @pytest.mark.parametrize("dialeto", ["claude", "agy"])
    async def test_stream_fechado_sem_result_vira_cli_caiu(self, dialeto: str) -> None:
        canal = CanalFalso(_linhas_fixture(f"{dialeto}_texto.ndjson"), bloquear_no_fim=False)
        adaptador = AdaptadorCli(canal, dialeto, prazo_evento=5.0, prazo_turno=30.0)
        with pytest.raises(ErroProvedor) as excinfo:
            await _coletar(adaptador, _mensagens(("user", "ola")))
        assert excinfo.value.codigo == "cli_caiu"

    async def test_imagem_nao_suportada(self) -> None:
        canal = CanalFalso([])
        adaptador = AdaptadorCli(canal, "claude")
        with pytest.raises(ErroProvedor) as excinfo:
            await _coletar(adaptador, _mensagens(("user", "ola")), imagem="aW1n")
        assert excinfo.value.codigo == "imagem_nao_suportada"

    def test_dialeto_desconhecido_e_recusado(self) -> None:
        with pytest.raises(ValueError):
            AdaptadorCli(CanalFalso([]), "codex")
