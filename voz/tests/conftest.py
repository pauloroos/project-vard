"""Guarda do PC real compartilhada com os testes do núcleo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nucleo" / "tests"))
from guarda_pc import (instalar, guarda_pc, powershell_isolado, pytest_addoption,
                      pytest_configure, pytest_collection_modifyitems)

instalar()

