#!/usr/bin/env python3
"""Prova real do cérebro e dos MCPs com modelo de teste (J2).

Executa duas categorias de prova:
1. Prova direta dos MCPs via stdio (sem modelo): handshake + chamada real.
2. Prova por HTTP/SSE do cérebro completo: modelo real chama ferramenta real.

O comando público está bloqueado até validar todos os caminhos de segurança e
cleanup. A implementação interna é usada apenas com dados fictícios nos testes.

Saída: JSON em /tmp/vard-j2-prova-<timestamp>.json ou caminho via --saida.
Nunca imprime chaves, endpoints privados ou nomes de modelo.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import datetime as dt
import json
import ipaddress
import logging
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

# Garante que o núcleo está no path
NUCLEO_DIR = Path(__file__).resolve().parents[2] / "nucleo"
if str(NUCLEO_DIR) not in sys.path:
    sys.path.insert(0, str(NUCLEO_DIR))


# ---------------------------------------------------------------------------
# Sanitização (importada do módulo canônico no núcleo)
# ---------------------------------------------------------------------------

from vard.sanitizacao import sanitizar, verificar_ambiente


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _porta_livre() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _estado_em_memoria() -> ExitStack:
    """Isola a persistência do cérebro durante a prova, inclusive dados de ferramentas."""
    from vard import instalaveis
    from vard.cerebro import diario, pedidos, sessoes

    pedidos_memoria: dict = {}
    sessoes_memoria: dict = {}
    diario_memoria: dict = {}
    pilha = ExitStack()
    ambiente_original = instalaveis.ambiente_limpo

    def ambiente_sem_chave():
        ambiente = ambiente_original()
        for variavel in ("OMNI_API_KEY", "OMNI_BASE_URL", "OMNI_MODELO"):
            ambiente.pop(variavel, None)
        return ambiente

    try:
        pilha.enter_context(patch.object(instalaveis, "ambiente_limpo", ambiente_sem_chave))
        pilha.enter_context(patch.object(pedidos, "_ler_info", lambda pedido_id: copy.deepcopy(pedidos_memoria.get(pedido_id))))
        pilha.enter_context(patch.object(pedidos, "_gravar_info", lambda info: pedidos_memoria.__setitem__(info.pedido_id, copy.deepcopy(info))))
        pilha.enter_context(patch.object(sessoes, "_ler", lambda sessao_id: copy.deepcopy(sessoes_memoria.get(sessao_id, {"mensagens": [], "trocass": 0}))))
        pilha.enter_context(patch.object(sessoes, "_gravar", lambda sessao_id, dados: sessoes_memoria.__setitem__(sessao_id, copy.deepcopy(dados))))
        pilha.enter_context(patch.object(diario, "_ler_linhas", lambda arq: copy.deepcopy(diario_memoria.get(arq, []))))
        pilha.enter_context(patch.object(diario, "_gravar_linha", lambda arq, linha: diario_memoria.setdefault(arq, []).append(copy.deepcopy(linha))))
    except BaseException:
        pilha.close()
        raise
    return pilha


class _ProcessoGerenciado:
    """Subprocesso com PID rastreado e término garantido."""

    def __init__(self, nome: str, proc: subprocess.Popen) -> None:
        self.nome = nome
        self.proc = proc
        self.pid = proc.pid

    def encerrar(self) -> dict:
        info = {"nome": self.nome, "pid": self.pid}
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                    info["terminado"] = "graceful"
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
                    info["terminado"] = "forced"
            else:
                info["terminado"] = "ja_encerrado"
        except Exception as exc:
            info["terminado"] = f"erro: {exc}"
        return info


class _FerramentaDaProva:
    """Só permite a consulta sem argumentos prevista para esta prova."""

    def __init__(self, gerenciador: Any) -> None:
        self.gerenciador = gerenciador

    async def listar_todas(self) -> list[dict]:
        return [f for f in await self.gerenciador.listar_todas()
                if f.get("identificador") == "configuracoes" and f.get("nome") == "ver_configuracoes"]

    async def chamar(self, identificador: str, nome: str, argumentos: dict) -> str:
        if identificador != "configuracoes" or nome != "ver_configuracoes" or argumentos != {}:
            raise ValueError("ferramenta ou argumentos não permitidos na prova")
        return await self.gerenciador.chamar(identificador, nome, argumentos)

    async def fechar_tudo(self) -> None:
        await self.gerenciador.fechar_tudo()


# ---------------------------------------------------------------------------
# Prova direta dos MCPs (sem modelo)
# ---------------------------------------------------------------------------

async def provar_mcps_diretos(config_dir: Path, dados_dir: Path) -> list[dict]:
    """Handshake + chamada real em cada MCP local que roda neste Linux."""
    from vard.cerebro.ferramentas import GerenciadorFerramentas

    resultados: list[dict] = []
    gm = GerenciadorFerramentas()

    # MCPs e ferramentas a testar
    mcp_ferramentas = {
        "configuracoes": ["ver_configuracoes", "listar_provedores", "listar_vozes"],
        "memoria": ["memoria_buscar"],
        "reuniao": ["reuniao_status"],
        "mesa": ["hora_atual"],
    }
    # oficina e consulta não rodam em Linux (msvcrt); registra como pendência
    mcp_pendentes_windows = ["oficina", "consulta"]

    try:
        for nome_mcp, ferramentas in mcp_ferramentas.items():
            script = NUCLEO_DIR / f"{nome_mcp}_mcp.py"
            if not script.exists():
                resultados.append({
                    "mcp": nome_mcp,
                    "status": "ausente",
                    "detalhe": sanitizar(f"script {script.name} não encontrado"),
                })
                continue

            try:
                await asyncio.wait_for(
                    gm.adicionar_stdio(nome_mcp, sys.executable, [str(script)]),
                    timeout=15,
                )
                pids = gm.pids_mcp()
                mcp_pid = pids.get(nome_mcp)
                if mcp_pid is not None:
                    resultados.append({
                        "mcp": nome_mcp,
                        "status": "pid_registrado",
                        "pid": mcp_pid,
                    })
            except Exception as exc:
                resultados.append({
                    "mcp": nome_mcp,
                    "status": "indisponivel",
                    "detalhe": "falha_no_handshake",
                })
                continue

            for ferr in ferramentas:
                inicio = time.monotonic()
                try:
                    args = {}
                    if ferr == "memoria_buscar":
                        args = {"pergunta": "teste de prova"}
                    resultado = await asyncio.wait_for(
                        gm.chamar(nome_mcp, ferr, args),
                        timeout=30,
                    )
                    duracao = round(time.monotonic() - inicio, 3)
                    resultados.append({
                        "mcp": nome_mcp,
                        "ferramenta": ferr,
                        "status": "executou",
                        "resultado_sanitizado": "[conteúdo omitido]",
                        "duracao_s": duracao,
                    })
                except asyncio.TimeoutError:
                    resultados.append({
                        "mcp": nome_mcp,
                        "ferramenta": ferr,
                        "status": "timeout",
                        "duracao_s": round(time.monotonic() - inicio, 3),
                    })
                except Exception as exc:
                    msg = str(exc)
                    # Classifica ausência declarada vs erro real
                    if any(kw in msg.lower() for kw in (
                        "não está configurad", "não está instalad",
                        "not configured", "not installed", "ausente",
                    )):
                        status = "ausencia_declarada"
                    else:
                        status = "erro"
                    resultados.append({
                        "mcp": nome_mcp,
                        "ferramenta": ferr,
                        "status": status,
                        "detalhe": "falha_na_ferramenta",
                        "duracao_s": round(time.monotonic() - inicio, 3),
                    })

        # Pendências Windows
        for nome_mcp in mcp_pendentes_windows:
            resultados.append({
                "mcp": nome_mcp,
                "status": "pendencia_windows",
                "detalhe": "MCP depende de msvcrt/Windows; não aplicável em Linux",
            })

    finally:
        await gm.fechar_tudo()

    return resultados


# ---------------------------------------------------------------------------
# Prova por HTTP/SSE (cérebro + modelo real + ferramenta real)
# ---------------------------------------------------------------------------

async def provar_cerebro_http(
    config_dir: Path,
    dados_dir: Path,
    porta_nucleo: int,
    token_local: str,
) -> dict:
    """Sobe núcleo real, assina SSE, envia pedido que pede ferramenta, coleta eventos."""
    import httpx

    base_url = f"http://127.0.0.1:{porta_nucleo}"
    resultado: dict[str, Any] = {
        "tipo": "cerebro_http_sse",
        "eventos": [],
        "pedido_estado": None,
        "ferramenta_chamada": None,
        "resposta_sanitizada": None,
        "http_status": None,
        "duracao_s": 0,
        "erro": None,
    }
    inicio = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False, headers={"X-Vard-Prova": token_local}) as client:
            # Aguarda núcleo ficar pronto
            for tentativa in range(30):
                try:
                    r = await client.get(f"{base_url}/saude")
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
            else:
                resultado["erro"] = "nucleo_nao_respondeu_em_30s"
                resultado["duracao_s"] = round(time.monotonic() - inicio, 3)
                return resultado

            # Assina SSE em background
            eventos_coletados: list[dict] = []
            sse_pronto = asyncio.Event()

            async def ouvir_sse():
                try:
                    async with client.stream("GET", f"{base_url}/events") as resp:
                        sse_pronto.set()
                        buffer = ""
                        async for chunk in resp.aiter_text():
                            buffer += chunk
                            while "\n\n" in buffer:
                                bloco, buffer = buffer.split("\n\n", 1)
                                for linha in bloco.split("\n"):
                                    if linha.startswith("data: "):
                                        try:
                                            ev = json.loads(linha[6:])
                                            eventos_coletados.append(ev)
                                        except json.JSONDecodeError:
                                            pass
                except Exception:
                    pass

            tarefa_sse = asyncio.create_task(ouvir_sse())
            await asyncio.wait_for(sse_pronto.wait(), timeout=10)
            await asyncio.sleep(0.5)  # tempo para estabilizar

            # Envia pedido que pede explicitamente uma ferramenta
            pedido_id = f"j2-prova-{int(time.time())}"
            payload = {
                "pedido_id": pedido_id,
                "sessao_id": "sess-j2-prova",
                "origem": "painel",
                "texto": "Use a ferramenta ver_configuracoes para me mostrar as configurações atuais do sistema.",
            }
            try:
                r = await client.post(f"{base_url}/pedidos", json=payload)
                resultado["http_status"] = r.status_code
            except Exception as exc:
                resultado["erro"] = "falha_ao_enviar_pedido"
                resultado["duracao_s"] = round(time.monotonic() - inicio, 3)
                tarefa_sse.cancel()
                return resultado

            # Espera conclusão (até 60s)
            for _ in range(60):
                await asyncio.sleep(1)
                try:
                    r = await client.get(f"{base_url}/pedidos/{pedido_id}")
                    if r.status_code == 200:
                        dados = r.json()
                        estado = dados.get("estado", "")
                        if estado in ("concluido", "falhou", "cancelado"):
                            resultado["pedido_estado"] = estado
                            resultado["resposta_sanitizada"] = "[conteúdo omitido]" if dados.get("resposta") else None
                            break
                except Exception:
                    pass

            # Coleta eventos relevantes
            for ev in eventos_coletados:
                if ev.get("pedido_id") != pedido_id:
                    continue
                tipo_ev = ev.get("evento_tipo", "")
                if tipo_ev not in ("estado", "ferramenta", "texto", "fim", "erro"):
                    continue
                if tipo_ev == "ferramenta":
                    resultado["ferramenta_chamada"] = {
                        "nome": "ver_configuracoes" if (ev.get("dados", {}).get("nome") or ev.get("dados", {}).get("name")) == "ver_configuracoes" else "outra",
                    }
                resultado["eventos"].append({
                    "tipo": tipo_ev,
                })

            tarefa_sse.cancel()
            try:
                await asyncio.wait_for(tarefa_sse, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    except Exception as exc:
        resultado["erro"] = "falha_http_sse"

    resultado["duracao_s"] = round(time.monotonic() - inicio, 3)
    return resultado


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _executar_prova(saida: Path | None = None) -> dict:
    """Implementação interna; reservada a testes com credenciais fictícias."""
    faltantes = verificar_ambiente()
    if faltantes:
        msg = f"Variáveis de ambiente obrigatórias ausentes: {', '.join(faltantes)}\n"
        msg += "Carregue as variáveis do provedor (OMNI_BASE_URL, OMNI_API_KEY, OMNI_MODELO) antes de rodar.\n"
        print(msg, file=sys.stderr)
        sys.exit(1)

    chave = os.environ["OMNI_API_KEY"]
    base = os.environ["OMNI_BASE_URL"]
    modelo = os.environ["OMNI_MODELO"]
    try:
        url = urlsplit(base)
        url_insegura = bool(url.username or url.password or url.query or url.fragment or not url.hostname)
        if url.scheme == "http":
            try:
                url_insegura |= not ipaddress.ip_address(url.hostname).is_loopback
            except ValueError:
                url_insegura = True
        elif url.scheme != "https":
            url_insegura = True
    except ValueError:
        url_insegura = True
    if url_insegura or chave in base or chave in modelo:
        print("Configuração de prova contém possível credencial; execução recusada.", file=sys.stderr)
        sys.exit(1)

    relatorio: dict[str, Any] = {
        "job": "J2",
        "data": dt.datetime.now(dt.timezone.utc).isoformat(),
        "provas_mcps_diretos": [],
        "prova_cerebro_http": {},
        "processos": [],
    }

    processos: list[_ProcessoGerenciado] = []

    with tempfile.TemporaryDirectory(prefix="vard-j2-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        dados_dir = tmp_path / "dados"
        dados_dir.mkdir()

        # Exporta VARD_CONFIG, VARD_DADOS e VARD_HUD_CONFIG_DIR para isolar da config do usuário
        os.environ["VARD_CONFIG"] = str(config_dir)
        os.environ["VARD_DADOS"] = str(dados_dir)
        hud_config_dir = tmp_path / "hud"
        hud_config_dir.mkdir()
        os.environ["VARD_HUD_CONFIG_DIR"] = str(hud_config_dir)

        # Injeta credencial em memória — NENHUM arquivo segredos.toml é criado.
        omni_key = os.environ["OMNI_API_KEY"]
        from vard import segredos as modulo_segredos
        mcp_pids_antes: dict[str, int] = {}
        estado_memoria = ExitStack()
        filhos_criados: list[asyncio.subprocess.Process] = []
        criar_subprocesso = asyncio.create_subprocess_exec

        async def criar_rastreado(*args, **kwargs):
            filho = await criar_subprocesso(*args, **kwargs)
            filhos_criados.append(filho)
            return filho

        nivel_log = logging.root.manager.disable
        servidor_uvicorn = None
        tarefa_servidor = None
        try:
            estado_memoria.enter_context(_estado_em_memoria())
            estado_memoria.enter_context(patch.object(asyncio, "create_subprocess_exec", criar_rastreado))
            logging.disable(logging.CRITICAL)
            modulo_segredos.definir_em_memoria({"lmstudio": {"chave": omni_key}})
            # --- Prova 1: MCPs diretos ---
            print("→ Provando MCPs diretamente (sem modelo)...")
            try:
                relatorio["provas_mcps_diretos"] = await provar_mcps_diretos(config_dir, dados_dir)
            except Exception as exc:
                relatorio["provas_mcps_diretos"] = [{"erro": "falha_prova_mcps"}]

            # --- Prova 2: Cérebro por HTTP/SSE (in-process, sem subprocesso) ---
            print("→ Subindo núcleo para prova HTTP/SSE (in-process)...")
            porta_nucleo = _porta_livre()

            import uvicorn
            import server as modulo_server
            estado_memoria.enter_context(patch.object(modulo_server, "_ler_provedor_ativo", lambda: {
                "tipo": "local", "url_base": base, "modelo": modelo, "credencial_ref": "",
            }))
            from vard.cerebro import provedores
            stream_original = provedores._stream_http

            def stream_sem_proxy(*args, **kwargs):
                kwargs["trust_env"] = False
                return stream_original(*args, **kwargs)

            estado_memoria.enter_context(patch.object(provedores, "_stream_http", stream_sem_proxy))
            token_local = secrets.token_urlsafe(32)

            async def app_nucleo(scope, receive, send):
                if scope["type"] in ("http", "websocket"):
                    headers = [v for k, v in scope.get("headers", []) if k.lower() == b"x-vard-prova"]
                    if len(headers) != 1 or not secrets.compare_digest(headers[0], token_local.encode()):
                        if scope["type"] == "http":
                            await send({"type": "http.response.start", "status": 403, "headers": []})
                            await send({"type": "http.response.body", "body": b""})
                        else:
                            await send({"type": "websocket.close", "code": 1008})
                        return
                await modulo_server.app(scope, receive, send)

            config_uvicorn = uvicorn.Config(
                app_nucleo, host="127.0.0.1", port=porta_nucleo, log_level="warning"
            )
            servidor_uvicorn = uvicorn.Server(config_uvicorn)
            tarefa_servidor: asyncio.Task | None = None
            try:
                tarefa_servidor = asyncio.create_task(servidor_uvicorn.serve())
            except Exception as exc:
                relatorio["prova_cerebro_http"] = {"erro": "falha_ao_iniciar_servidor"}
                servidor_uvicorn = None  # type: ignore[assignment]
            # Aguarda o servidor iniciar
            if servidor_uvicorn is not None:
                for _ in range(30):
                    if servidor_uvicorn.started or tarefa_servidor.done():
                        break
                    await asyncio.sleep(0.5)

                if servidor_uvicorn.started and modulo_server._ferramentas_cerebro is not None:
                    modulo_server._ferramentas_cerebro = _FerramentaDaProva(modulo_server._ferramentas_cerebro)
                    print(f"→ Provando cérebro via HTTP/SSE (porta {porta_nucleo})...")
                    try:
                        relatorio["prova_cerebro_http"] = await provar_cerebro_http(
                            config_dir, dados_dir, porta_nucleo, token_local
                        )
                    except Exception as exc:
                        relatorio["prova_cerebro_http"] = {"erro": "falha_prova_cerebro"}
                else:
                    relatorio["prova_cerebro_http"] = {"erro": "servidor_nao_iniciado"}
        finally:
            # Encerra servidor in-process e limpa credencial em memória
            print("→ Encerrando servidor e limpando credencial...")
            if servidor_uvicorn is not None and tarefa_servidor is not None:
                try:
                    servidor_uvicorn.should_exit = True
                    await asyncio.wait_for(tarefa_servidor, timeout=5)
                    relatorio["processos"].append({
                        "nome": "nucleo_in_process",
                        "pid": os.getpid(),
                        "terminado": "graceful",
                    })
                except Exception as exc:
                    relatorio["processos"].append({
                        "nome": "nucleo_in_process",
                        "pid": os.getpid(),
                        "terminado": "erro_encerramento",
                    })
            elif not relatorio["prova_cerebro_http"]:
                relatorio["prova_cerebro_http"] = {"erro": "servidor_nao_iniciado"}
            for filho in filhos_criados:
                try:
                    if filho.returncode is None:
                        filho.terminate()
                        try:
                            await asyncio.wait_for(filho.wait(), timeout=5)
                        except asyncio.TimeoutError:
                            filho.kill()
                            await asyncio.wait_for(filho.wait(), timeout=3)
                    relatorio["processos"].append({"nome": "subprocesso_prova", "pid": filho.pid,
                                                  "terminado": filho.returncode is not None})
                except (ProcessLookupError, asyncio.TimeoutError, OSError):
                    relatorio["processos"].append({"nome": "subprocesso_prova", "pid": filho.pid,
                                                  "terminado": False})
            modulo_segredos.definir_em_memoria(None)
            estado_memoria.close()
            logging.disable(nivel_log)

            # Encerra processos restantes (MCPs stdio)
            for p in processos:
                info = p.encerrar()
                relatorio["processos"].append(info)
                print(f"  {info['nome']} (PID {info['pid']}): {info['terminado']}")

            # Confirma que nenhum MCP stdio sobreviveu (verificação por PID)
            import psutil
            mcp_encerrados: list[dict] = []
            for item in relatorio.get("provas_mcps_diretos", []):
                if item.get("status") == "pid_registrado" and "pid" in item:
                    pid = item["pid"]
                    vivo = psutil.pid_exists(pid)
                    mcp_encerrados.append({
                        "mcp": item["mcp"],
                        "pid": pid,
                        "terminado": not vivo,
                    })
            if mcp_encerrados:
                relatorio["mcp_terminados"] = mcp_encerrados

    # Sanitiza também campos que vieram de nomes de ferramentas e erros de encerramento.
    def limpar_relatorio(valor: Any) -> Any:
        if isinstance(valor, str):
            return sanitizar(valor).replace(chave, "***")
        if isinstance(valor, list):
            return [limpar_relatorio(item) for item in valor]
        if isinstance(valor, dict):
            return {limpar_relatorio(k): limpar_relatorio(v) for k, v in valor.items()}
        return valor

    relatorio = limpar_relatorio(relatorio)
    # Escreve relatório
    destino = saida or Path(tempfile.gettempdir()) / f"vard-j2-prova-{int(time.time())}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"→ Relatório escrito em: {destino}")

    return relatorio


async def main(saida: Path | None = None) -> dict:
    print("Prova bloqueada: proteção de credenciais e limpeza de subprocessos ainda não foram comprovadas em todos os caminhos.", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prova real de ferramentas J2")
    parser.add_argument("--saida", type=Path, help="Caminho do JSON de saída")
    args = parser.parse_args()
    asyncio.run(main(args.saida))
