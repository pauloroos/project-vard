"""Estado do assistente de primeiro uso: progresso retomável separado da config ativa.

Persistência atômica em VARD_DADOS/primeiro_uso.json. Configuração preexistente
(config.toml com nome não vazio) marca concluido=true automaticamente para que o
assistente nunca apareça nem mude nada para quem já tem instalação configurada.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from vard import config as modulo_config

VERSAO_SCHEMA = 1
ETAPAS = ("importar", "detectar", "nome", "cerebro", "voz", "audio", "resumo")
ARQUIVO_NOME = "primeiro_uso.json"


def _caminho() -> Path:
    return modulo_config.pasta_dados() / ARQUIVO_NOME


def _ler_bruto() -> dict[str, Any]:
    arq = _caminho()
    try:
        texto = arq.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        dados = json.loads(texto)
    except ValueError:
        return {}
    if not isinstance(dados, dict):
        return {}
    return dados


def _gravar(dados: dict[str, Any]) -> None:
    arq = _caminho()
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, arq)


def _hud_config_tem_nome() -> bool:
    """True quando hud.config.json do widget tem campo nome não vazio.

    Em testes, VARD_HUD_CONFIG_DIR sobrescreve o caminho base para evitar
    leitura do APPDATA real do sistema. Sem essa variável, usa APPDATA.
    """
    hud_dir_override = os.environ.get("VARD_HUD_CONFIG_DIR", "")
    if hud_dir_override:
        hud_arq = Path(hud_dir_override) / "hud.config.json"
    else:
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return False
        hud_arq = Path(appdata) / "io.github.pauloroos.vard" / "hud.config.json"
    try:
        texto = hud_arq.read_text(encoding="utf-8")
        dados = json.loads(texto)
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    if not isinstance(dados, dict):
        return False
    nome = dados.get("nome", "")
    return bool(str(nome).strip())


def _config_existe() -> bool:
    """True quando há qualquer sinal real de instalação já configurada.

    Verifica em ordem: hud.config.json com nome, persona.md, openjarvis.toml,
    instalacao.json com raiz_codigo. Config.toml com nome também conta para
    compatibilidade com testes e instalações futuras.
    """
    # 1. hud.config.json do widget (fonte primária de nome/usuario)
    if _hud_config_tem_nome():
        return True
    # 2. persona.md na pasta de config
    persona = modulo_config.arquivo_config("persona.md")
    if persona.exists():
        return True
    # 3. openjarvis.toml na pasta de config
    oj_toml = modulo_config.arquivo_config("openjarvis.toml")
    if oj_toml.exists():
        return True
    # 4. instalacao.json com raiz_codigo na pasta de dados
    inst_arq = modulo_config.pasta_dados() / "instalacao.json"
    try:
        texto = inst_arq.read_text(encoding="utf-8")
        inst = json.loads(texto)
        if isinstance(inst, dict) and str(inst.get("raiz_codigo", "")).strip():
            return True
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    # 5. config.toml com nome (compatibilidade)
    cfg_toml = modulo_config.arquivo_config("config.toml")
    try:
        with cfg_toml.open("rb") as f:
            dados = tomllib.load(f)
        if isinstance(dados, dict) and str(dados.get("nome", "")).strip():
            return True
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    return False


def ler() -> dict[str, Any]:
    """Lê o estado atual; instalação preexistente devolve concluido=True sem abrir assistente."""
    if _config_existe():
        return {
            "schema": VERSAO_SCHEMA,
            "etapa": ETAPAS[-1],
            "concluido": True,
            "pendencias": [],
        }
    bruto = _ler_bruto()
    schema = bruto.get("schema")
    if schema != VERSAO_SCHEMA:
        return {"schema": VERSAO_SCHEMA, "etapa": ETAPAS[0], "concluido": False, "pendencias": []}
    etapa = bruto.get("etapa") if bruto.get("etapa") in ETAPAS else ETAPAS[0]
    concluido = bruto.get("concluido") is True
    pendencias = bruto.get("pendencias") if isinstance(bruto.get("pendencias"), list) else []
    estado: dict[str, Any] = {
        "schema": VERSAO_SCHEMA,
        "etapa": etapa,
        "concluido": concluido,
        "pendencias": [str(p) for p in pendencias if str(p).strip()],
    }
    for chave in ("nome_chamada", "cerebro_id", "voz_id", "microfone_id", "saida_id"):
        if chave in bruto and isinstance(bruto[chave], str):
            estado[chave] = bruto[chave]
    return estado


def atualizar(patch: dict[str, Any]) -> dict[str, Any]:
    """Aplica campos conhecidos ao estado e grava atomicamente; devolve o estado saneado."""
    atual = ler()
    if atual.get("concluido"):
        return atual
    campos_validos = {
        "etapa", "concluido", "nome_chamada", "cerebro_id", "voz_id",
        "microfone_id", "saida_id", "pendencias",
    }
    for chave, valor in patch.items():
        if chave not in campos_validos:
            continue
        if chave == "etapa" and valor in ETAPAS:
            atual["etapa"] = valor
        elif chave == "concluido" and valor is True:
            atual["concluido"] = True
        elif chave == "pendencias" and isinstance(valor, list):
            atual["pendencias"] = [str(p) for p in valor if str(p).strip()]
        elif chave in ("nome_chamada", "cerebro_id", "voz_id", "microfone_id", "saida_id"):
            if isinstance(valor, str):
                atual[chave] = valor
    _gravar(atual)
    return ler()


def reabrir() -> dict[str, Any]:
    """Reabre o assistente sem apagar escolhas salvas; só desmarca concluido."""
    atual = ler()
    if not atual.get("concluido"):
        return atual
    atual["concluido"] = False
    _gravar(atual)
    return ler()


def validar_nome(nome: str) -> str:
    """Nome vazio ou só espaços é recusado; devolve o nome limpo."""
    limpo = str(nome).strip()
    if not limpo:
        raise ValueError("nome_vazio")
    return limpo