"""Ícone da bandeja do Vard. Chama o vard-modo.ps1 e relê o estado a cada 5 s."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

NUCLEO = Path(__file__).resolve().parents[2] / "nucleo"   # raiz do repositório/núcleo
sys.path.insert(0, str(NUCLEO))
import pystray  # noqa: E402

from vard import bandeja, modo  # noqa: E402

LOG_MODO = modo.PASTA / "logs" / "vard-modo.log"


def _rodar(verbo: str) -> None:
    try:
        if verbo == "log":
            os.startfile(str(LOG_MODO))
        elif verbo == "preflight":
            subprocess.Popen(["powershell", "-NoProfile", "-NoExit", "-Command", "uv run python preflight.py"], cwd=str(NUCLEO))
        else:
            modo.disparar(verbo)   # inclui "aba": o script só abre a janela do Vard se ela não existir
    except Exception as exc:
        print(f"bandeja: {verbo}: {exc}", file=sys.stderr)


def _menu(icone: pystray.Icon, estado: str) -> pystray.Menu:
    itens = []
    for rotulo, verbo in bandeja.itens_menu(estado):
        if verbo is None:
            itens.append(pystray.Menu.SEPARATOR)
        elif verbo == "sair":
            itens.append(pystray.MenuItem(rotulo, lambda: icone.stop()))
        else:
            itens.append(pystray.MenuItem(rotulo, (lambda v: (lambda: _rodar(v)))(verbo)))
    return pystray.Menu(*itens)


def _estado_voz() -> str:
    """vard-voz em :4710: ligado (pronta), aquecendo (responde, modelo carregando) ou desligado."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:4710/saude", timeout=1.5) as r:
            return "ligado" if json.load(r).get("pronta") else "aquecendo"
    except Exception:
        return "desligado"


def _vigiar(icone: pystray.Icon) -> None:
    anterior = None
    voz_ant = None
    while True:
        try:
            atual = modo.ler_estado()
            voz = _estado_voz()
            if anterior is None or (atual["modo"], atual["detalhe"], voz) != (anterior["modo"], anterior["detalhe"], voz_ant):
                icone.icon = bandeja.desenhar_icone(atual["modo"])
                icone.title = bandeja.titulo(atual, voz)
                if anterior is None or atual["modo"] != anterior["modo"]:
                    icone.menu = _menu(icone, atual["modo"])
                    try:
                        icone.update_menu()
                    except Exception as exc:
                        print(f"bandeja: update_menu: {exc}", file=sys.stderr)
                if bandeja.deve_avisar(anterior, atual):
                    try:
                        icone.notify(atual["detalhe"] or "falhou (ver Abrir log)", "Vard")
                    except Exception as exc:
                        print(f"bandeja: notify: {exc}", file=sys.stderr)
                anterior, voz_ant = atual, voz
        except Exception as exc:
            print(f"bandeja: {exc}", file=sys.stderr)
        time.sleep(5)


def _setup(icone: pystray.Icon) -> None:
    # Setup do pystray: o ícone já está registrado (o balão do notify só funciona daí em diante).
    # O vigia vai numa thread daemon: a thread do setup não é daemon e prenderia o "Sair da bandeja".
    icone.visible = True
    threading.Thread(target=_vigiar, args=(icone,), daemon=True).start()


def _registrar(msg: str) -> None:
    """Uma linha com hora em logs\bandeja.log (início, PID, saída): se a bandeja sumir, o log diz como saiu."""
    try:
        arq = modo.PASTA / "logs" / "bandeja.log"
        arq.parent.mkdir(parents=True, exist_ok=True)
        with arq.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def main() -> None:
    _registrar("início")
    motivo = "saída normal (Sair da bandeja)"
    try:
        estado = modo.ler_estado()
        icone = pystray.Icon("Vard", bandeja.desenhar_icone(estado["modo"]), bandeja.titulo(estado))
        icone.menu = _menu(icone, estado["modo"])
        icone.run(setup=_setup)
    except BaseException as exc:
        motivo = f"saiu por {type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        _registrar(motivo)


if __name__ == "__main__":
    main()
