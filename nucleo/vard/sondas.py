"""Prazos das sondas HTTP curtas (/status, /recursos).

No Windows, conectar numa porta fechada do 127.0.0.1 leva ~2 s: o SYN é repetido depois do RST.
Um serviço local que está no ar aceita a conexão em milissegundos; por isso o prazo de conexão
no loopback é curto. Endereço de outra máquina (LM Studio na rede) ganha um pouco mais de folga.
A leitura de quem já conectou mantém o prazo de sempre.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

import httpx

CONEXAO_LOCAL_S = 0.5
CONEXAO_REMOTA_S = 1.0
LEITURA_S = 2.0


def loopback(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def prazo(url: str, leitura: float = LEITURA_S) -> httpx.Timeout:
    """Prazo de uma sonda a `url`: conexão curta (loopback) ou um pouco maior (rede); leitura igual."""
    conexao = CONEXAO_LOCAL_S if loopback(url) else CONEXAO_REMOTA_S
    return httpx.Timeout(leitura, connect=conexao)
