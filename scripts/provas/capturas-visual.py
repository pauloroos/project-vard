#!/usr/bin/env python3
"""Captura o estado visual atual das três telas do Vard: HUD, Sala e Configurações.

Executa no navegador Chromium headless via Playwright com mock do ambiente Tauri,
sem necessidade de WebView2 ou Windows.

Uso:
    PLAYWRIGHT_BROWSERS_PATH=<diretório de navegadores do Playwright> \\
    python scripts/provas/capturas-visual.py --saida PASTA [--url URL]
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
TAMANHO_MINIMO_PNG = 2048  # 2 KB

ABAS_CONFIGURACOES = [
    "geral",
    "perfil",
    "voz",
    "transcricao",
    "atalhos",
    "oficina",
    "modelos",
    "paineis-mcps",
    "sistema",
    "reuniao",
    "avisos",
    "diagnostico",
]

# Dados fictícios para o mock do Tauri (sem informações pessoais)
CONFIG_FICTICIA: dict[str, Any] = {
    "openjarvis_url": "http://127.0.0.1:8000",
    "gui_url": "http://127.0.0.1:5173",
    "ponte_url": "",
    "voz_url": "http://127.0.0.1:4710",
    "nome": "Aurora",
    "usuario": "",
    "variantes": ["Aurora", "Auri", "Au"],
    "idioma": "pt",
    "voz": "pm_alex",
    "velocidade": 1.05,
    "vad": "energia",
    "interromper_ao_falar": False,
    "finish_ms": 900,
    "limiar_vad": 0.02,
    "sempre_no_topo": True,
    "click_through": False,
    "invisivel": False,
    "posicao": None,
    "tamanho": "medio",
    "tamanho_px": 320,
    "compacto": False,
    "atalhos": {
        "falar": "Alt+Super+Space",
        "parar": "Alt+Super+Period",
        "mostrar": "Alt+Super+V",
        "config": "Shift+Super+K",
        "escuta": "Alt+Super+L",
        "sala": "Shift+Super+G",
        "naofalar": "Alt+Super+N",
        "conversa": "Alt+Super+C",
    },
    "instrucao_formato": "Responda em até duas frases, para ser lido em voz alta.",
    "modelo": "",
    "sala_monitor": "",
    "conversa_ms": 20000,
    "voz_provedor": "propria",
    "voz_motor": "",
    "voz_propria": "",
    "elevenlabs_chave": "",
    "elevenlabs_voz": "",
    "gemini_chave": "",
    "gemini_voz": "Kore",
    "voz_reserva_provedor": "nenhuma",
    "voz_reserva_motor": "",
    "voz_reserva_id": "",
    "atualizacao_ao_abrir": False,
    "nao_ouvir": False,
    "nao_falar": False,
    "falar_avisos": False,
    "cerebro": "openjarvis",
    "usar_openjarvis": False,
    "microfone_id": "",
    "microfone_rotulo": "",
    "saida_id": "",
    "saida_rotulo": "",
    "cor_elementos": "",
    "opacidade_elementos": 1,
    "stt_modelo": "",
    "stt_dispositivo": "",
}

PAINEIS_CONFIG_FICTICIA: dict[str, Any] = {
    "versao": 1,
    "provedores": [
        {
            "id": "openai-gpt4o",
            "nome": "OpenAI GPT-4o Omni (Produção)",
            "tipo": "openai",
            "url_base": "https://api.openai.com/v1/chat/completions",
            "modelo": "gpt-4o-2024-08-06",
            "credencial_ref": "env:OPENAI_API_KEY",
        },
        {
            "id": "anthropic-claude",
            "nome": "Anthropic Claude 3.5 Sonnet v2",
            "tipo": "anthropic",
            "url_base": "https://api.anthropic.com/v1/messages",
            "modelo": "claude-3-5-sonnet-20241022",
            "credencial_ref": "cofre:anthropic_prod",
        },
        {
            "id": "ollama-local",
            "nome": "Ollama Local Llama 3.1 70B Q4_K_M",
            "tipo": "ollama",
            "url_base": "http://127.0.0.1:11434/api/chat",
            "modelo": "llama3.1:70b-instruct-q4_K_M",
            "credencial_ref": "",
        },
        {
            "id": "cli-claude-code",
            "nome": "Claude Code CLI (Agente Principal)",
            "tipo": "cli-claude",
            "url_base": "",
            "modelo": "claude-sonnet-5-5",
            "yolo": True,
            "enxuto": False,
            "esforco": "high",
        },
    ],
    "ativo": "anthropic-claude",
    "reserva": "ollama-local",
    "agentes": {
        "claude": {
            "padrao": "claude-sonnet-5-5",
            "modelos": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        },
        "codex": {"padrao": "o3-mini", "modelos": ["o3-mini", "o4-mini", "gpt-4o"]},
        "opencode": {
            "padrao": "gemini-2.5-pro",
            "modelos": ["gemini-2.5-pro", "gemini-2.5-flash"],
        },
        "agy": {"padrao": "agy-v1", "modelos": ["agy-v1", "agy-v0"]},
    },
    "mcps": [
        {
            "id": "filesystem",
            "nome": "Filesystem MCP Server",
            "habilitado": True,
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "projetos"],
            "credencial_ref": "",
        },
        {
            "id": "github",
            "nome": "GitHub MCP (Repos & Issues)",
            "habilitado": True,
            "url": "https://mcp.github.com/api/v1/stream",
            "credencial_ref": "cofre:github_mcp_token",
        },
        {
            "id": "postgres-dev",
            "nome": "PostgreSQL Dev Database",
            "habilitado": False,
            "command": "docker",
            "args": ["exec", "-i", "postgres-dev", "psql", "-U", "devuser"],
            "credencial_ref": "env:PGPASSWORD",
        },
    ],
}

PAINEIS_ESTADO_FICTICIO: dict[str, Any] = {
    "revisao": 3,
    "estado": "aplicado",
    "ativo_efetivo": "anthropic-claude",
    "reserva_efetiva": "ollama-local",
}

MONITORES_FICTICIOS: list[dict[str, str]] = [
    {"id": r"\\.\DISPLAY1", "nome": "Monitor Principal 1920x1080"},
    {"id": r"\\.\DISPLAY2", "nome": "Monitor Secundário 2560x1440"},
]

RELEASE_FICTICIA: dict[str, Any] = {
    "url": "https://github.com/exemplo/vard/releases/download/v0.0.0-prova/vard-setup.exe",
    "nome": "vard-setup.exe",
    "bytes": 1234567,
    "sha256": "0123456789abcdef",
}

CONFIG_JSON = json.dumps(CONFIG_FICTICIA)
PAINEIS_CONFIG_JSON = json.dumps(PAINEIS_CONFIG_FICTICIA)
PAINEIS_ESTADO_JSON = json.dumps(PAINEIS_ESTADO_FICTICIO)
MONITORES_JSON = json.dumps(MONITORES_FICTICIOS)
RELEASE_JSON = json.dumps(RELEASE_FICTICIA)

# Código JS injetado em cada página para mockar @tauri-apps/api v2
INIT_SCRIPT = f"""
(() => {{
  let proxId = 1;
  const listeners = {{}};

  const configFicticia = {CONFIG_JSON};
  const paineisConfig = {PAINEIS_CONFIG_JSON};
  const paineisEstado = {PAINEIS_ESTADO_JSON};
  const monitores = {MONITORES_JSON};
  const release = {RELEASE_JSON};

  const invokeMock = async (cmd, args) => {{
    if (typeof cmd === "string" && cmd.startsWith("plugin:")) {{
      if (cmd === "plugin:event|listen") {{
        const ev = args && args.event;
        const hId = args && args.handler;
        if (ev && hId !== undefined) {{
          listeners[ev] = listeners[ev] || [];
          listeners[ev].push(hId);
        }}
      }}
      return proxId++;
    }}
    if (cmd === "ler_config") return configFicticia;
    if (cmd === "ler_paineis") {{
      if (args && args.arquivo === "estado") return paineisEstado;
      return paineisConfig;
    }}
    if (cmd === "falhas_de_atalho") return [];
    if (cmd === "inicio_no_logon_ativo") return false;
    if (cmd === "listar_monitores") return monitores;
    if (cmd === "versao_do_app") return "0.0.0-prova";
    if (cmd === "buscar_release") return release;
    return null;
  }};

  window.__TAURI__ = {{
    core: {{ invoke: invokeMock }},
    event: {{
      emitTo: async () => {{}},
      emit: async () => {{}},
      listen: async () => () => {{}},
    }},
  }};

  window.__TAURI_INTERNALS__ = {{
    invoke: invokeMock,
    transformCallback: (cb, once) => {{
      const id = proxId++;
      window["_" + id] = (res) => {{
        if (once) delete window["_" + id];
        return cb(res);
      }};
      return id;
    }},
    unregisterCallback: (id) => {{
      delete window["_" + id];
    }},
    convertFileSrc: (p) => p,
    metadata: {{
      get currentWindow() {{
        const p = window.location.pathname;
        const lbl = p.includes("sala") ? "sala" : p.includes("configuracoes") ? "configuracoes" : "main";
        return {{ label: lbl }};
      }},
      get currentWebview() {{
        const p = window.location.pathname;
        const lbl = p.includes("sala") ? "sala" : p.includes("configuracoes") ? "configuracoes" : "main";
        return {{ windowLabel: lbl, label: lbl }};
      }},
    }},
  }};

  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {{
    unregisterListener: () => {{}},
  }};

  // Helper global para disparo controlado de eventos
  window.__vardDispararEvento = (evento, payload) => {{
    const hIds = listeners[evento] || [];
    for (const hId of hIds) {{
      const fn = window["_" + hId];
      if (typeof fn === "function") {{
        fn({{ event: evento, id: hId, payload: payload }});
      }}
    }}
  }};
}})();
"""


def esperar_servidor(processo: subprocess.Popen[str], timeout: float = 15.0) -> None:
    """Aceita somente o aviso de prontidão emitido pelo processo que iniciamos."""
    linhas: queue.Queue[str | None] = queue.Queue()
    def ler_saida() -> None:
        assert processo.stdout is not None
        for linha in processo.stdout:
            linhas.put(linha)
        linhas.put(None)
    threading.Thread(target=ler_saida, daemon=True).start()
    limite = time.monotonic() + timeout
    while True:
        try:
            linha = linhas.get(timeout=max(0, limite - time.monotonic()))
        except queue.Empty:
            raise TimeoutError("Vite não sinalizou prontidão no prazo.") from None
        if linha is None:
            raise RuntimeError("Vite encerrou antes de sinalizar prontidão.")
        if "Local:" in linha and "http://127.0.0.1:5199/" in linha:
            if processo.poll() is not None:
                raise RuntimeError("Vite encerrou após sinalizar prontidão.")
            return


def verificar_arquivo_png(caminho: Path) -> None:
    """Garante que a captura existe e tem pelo menos o tamanho mínimo esperado."""
    if not caminho.is_file():
        raise FileNotFoundError(f"Captura não gerada: {caminho}")
    tamanho = caminho.stat().st_size
    if tamanho < TAMANHO_MINIMO_PNG:
        raise ValueError(
            f"Captura em branco ou corrompida: {caminho} possui {tamanho} bytes "
            f"(mínimo exigido: {TAMANHO_MINIMO_PNG} bytes)."
        )


def configurar_rotas_mock(contexto: Any, url_base: str) -> None:
    """Isola serviços reais; somente os arquivos da origem de prova são acessíveis."""
    base = urlsplit(url_base)
    origem = (base.scheme, base.hostname, base.port)
    if base.scheme not in ("http", "https") or not base.hostname:
        raise ValueError("A URL de prova deve ser HTTP ou HTTPS.")

    def rotear(rota: Any) -> None:
        url = urlsplit(rota.request.url)
        if (url.scheme, url.hostname, url.port) != origem:
            rota.abort()
        elif url.path in ("/oj/health", "/oj/v1/speech/health"):
            corpo = {"status": "ok"} if url.path == "/oj/health" else {"available": True}
            rota.fulfill(status=200, content_type="application/json", body=json.dumps(corpo))
        elif url.path == "/oj" or url.path.startswith("/oj/"):
            rota.abort()
        else:
            rota.continue_()

    contexto.route("**/*", rotear)
    contexto.route_web_socket("**/*", lambda websocket: websocket.close())


def capturar_hud(page: Any, url_base: str, saida_dir: Path) -> None:
    """Captura a tela HUD (index.html) com viewport 320x360 e escala 2x."""
    page.on("pageerror", lambda err: print("[HUD PAGEERROR]:", err))
    page.on("console", lambda m: print(f"[HUD CONSOLE {m.type}]:", m.text) if m.type == "error" else None)
    page.set_viewport_size({"width": 320, "height": 360})
    page.goto(f"{url_base}/index.html")
    page.wait_for_selector("#nucleo", timeout=10000)

    # Garante transição completa para estado de repouso ("pronto")
    page.wait_for_function(
        "() => document.getElementById('dica')?.textContent?.toLowerCase().includes('pronto') || "
        "document.getElementById('app')?.dataset?.estado === 'repouso'",
        timeout=5000,
    )

    # Fundo sintético escuro neutro atrás do widget transparente para visualização nítida
    page.evaluate("document.body.style.backgroundColor = '#0b0f17';")

    # Espera quadro estável da animação do núcleo
    page.wait_for_timeout(600)

    destino = saida_dir / "hud.png"
    page.screenshot(path=str(destino), full_page=False)
    verificar_arquivo_png(destino)
    print(f"[OK] HUD capturado: {destino.name} ({destino.stat().st_size} bytes)")


def capturar_sala(page: Any, url_base: str, saida_dir: Path) -> None:
    """Captura a tela da sala (sala.html) com viewport 1280x800 e escala 1x."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{url_base}/sala.html")
    page.wait_for_selector("#nucleo", timeout=10000)
    page.wait_for_selector("#relogio", timeout=10000)
    page.wait_for_timeout(300)

    # Dispara retrato fictício pelo mock do evento sala:espelho
    page.evaluate("""
        window.__vardDispararEvento("sala:espelho", {
            tipo: "retrato",
            espelho: {
                estado: "repouso",
                detalhe: "pronto",
                ouvido: "qual é o status do laboratório?",
                resposta: "todos os sistemas operando normalmente"
            }
        });
    """)

    page.wait_for_function(
        "document.getElementById('ouvido')?.textContent?.includes('qual é o status do laboratório?')",
        timeout=5000,
    )
    page.wait_for_function(
        "document.getElementById('resposta')?.textContent?.includes('todos os sistemas operando normalmente')",
        timeout=5000,
    )
    page.wait_for_timeout(400)

    destino = saida_dir / "sala.png"
    page.screenshot(path=str(destino), full_page=False)
    verificar_arquivo_png(destino)
    print(f"[OK] Sala capturada: {destino.name} ({destino.stat().st_size} bytes)")


