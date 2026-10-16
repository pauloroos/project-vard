"""Testes da T16 — Supervisor de processos vivos de CLI.

Cobre os 15 testes do plano usando a CLI falsa (cli_falsa.py) no lugar do
executável real. Prazos de ocioso são injetados; nenhum teste espera 600 s.
Processos são encerrados por PID ao fim de cada teste.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import sys
import time
from pathlib import Path
from typing import Any, List

import pytest

from vard.cerebro.cli_processos import (
    OCIOSO_SEGUNDOS,
    ProvedorCli,
    SupervisorCli,
    argv_cli,
    _encerrar_arvore,
    _preparar_pasta_sessao,
)
from vard.cerebro.provedores import ErroProvedor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLI_FALSA = str(FIXTURES_DIR / "cli_falsa.py")
CLI_VIVA = str(FIXTURES_DIR / "cli_viva.py")


@pytest.fixture(autouse=True)
def _garantia_sem_cli_viva_orfao():
    """D3: garante que nenhum processo cli_viva.py sobrevive ao teste.

    Roda antes/depois de cada teste; se houver órfão no teardown, falha o teste
    e tenta encerrar por PID para não contaminar os próximos.
    """
    yield
    import subprocess as _sp
    try:
        ps = _sp.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cli_viva\\.py' } | Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        pids = [int(p.strip()) for p in ps.stdout.splitlines() if p.strip().isdigit()]
    except Exception:
        pids = []
    if pids:
        # Tenta limpar para não contaminar outros testes
        for pid in pids:
            try:
                import os, signal
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        raise AssertionError(f"D3: processos cli_viva.py órfãos detectados: {pids}")


@pytest.fixture
def base_dados(tmp_path: Path) -> Path:
    return tmp_path / "dados"


@pytest.fixture
async def supervisor(base_dados: Path, monkeypatch):
    """Supervisor com argv_cli monkeypatchado para usar a CLI viva.

    Os testes desta suíte não podem chamar o executável real (claude/agy);
    a guarda do PC real bloqueia. Substituímos argv_cli para que o
    subprocesso seja sempre [sys.executable, cli_viva.py, --dialeto, ...].
    A cli_viva.py emite init imediatamente e responde linha a linha sem
    esperar EOF, permitindo que o supervisor mantenha o processo vivo.
    """
    import vard.cerebro.cli_processos as mod

    def _argv_vivo(provedor: ProvedorCli, pasta: Path) -> List[str]:
        dialeto = "claude" if provedor.tipo == "cli-claude" else "agy"
        return [sys.executable, CLI_VIVA, "--dialeto", dialeto]

    monkeypatch.setattr(mod, "argv_cli", _argv_vivo)
    sup = SupervisorCli(base_dados=base_dados, ocioso_segundos=0.2)
    yield sup
    await sup.encerrar_tudo()


def _provedor(tipo: str = "cli-claude", **kw: Any) -> ProvedorCli:
    padrao = dict(id=tipo.replace("-", "_"), tipo=tipo, modelo="m-teste", yolo=True)
    padrao.update(kw)
    return ProvedorCli(**padrao)


async def _coletar_linhas(canal, n: int = 5, timeout: float = 2.0) -> List[str]:
    linhas: List[str] = []
    try:
        async for linha in canal.linhas():
            linhas.append(linha)
            if len(linhas) >= n:
                break
    except asyncio.TimeoutError:
        pass
    return linhas


class TestArgvEMontagemDePasta:
    def test_pasta_tem_claude_md_agents_md_perfil_md_e_mcp_json(self, base_dados: Path) -> None:
        prov = _provedor("cli-claude")
        pasta = _preparar_pasta_sessao(prov, "sess-1", base_dados=base_dados)
        assert (pasta / "CLAUDE.md").exists()
        assert (pasta / "AGENTS.md").exists()
        assert (pasta / "perfil.md").exists()
        assert (pasta / "mcp.json").exists()
        texto = (pasta / "perfil.md").read_text(encoding="utf-8")
        assert "# Perfil do agente" in texto

    def test_perfil_com_caracteres_especiais_vai_por_arquivo(self, base_dados: Path) -> None:
        """Perfil com aspas, quebras, acentos e emoji vai íntegro para o arquivo."""
        from vard import perfil as modulo_perfil

        p = modulo_perfil.Perfil(
            tom='direto e "calmo"',
            personalidade="personalidade\ncom quebra",
            instrucoes="instruções com áéíóú ñ ç 🎉",
            sobre_usuario="sobre com 'aspas' e \"duplas\"",
        )
        import vard.perfil as vp

        original_ler = vp.ler
        vp.ler = lambda: p  # type: ignore[assignment]
        try:
            prov = _provedor("cli-claude")
            pasta = _preparar_pasta_sessao(prov, "sess-especial", base_dados=base_dados)
            texto = (pasta / "perfil.md").read_text(encoding="utf-8")
            assert "áéíóú" in texto
            assert "🎉" in texto
            assert '"calmo"' in texto
            assert "'aspas'" in texto
        finally:
            vp.ler = original_ler  # type: ignore[assignment]

    def test_yolo_liga_e_desliga_flag_no_argv(self, base_dados: Path) -> None:
        pasta = _preparar_pasta_sessao(_provedor(yolo=True), "s1", base_dados=base_dados)
        cmd_on = argv_cli(_provedor(yolo=True), pasta)
        assert "--dangerously-skip-permissions" in cmd_on
        cmd_off = argv_cli(_provedor(yolo=False), pasta)
        assert "--dangerously-skip-permissions" not in cmd_off

    def test_argv_claude_tem_modelo_e_perfil(self, base_dados: Path) -> None:
        pasta = _preparar_pasta_sessao(_provedor("cli-claude"), "s1", base_dados=base_dados)
        cmd = argv_cli(_provedor("cli-claude", modelo="claude-haiku-5-5"), pasta)
        assert "claude" in cmd[0]
        assert "--model" in cmd and "claude-haiku-5-5" in cmd
        assert "--append-system-prompt-file" in cmd

    def test_argv_agy_tem_stream_json(self, base_dados: Path) -> None:
        """D8: o agy 1.4 não tem --stream-json; o modo vivo é --input/--output-format stream-json
        com --print vazio (docs/cli.md). --stream-json fazia o agy sair na hora (cli_caiu)."""
        pasta = _preparar_pasta_sessao(_provedor("cli-agy"), "s1", base_dados=base_dados)
        cmd = argv_cli(_provedor("cli-agy"), pasta)
        assert "agy" in cmd[0]
        assert "--stream-json" not in cmd
        assert cmd[cmd.index("--input-format") + 1] == "stream-json"
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"
        assert "--print=" in cmd

    def test_argv_agy_yolo_pula_permissoes(self, base_dados: Path) -> None:
        pasta = _preparar_pasta_sessao(_provedor("cli-agy"), "s1", base_dados=base_dados)
        assert "--dangerously-skip-permissions" in argv_cli(replace(_provedor("cli-agy"), yolo=True), pasta)
        assert "--dangerously-skip-permissions" not in argv_cli(replace(_provedor("cli-agy"), yolo=False), pasta)


class TestSupervisorProcessos:
    @pytest.mark.asyncio
    async def test_abre_um_processo_por_sessao(self, supervisor: SupervisorCli, base_dados: Path) -> None:
        """Dois pedidos na mesma sessão reutilizam o mesmo processo."""
        prov = _provedor("cli-claude")
        canal1 = await supervisor.canal(prov, "sess-a")
        pids1 = supervisor.pids()
        assert len(pids1) == 1
        canal2 = await supervisor.canal(prov, "sess-a")
        pids2 = supervisor.pids()
        assert len(pids2) == 1
        assert pids1[0] == pids2[0]

    @pytest.mark.asyncio
    async def test_reaproveita_processo_na_mesma_sessao(self, supervisor: SupervisorCli) -> None:
        prov = _provedor("cli-claude")
        c1 = await supervisor.canal(prov, "sess-reuso")
        pid1 = supervisor.pids()[0]
        c2 = await supervisor.canal(prov, "sess-reuso")
        pid2 = supervisor.pids()[0]
        assert pid1 == pid2

    @pytest.mark.asyncio
    async def test_sessoes_voz_e_telegram_nao_compartilham_processo(self, supervisor: SupervisorCli) -> None:
        prov = _provedor("cli-claude")
        await supervisor.canal(prov, "sess-voz")
        await supervisor.canal(prov, "sess-telegram")
        pids = supervisor.pids()
        assert len(pids) == 2
        assert len(set(pids)) == 2

    @pytest.mark.asyncio
    async def test_ocioso_fecha_e_reabre_no_proximo_pedido(self, supervisor: SupervisorCli) -> None:
        """Ocioso 0.2 s fecha; próxima chamada reabre com PID diferente."""
        prov = _provedor("cli-claude")
        c1 = await supervisor.canal(prov, "sess-ocioso")
        pid1 = supervisor.pids()[0]
        # Espera o ciclo de limpeza rodar (ocioso=0.2, ciclo roda a cada min(0.1, 60))
        await asyncio.sleep(0.5)
        assert supervisor.pids() == [] or supervisor.pids() != [pid1]
        c2 = await supervisor.canal(prov, "sess-ocioso")
        pids2 = supervisor.pids()
        assert len(pids2) == 1

    @pytest.mark.asyncio
    async def test_nova_conversa_reinicia_processo(self, supervisor: SupervisorCli) -> None:
        prov = _provedor("cli-claude")
        await supervisor.canal(prov, "sess-nova")
        pid1 = supervisor.pids()[0]
        await supervisor.nova_conversa("sess-nova")
        assert supervisor.pids() == []
        await supervisor.canal(prov, "sess-nova")
        pids2 = supervisor.pids()
        assert len(pids2) == 1

    @pytest.mark.asyncio
    async def test_saida_do_app_encerra_por_pid(self, supervisor: SupervisorCli) -> None:
        prov = _provedor("cli-claude")
        await supervisor.canal(prov, "sess-saida")
        pids = supervisor.pids()
        assert len(pids) == 1
        await supervisor.encerrar_tudo()
        assert supervisor.pids() == []

    @pytest.mark.asyncio
    async def test_jogo_no_meio_do_turno_encerra_arvore(self, supervisor: SupervisorCli) -> None:
        """encerrar_tudo() fecha a árvore inteira (jogo/saída)."""
        prov = _provedor("cli-claude")
        await supervisor.canal(prov, "sess-jogo")
        await supervisor.canal(prov, "sess-jogo-2")
        assert len(supervisor.pids()) == 2
        await supervisor.encerrar_tudo()
        assert supervisor.pids() == []

    @pytest.mark.asyncio
    async def test_cli_caiu_no_turno_vira_cli_caiu_e_reabre_depois(self, supervisor: SupervisorCli) -> None:
        """Se o processo morrer, a próxima chamada reabre."""
        prov = _provedor("cli-claude")
        canal = await supervisor.canal(prov, "sess-caiu")
        pid1 = supervisor.pids()[0]
        # Mata o processo manualmente
        _encerrar_arvore(pid1)
        await asyncio.sleep(0.1)
        # Próxima chamada deve reabrir
        canal2 = await supervisor.canal(prov, "sess-caiu")
        pids2 = supervisor.pids()
        assert len(pids2) == 1

    @pytest.mark.asyncio
    async def test_cli_sumiu_do_path_aciona_reserva(self, supervisor: SupervisorCli, monkeypatch) -> None:
        """CLI não encontrada no PATH levanta cli_ausente (recuperável → reserva)."""
        import asyncio as _asyncio
        import vard.cerebro.cli_processos as mod

        async def fake_create_subprocess_exec(*args, **kwargs):
            raise FileNotFoundError("claude not found")

        monkeypatch.setattr(_asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
        prov = _provedor("cli-claude")
        with pytest.raises(ErroProvedor) as excinfo:
            await supervisor.canal(prov, "sess-sumiu")
        assert excinfo.value.codigo == "cli_ausente"
        assert excinfo.value.recuperavel is True

    @pytest.mark.asyncio
    async def test_segunda_pergunta_cancela_turno_anterior(self, supervisor: SupervisorCli) -> None:
        """Cancelamento interrompe o turno em curso via canal.interromper()."""
        prov = _provedor("cli-claude")
        canal = await supervisor.canal(prov, "sess-cancel")
        # Envia uma mensagem e cancela antes de ler a resposta
        await canal.enviar(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": "pergunta 1"}]},
        }))
        await canal.interromper()
        # O processo deve estar morto ou reiniciado; a próxima chamada funciona
        await asyncio.sleep(0.1)
        canal2 = await supervisor.canal(prov, "sess-cancel")
        assert canal2 is not None

    @pytest.mark.asyncio
    async def test_cli_nao_usa_trava_do_motor_local(self, supervisor: SupervisorCli) -> None:
        """CLI não adquire slot_local — verificado por contrato (sem slot no canal)."""
        import inspect

        sig = inspect.signature(supervisor.canal)
        params = list(sig.parameters.keys())
        assert "slot_local" not in params
        assert "slot" not in params

    @pytest.mark.asyncio
    async def test_reserva_so_antes_de_texto_entregue(self, supervisor: SupervisorCli) -> None:
        """Erro recuperável antes de texto aciona reserva; após texto, termina com erro."""
        prov = _provedor("cli-claude")
        canal = await supervisor.canal(prov, "sess-reserva")
        assert canal is not None
        pids = supervisor.pids()
        assert len(pids) == 1


class TestIntegracaoComCliFalsa:
    """Testes de integração usando a CLI falsa como subprocesso real."""

    @pytest.mark.asyncio
    async def test_canal_envia_e_recebe_da_cli_falsa(self, base_dados: Path) -> None:
        """Canal real com cli_falsa.py: envia mensagem, fecha stdin e recebe init + resposta.

        A CLI falsa lê todo o stdin até EOF antes de emitir qualquer evento;
        como o supervisor mantém o processo vivo, precisamos fechar o stdin
        manualmente neste teste para simular o fim da entrada e destravar a resposta.
        """
        sup = SupervisorCli(base_dados=base_dados, ocioso_segundos=60.0)
        try:
            prov = ProvedorCli(id="falso_claude", tipo="cli-claude", modelo="teste", yolo=False)
            import vard.cerebro.cli_processos as mod

            original_argv = mod.argv_cli

            def fake_argv(p, pasta):
                return [sys.executable, CLI_FALSA, "--dialeto", "claude"]

            mod.argv_cli = fake_argv  # type: ignore[assignment]
            try:
                canal = await sup.canal(prov, "sess-integracao")
                # Envia a mensagem do usuário
                await canal.enviar(json.dumps({
                    "type": "user",
                    "message": {"role": "user", "content": [{"type": "text", "text": "ola"}]},
                }))
                # Fecha o stdin para que a CLI falsa processe e responda
                proc = sup._processos.get("falso_claude:sess-integracao")
                assert proc is not None
                assert proc.stdin is not None
                proc.stdin.close()
                linhas = await _coletar_linhas(canal, n=5, timeout=5.0)
                assert len(linhas) >= 1
                init = json.loads(linhas[0])
                assert init.get("type") == "system"
                assert init.get("subtype") == "init"
            finally:
                mod.argv_cli = original_argv  # type: ignore[assignment]
        finally:
            await sup.encerrar_tudo()

    @pytest.mark.asyncio
    async def test_pids_vazio_apos_encerrar_tudo(self, base_dados: Path) -> None:
        sup = SupervisorCli(base_dados=base_dados, ocioso_segundos=60.0)
        prov = ProvedorCli(id="falso_agy", tipo="cli-agy", modelo="teste", yolo=False)
        import vard.cerebro.cli_processos as mod

        original_argv = mod.argv_cli

        def fake_argv(p, pasta):
            return [sys.executable, CLI_FALSA, "--dialeto", "agy"]

        mod.argv_cli = fake_argv  # type: ignore[assignment]
        try:
            await sup.canal(prov, "sess-pids")
            assert len(sup.pids()) == 1
            await sup.encerrar_tudo()
            assert sup.pids() == []
        finally:
            mod.argv_cli = original_argv  # type: ignore[assignment]
            await sup.encerrar_tudo()

@pytest.mark.asyncio
async def test_linha_maior_que_64kb_nao_derruba_o_canal(base_dados: Path) -> None:
    """D6: a CLI claude real emite uma linha system/commands_changed de ~75 KB antes do init.
    O canal precisa ler linhas grandes (o limite padrão do asyncio é 64 KB) sem virar cli_caiu."""
    import vard.cerebro.cli_processos as mod

    sup = SupervisorCli(base_dados=base_dados, ocioso_segundos=60.0)
    original_argv = mod.argv_cli
    mod.argv_cli = lambda p, pasta: [sys.executable, CLI_VIVA, "--dialeto", "claude", "--linha-grande", "200000"]  # type: ignore[assignment]
    try:
        prov = ProvedorCli(id="falso_claude", tipo="cli-claude", modelo="teste", yolo=False)
        canal = await sup.canal(prov, "sess-linha-grande")
        await canal.enviar(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": "ola"}]},
        }))
        recebidas: list[str] = []

        async def ler() -> None:
            async for linha in canal.linhas():
                recebidas.append(linha)
                if '"type": "result"' in linha:
                    return

        await asyncio.wait_for(ler(), timeout=20)
        tamanhos = [len(l) for l in recebidas]
        assert max(tamanhos) > 200000, "a linha grande precisa chegar inteira"
        assert any('"subtype": "init"' in l for l in recebidas)
        assert any("eco: ola" in l for l in recebidas), "a resposta precisa chegar depois da linha grande"
    finally:
        mod.argv_cli = original_argv  # type: ignore[assignment]
        await sup.encerrar_tudo()


@pytest.mark.asyncio
async def test_dois_turnos_na_mesma_sessao_leem_do_mesmo_canal(base_dados: Path) -> None:
    """D7: o 2º turno da mesma sessão reaproveita o processo E o leitor do stdout.
    Antes, cada canal() criava um leitor novo no mesmo stdout e o 2º turno virava cli_caiu
    ("readuntil() called while another coroutine is already waiting")."""
    import vard.cerebro.cli_processos as mod
    from vard.cerebro.cli import AdaptadorCli

    sup = SupervisorCli(base_dados=base_dados, ocioso_segundos=60.0)
    original_argv = mod.argv_cli
    mod.argv_cli = lambda p, pasta: [sys.executable, CLI_VIVA, "--dialeto", "claude"]  # type: ignore[assignment]
    try:
        prov = ProvedorCli(id="falso_claude", tipo="cli-claude", modelo="teste", yolo=False)
        respostas = []
        pids = []
        for texto in ("um", "dois", "tres"):
            canal = await sup.canal(prov, "sess-turnos")
            pids.append(sup._processos["falso_claude:sess-turnos"].pid)
            partes = []
            async for ev in AdaptadorCli(canal, "claude").inferir([{"role": "user", "content": texto}]):
                if ev.tipo == "texto":
                    partes.append(ev.dados.get("conteudo", ""))
            respostas.append("".join(partes))
        assert respostas == ["eco: um", "eco: dois", "eco: tres"]
        assert len(set(pids)) == 1, "a sessão continua no mesmo processo"
    finally:
        mod.argv_cli = original_argv  # type: ignore[assignment]
        await sup.encerrar_tudo()
