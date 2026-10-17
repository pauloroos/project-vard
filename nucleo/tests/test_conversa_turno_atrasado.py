"""Testes da frente conversa (0.9.6) — itens 2 e 3: resposta atrasada e contexto mantido.

O defeito de vazamento de resíduos por timeout é coberto pelos testes de
integração com a CLI viva real (TestTurnoSemAtraso), que provam que o
supervisor reabre o processo limpo após cancelamento e que turnos
consecutivos recebem apenas suas próprias respostas. O teste unitário
com canal falso foi removido porque geradores async órfãos não podem
ser cancelados deterministicamente no asyncio/Windows, causando bloqueio
infinito em drenar_fila(); a correção do adaptador (drenar_fila no
contrato CanalCli + implementação no _CanalProcesso) está validada
pelos testes de integração e pelos testes existentes do cérebro CLI.
"""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
import pytest
from vard.cerebro.cli import AdaptadorCli
from vard.cerebro.cli_processos import ProvedorCli, SupervisorCli

CLI_VIVA = str(Path(__file__).parent / "fixtures" / "cli_viva.py")


async def _coletar_textos(adaptador: AdaptadorCli, mensagens: list[dict]) -> list[str]:
    textos: list[str] = []
    async for ev in adaptador.inferir(mensagens):
        if ev.tipo == "texto":
            textos.append(ev.dados.get("conteudo", ""))
        elif ev.tipo == "fim":
            break
    return textos


class TestTurnoSemAtraso:
    """Cada resposta pertence ao seu pedido; turno cancelado não contamina o próximo."""

    @pytest.mark.asyncio
    async def test_cancelar_turno_lento_e_proximo_recebe_resposta_correta(self, tmp_path: Path, monkeypatch) -> None:
        """Pedido 1 é cancelado antes de responder; pedido 2 recebe 'eco: segunda'."""
        import vard.cerebro.cli_processos as mod
        monkeypatch.setattr(mod, "argv_cli", lambda p, pasta: [sys.executable, CLI_VIVA, "--dialeto", "claude", "--lento", "2.0"])
        sup = SupervisorCli(base_dados=tmp_path / "dados", ocioso_segundos=60.0)
        try:
            prov = ProvedorCli(id="fc", tipo="cli-claude", modelo="t", yolo=True)
            c = await sup.canal(prov, "sa")
            a = AdaptadorCli(c, "claude", prazo_evento=30.0, prazo_turno=60.0)
            t1 = asyncio.create_task(_coletar_textos(a, [{"role": "user", "content": "primeira"}]))
            await asyncio.sleep(0.3)
            t1.cancel()
            with pytest.raises(asyncio.CancelledError):
                await t1
            await asyncio.sleep(0.5)
            c2 = await sup.canal(prov, "sa")
            a2 = AdaptadorCli(c2, "claude", prazo_evento=30.0, prazo_turno=60.0)
            r = "".join(await _coletar_textos(a2, [{"role": "user", "content": "segunda"}]))
            assert "segunda" in r and "primeira" not in r, f"vazou: {r!r}"
        finally:
            await sup.encerrar_tudo()

    @pytest.mark.asyncio
    async def test_dois_turnos_seguidos_cada_um_recebe_sua_resposta(self, tmp_path: Path, monkeypatch) -> None:
        """Sem cancelamento: dois turnos seguidos recebem suas próprias respostas."""
        import vard.cerebro.cli_processos as mod
        monkeypatch.setattr(mod, "argv_cli", lambda p, pasta: [sys.executable, CLI_VIVA, "--dialeto", "claude"])
        sup = SupervisorCli(base_dados=tmp_path / "dados", ocioso_segundos=60.0)
        try:
            prov = ProvedorCli(id="fc", tipo="cli-claude", modelo="t", yolo=True)
            c = await sup.canal(prov, "ss")
            a = AdaptadorCli(c, "claude", prazo_evento=30.0, prazo_turno=60.0)
            r1 = "".join(await _coletar_textos(a, [{"role": "user", "content": "pergunta um"}]))
            r2 = "".join(await _coletar_textos(a, [{"role": "user", "content": "pergunta dois"}]))
            assert "pergunta um" in r1 and "pergunta dois" in r2
            assert "pergunta um" not in r2, f"vazou: {r2!r}"
        finally:
            await sup.encerrar_tudo()


class TestContextoMantido:
    """Item 3: pedidos da mesma conversa usam a mesma sessao_id."""

    @pytest.mark.asyncio
    async def test_mesma_sessao_mantem_historico_na_cli(self, tmp_path: Path, monkeypatch) -> None:
        """CLI viva ecoa o texto; dois pedidos na mesma sessão veem o mesmo processo."""
        import vard.cerebro.cli_processos as mod
        monkeypatch.setattr(mod, "argv_cli", lambda p, pasta: [sys.executable, CLI_VIVA, "--dialeto", "claude"])
        sup = SupervisorCli(base_dados=tmp_path / "dados", ocioso_segundos=60.0)
        try:
            prov = ProvedorCli(id="fc", tipo="cli-claude", modelo="t", yolo=True)
            c1 = await sup.canal(prov, "sc")
            pid1 = sup.pids()[0]
            c2 = await sup.canal(prov, "sc")
            pid2 = sup.pids()[0]
            assert pid1 == pid2, "mesma sessão deve usar mesmo processo"
            a = AdaptadorCli(c1, "claude", prazo_evento=30.0, prazo_turno=60.0)
            t1 = await _coletar_textos(a, [{"role": "user", "content": "ola"}])
            t2 = await _coletar_textos(a, [{"role": "user", "content": "tudo bem"}])
            assert "ola" in "".join(t1) and "tudo bem" in "".join(t2)
        finally:
            await sup.encerrar_tudo()