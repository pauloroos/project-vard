"""MCPs que o usuário cadastra na aba Ferramentas (MCP) e entram na sessão da CLI.

`servidores_do_usuario()` lê `paineis.json` e devolve, no formato `mcpServers` do Claude Code,
só os MCPs habilitados: stdio vira `command`/`args`; http vira `type: http` e `url`.

Nenhum segredo vai ao arquivo. Um MCP http com `credencial_ref` (tipo:id do cofre) recebe
`headersHelper`: a CLI roda `python -I -m vard.mcp_usuario cabecalhos <ref>` ao conectar, e
este módulo lê o cofre e imprime `{"Authorization": "Bearer <valor>"}` só no stdout desse
auxiliar. Para stdio não existe forma segura de entregar a credencial: o servidor entra sem ela.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Referência aceita para virar comando: só os tipos do cofre e caracteres sem efeito em shell.
_REF_SEGURA = re.compile(r"(provedor|voz|mcp):[A-Za-z0-9._-]{1,128}")


def referencia_segura(ref: object) -> bool:
    return isinstance(ref, str) and _REF_SEGURA.fullmatch(ref) is not None


def comando_cabecalhos(ref: str) -> str:
    """Linha de comando do auxiliar (a CLI a roda num shell): caminho entre aspas, barras normais."""
    python = Path(sys.executable).as_posix()
    return f'"{python}" -I -m vard.mcp_usuario cabecalhos {ref}'


def servidores_do_usuario() -> dict:
    """MCPs habilitados em paineis.json; paineis ausente ou inválido = nenhum."""
    from vard import ajustes
    try:
        doc = ajustes.ler_documento("paineis")
    except Exception:  # noqa: BLE001
        log.warning("paineis.json inválido: os MCPs do usuário ficam fora da sessão")
        return {}
    servidores: dict = {}
    for m in doc.get("mcps", []):
        if not m.get("habilitado"):
            continue
        nome = m["id"]
        ref = m.get("credencial_ref")
        if m.get("command"):
            servidores[nome] = {"command": m["command"], "args": list(m.get("args") or [])}
            if ref:
                log.warning("MCP %s: credencial de servidor stdio não é entregue à CLI", nome)
            continue
        entrada = {"type": "http", "url": m["url"]}
        if ref:
            if referencia_segura(ref):
                entrada["headersHelper"] = comando_cabecalhos(ref)
            else:
                log.warning("MCP %s: referência de credencial fora do formato tipo:id; vai sem credencial", nome)
        servidores[nome] = entrada
    return servidores


def cabecalhos(ref: str) -> dict:
    """Lê a credencial no cofre e monta o cabeçalho. Nunca imprima o retorno fora do auxiliar."""
    from vard import credenciais
    valor = credenciais.ler_para_uso_interno(*credenciais.separar_referencia(ref, "mcp"))
    if not valor:
        raise LookupError("credencial ausente no cofre")
    return {"Authorization": f"Bearer {valor}"}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "cabecalhos" or not referencia_segura(argv[1]):
        print("uso: python -m vard.mcp_usuario cabecalhos tipo:id", file=sys.stderr)
        return 2
    try:
        dados = cabecalhos(argv[1])
    except Exception:  # noqa: BLE001
        print("credencial do MCP indisponível no cofre", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(dados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
