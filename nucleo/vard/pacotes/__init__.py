"""Pacotes opcionais do Vard (XTTS, vozes extras, reunião).

Este módulo fornece:
- Manifesto: leitura e validação de config/pacotes/*.json
- Instalador: download com hash, staging, promoção atômica e rollback
- Estado: consulta de pacotes instalados via VARD_DADOS/pacotes/estado.json

Regras de segurança:
- Hash SHA-256 obrigatório para download; pacote sem hash é recusado.
- Extração segura: rejeita caminhos com '..', absolutos ou symlinks.
- Staging separado da instalação ativa; promoção só após teste de saúde.
- Cancelamento limpa apenas staging; interrupção permite reiniciar.
- Licença deve ser apresentada antes da instalação (CPML para XTTS-v2).
"""
from .manifesto import carregar_manifesto, carregar_todos_manifestos, validar_pacote, PacoteInfo
from .instalador import InstaladorPacotes, ProgressoInstalacao

__all__ = [
    "carregar_manifesto",
    "carregar_todos_manifestos",
    "validar_pacote",
    "PacoteInfo",
    "InstaladorPacotes",
    "ProgressoInstalacao",
]