def capturar_configuracoes(page: Any, url_base: str, saida_dir: Path) -> None:
    """Captura cada aba da tela de configurações (configuracoes.html) com viewport 960x640."""
    page.set_viewport_size({"width": 960, "height": 640})
    page.goto(f"{url_base}/configuracoes.html")
    page.wait_for_selector("#painel nav button", timeout=10000)

    for aba in ABAS_CONFIGURACOES:
        btn = page.wait_for_selector(f'nav button[data-aba="{aba}"]', timeout=5000)
        btn.click()
        page.wait_for_selector(f'section[data-aba="{aba}"]:not([hidden])', timeout=5000)
        page.wait_for_timeout(300)

        destino = saida_dir / f"configuracoes-{aba}.png"
        page.screenshot(path=str(destino), full_page=False)
        verificar_arquivo_png(destino)
        print(f"[OK] Configurações ({aba}): {destino.name} ({destino.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera capturas de referência visual do Vard.")
    parser.add_argument(
        "--url",
        default=None,
        help="Endereço base do Vite (ex.: http://127.0.0.1:5199). Se omitido, sobe o Vite automaticamente.",
    )
    parser.add_argument(
        "--saida",
        required=True,
        help="Novo diretório onde salvar as capturas; não pode existir anteriormente.",
    )
    args = parser.parse_args()

    saida_dir = RAIZ / args.saida if not Path(args.saida).is_absolute() else Path(args.saida)
    saida_dir.mkdir(parents=True, exist_ok=False)

    vite_proc: subprocess.Popen[str] | None = None
    url_base = args.url

    try:
        if not url_base:
            porta = 5199
            url_base = f"http://127.0.0.1:{porta}"
            env = os.environ.copy()
            env["VITE_PROVA"] = "repouso"

            vite_script = RAIZ / "node_modules" / "vite" / "bin" / "vite.js"
            comando = [
                "node",
                str(vite_script),
                "--host",
                "127.0.0.1",
                "--port",
                str(porta),
                "--strictPort",
            ]

            print(f"[Vite] Iniciando servidor de prova na porta {porta}...")
            vite_proc = subprocess.Popen(
                comando,
                cwd=str(RAIZ),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            esperar_servidor(vite_proc)
            print(f"[Vite] Servidor pronto em {url_base}.")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                # 1. Contexto para HUD (device_scale_factor=2)
                context_hud = browser.new_context(device_scale_factor=2, service_workers="block")
                configurar_rotas_mock(context_hud, url_base)
                page_hud = context_hud.new_page()
                page_hud.add_init_script(INIT_SCRIPT)
                capturar_hud(page_hud, url_base, saida_dir)
                context_hud.close()

                # 2. Contexto para Sala e Configurações (device_scale_factor=1)
                context_geral = browser.new_context(device_scale_factor=1, service_workers="block")
                configurar_rotas_mock(context_geral, url_base)
                page_geral = context_geral.new_page()
                page_geral.add_init_script(INIT_SCRIPT)

                capturar_sala(page_geral, url_base, saida_dir)
                capturar_configuracoes(page_geral, url_base, saida_dir)
                context_geral.close()

            finally:
                browser.close()

        print(f"\n[SUCESSO] Todas as 14 capturas foram geradas em {saida_dir}.")

    finally:
        if vite_proc is not None:
            print("[Vite] Encerrando processo do Vite...")
            vite_proc.terminate()
            try:
                vite_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                vite_proc.kill()
                vite_proc.wait(timeout=5)
            print("[Vite] Processo encerrado.")


if __name__ == "__main__":
    main()
