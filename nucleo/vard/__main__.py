"""Entrada do núcleo: python -m vard servir | --versao."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vard")
    ap.add_argument("--versao", action="store_true", help="mostra a versão e sai")
    sub = ap.add_subparsers(dest="comando")
    servir_p = sub.add_parser("servir", help="sobe o núcleo em loopback")
    servir_p.add_argument("--porta", type=int, default=4700, help="porta TCP (padrão 4700)")
    servir_p.add_argument("--host", default="127.0.0.1", help="host de bind (padrão 127.0.0.1)")
    args = ap.parse_args(argv)

    if args.versao:
        from . import __version__
        print(__version__)
        return 0

    if args.comando == "servir":
        from . import servidor
        return servidor.servir(porta=args.porta, host=args.host)

    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())