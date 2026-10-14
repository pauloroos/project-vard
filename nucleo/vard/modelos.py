"""Clientes HTTP: OpenJarvis (agente com ferramentas) e LM Studio (visão)."""
from __future__ import annotations

import httpx


def _local(base: str) -> bool:
    # Loopback nunca passa por proxy do ambiente (o httpx tentaria e daria timeout).
    return base.startswith(("http://127.0.0.1", "http://localhost"))


class ErroModelo(Exception):
    """Falha ao falar com um modelo. `codigo` é curto e estável (a aba o traduz em fala);
    `detalhe` é só para o log da ponte, nunca vai para a boca."""

    def __init__(self, codigo: str, detalhe: str = ""):
        super().__init__(codigo)
        self.codigo = codigo
        self.detalhe = detalhe


def _conteudo(resposta: httpx.Response) -> str:
    try:
        dados = resposta.json()
    except ValueError as exc:
        raise ErroModelo("nao_json", "resposta não é JSON") from exc
    escolhas = dados.get("choices") or []
    texto = ((escolhas[0].get("message") or {}).get("content") or "") if escolhas else ""
    if not texto.strip():
        raise ErroModelo("modelo_vazio", "choices vazio ou content vazio")
    return texto


def _postar(url: str, base: str, *, fora: str, demorou: str, **kw) -> httpx.Response:
    try:
        r = httpx.post(url, trust_env=not _local(base), **kw)
        r.raise_for_status()
    except httpx.ConnectError as exc:
        raise ErroModelo("modelo_fora", f"{fora}: {base}") from exc
    except httpx.TimeoutException as exc:
        raise ErroModelo("modelo_demorou", demorou) from exc
    except httpx.HTTPStatusError as exc:
        raise ErroModelo("modelo_http", f"HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise ErroModelo("rede", type(exc).__name__) from exc
    return r


def perguntar_openjarvis(
    mensagens: list[dict], *, base: str = "http://127.0.0.1:8000", modelo: str, timeout: float = 90
) -> str:
    # Sem o campo "tools": é assim que o jarvis serve escolhe o caminho do agente.
    corpo = {"model": modelo, "messages": mensagens, "stream": False}
    r = _postar(f"{base}/v1/chat/completions", base, fora="OpenJarvis fora do ar", demorou="OpenJarvis demorou", json=corpo, timeout=timeout)
    return _conteudo(r)


def ver_imagem(
    jpeg_b64: str, pergunta: str, *, base: str = "http://127.0.0.1:1234", modelo: str, timeout: float = 60,
    instrucao: str = "", chave: str = "",
) -> str:
    mensagens = [
        {"role": "system", "content": instrucao},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": pergunta},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64}"}},
            ],
        },
    ]
    cabecalhos = {"Authorization": f"Bearer {chave}"} if chave else {}
    corpo = {"model": modelo, "messages": mensagens, "max_tokens": 1024, "stream": False}
    if ":1234" in base:   # só o LM Studio: sem o "pensamento" do Gemma (~3 s a menos); OmniRouter/vllm não recebem
        corpo["reasoning_effort"] = "none"
    r = _postar(f"{base}/v1/chat/completions", base, fora="servidor de visão fora do ar", demorou="visão demorou", json=corpo, headers=cabecalhos, timeout=timeout)
    return _conteudo(r)
