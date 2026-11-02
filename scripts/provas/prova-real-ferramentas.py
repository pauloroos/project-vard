#!/usr/bin/env python3
"""Prova real do cérebro e dos MCPs com modelo de teste (J2).

Executa duas categorias de prova:
1. Prova direta dos MCPs via stdio (sem modelo): handshake + chamada real.
2. Prova por HTTP/SSE do cérebro completo: modelo real chama ferramenta real.

Uso:
    Carregue as variáveis de ambiente do provedor (OMNI_BASE_URL, OMNI_API_KEY, OMNI_MODELO)
    e execute: uv run --project nucleo --python 3.13 python scripts/provas/prova-real-ferramentas.py

Saída: JSON em /tmp/vard-j2-prova-<timestamp>.json ou caminho via --saida.
Nunca imprime chaves, endpoints privados ou nomes de modelo.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

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
            except Exception as exc:
                resultados.append({
                    "mcp": nome_mcp,
                    "status": "indisponivel",
                    "detalhe": sanitizar(str(exc)[:300]),
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
                        "resultado_sanitizado": sanitizar(resultado[:500]),
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
                        "detalhe": sanitizar(msg[:300]),
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
        async with httpx.AsyncClient(timeout=90) as client:
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
                resultado["erro"] = sanitizar(f"falha_ao_enviar_pedido: {exc}")
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
                            resultado["resposta_sanitizada"] = sanitizar(
                                (dados.get("resposta") or "")[:500]
                            )
                            break
                except Exception:
                    pass

            # Coleta eventos relevantes
            for ev in eventos_coletados:
                if ev.get("pedido_id") != pedido_id:
                    continue
                tipo_ev = ev.get("evento_tipo", "")
                if tipo_ev == "ferramenta":
                    resultado["ferramenta_chamada"] = {
                        "nome": ev.get("dados", {}).get("nome") or ev.get("dados", {}).get("name", ""),
                        "argumentos_sanitizados": sanitizar(
                            str(ev.get("dados", {}).get("argumentos", ""))[:200]
                        ),
                    }
                resultado["eventos"].append({
                    "tipo": tipo_ev,
                    "dados_sanitizados": sanitizar(str(ev.get("dados", {}))[:300]),
                })

            tarefa_sse.cancel()
            try:
                await asyncio.wait_for(tarefa_sse, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    except Exception as exc:
        resultado["erro"] = sanitizar(str(exc)[:300])

    resultado["duracao_s"] = round(time.monotonic() - inicio, 3)
    return resultado


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(saida: Path | None = None) -> dict:
    faltantes = verificar_ambiente()
    if faltantes:
        msg = f"Variáveis de ambiente obrigatórias ausentes: {', '.join(faltantes)}\n"
        msg += "Carregue as variáveis do provedor (OMNI_BASE_URL, OMNI_API_KEY, OMNI_MODELO) antes de rodar.\n"
        print(msg, file=sys.stderr)
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

        # Cria paineis.json apontando para provedor do ambiente
        # Usa tipo "local" para mapear para AdaptadorOpenAICompat e aceitar chave de [lmstudio]
        # Inclui as quatro chaves de agente exigidas por ajustes.validar_documento
        omni_base = os.environ["OMNI_BASE_URL"]
        omni_modelo = os.environ["OMNI_MODELO"]
        paineis = {
            "versao": 1,
            "provedores": [{
                "id": "omni-prova",
                "nome": "Omni Prova",
                "tipo": "local",
                "url_base": omni_base,
                "modelo": omni_modelo,
                "credencial_ref": "",
            }],
            "ativo": "omni-prova",
            "reserva": None,
            "agentes": {
                "claude": {"padrao": "", "modelos": []},
                "codex": {"padrao": "", "modelos": []},
                "opencode": {"padrao": "", "modelos": []},
                "agy": {"padrao": "", "modelos": []},
            },
            "mcps": [],
        }
        (config_dir / "paineis.json").write_text(
            json.dumps(paineis, ensure_ascii=False), encoding="utf-8"
        )

        # Cria segredos.toml no caminho que o núcleo lê (parent de VARD_CONFIG)
        omni_key = os.environ["OMNI_API_KEY"]
        segredos_toml = f"[lmstudio]\nchave = \"{omni_key}\"\n"
        segredos_path = config_dir.parent / "segredos.toml"
        segredos_path.write_text(segredos_toml, encoding="utf-8")

        # --- Prova 1: MCPs diretos ---
        print("→ Provando MCPs diretamente (sem modelo)...")
        try:
            relatorio["provas_mcps_diretos"] = await provar_mcps_diretos(config_dir, dados_dir)
        except Exception as exc:
            relatorio["provas_mcps_diretos"] = [{"erro": sanitizar(str(exc)[:300])}]

        # --- Prova 2: Cérebro por HTTP/SSE ---
        print("→ Subindo núcleo para prova HTTP/SSE...")
        porta_nucleo = _porta_livre()

        # Inicia núcleo como subprocesso
        proc_nucleo = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", str(porta_nucleo),
             "--log-level", "warning"],
            cwd=str(NUCLEO_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "VARD_CONFIG": str(config_dir), "VARD_DADOS": str(dados_dir)},
        )
        processos.append(_ProcessoGerenciado("nucleo", proc_nucleo))

        print(f"→ Provando cérebro via HTTP/SSE (porta {porta_nucleo})...")
        try:
            relatorio["prova_cerebro_http"] = await provar_cerebro_http(
                config_dir, dados_dir, porta_nucleo
            )
        except Exception as exc:
            relatorio["prova_cerebro_http"] = {"erro": sanitizar(str(exc)[:300])}

    # Encerra todos os processos
    print("→ Encerrando processos...")
    for p in processos:
        info = p.encerrar()
        relatorio["processos"].append(info)
        print(f"  {info['nome']} (PID {info['pid']}): {info['terminado']}")

    # Escreve relatório
    destino = saida or Path(tempfile.gettempdir()) / f"vard-j2-prova-{int(time.time())}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"→ Relatório escrito em: {destino}")

    return relatorio


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prova real de ferramentas J2")
    parser.add_argument("--saida", type=Path, help="Caminho do JSON de saída")
    args = parser.parse_args()
    asyncio.run(main(args.saida))