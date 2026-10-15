"""Entrada do núcleo: python -m vard servir | --versao."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vard")
    ap.add_argument("--versao", action="store_true", help="mostra a versão e sai")
    sub = ap.add_subparsers(dest="comando")
    sub.add_parser("servir", help="sobe o núcleo em 127.0.0.1:4700")
    args = ap.parse_args(argv)

    if args.versao:
        from . import __version__
        print(__version__)
        return 0

    if args.comando == "servir":
        from . import servidor
        return servidor.servir()

    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())