"""Perfil do agente (T14a): `perfil.json`, migração da `persona.md` e montagem da persona.

Arquivo: `VARD_CONFIG/perfil.json` — gravado de forma atômica (tmp + troca).
- `ler()` nunca apaga nada: `persona.md` presente e `perfil.json` ausente importa o
  texto para `instrucoes` em memória; a gravação materializa a migração.
- `montar_persona()` entrega o texto para o laço e para a prévia em ordem fixa:
  cabeçalho (nome/usuário/tom/personalidade) → instruções → sobre a pessoa →
  bloco do produto lido de `config/examples/persona.example.md`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import config as modulo_config

log = logging.getLogger(__name__)

VERSAO = 1
EXEMPLO_PERSONA = Path(__file__).resolve().parents[2] / "config" / "examples" / "persona.example.md"
IDENTIDADE_EXEMPLO = "Você é o Vard, assistente de Fulano."


@dataclass
class Perfil:
    tom: str = ""
    personalidade: str = ""
    instrucoes: str = ""
    sobre_usuario: str = ""
    versao: int = VERSAO


def caminho() -> Path:
    """Arquivo do perfil dentro da pasta de configuração."""
    return modulo_config.arquivo_config("perfil.json")


def ler() -> Perfil:
    """Lê o perfil; sem arquivo migra a persona.md; ilegível cai no padrão e avisa."""
    arq = caminho()
    try:
        bruto = arq.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _migrar_persona_md()
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as erro:
        log.warning("perfil.json inválido (%s); usando o padrão", erro)
        return Perfil()
    if not isinstance(dados, dict):
        log.warning("perfil.json inválido (conteúdo não é objeto); usando o padrão")
        return Perfil()
    lido = _de_dict(dados)
    # Um perfil salvo em branco pela tela não pode esconder a persona.md que o usuário já escreveu.
    if not any(getattr(lido, c).strip() for c in ("tom", "personalidade", "instrucoes", "sobre_usuario")):
        migrado = _migrar_persona_md()
        if migrado.instrucoes.strip():
            return migrado
    return lido


def gravar(perfil: Perfil) -> None:
    """Grava o perfil de forma atômica, sem deixar arquivo temporário no fim."""
    arq = caminho()
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.parent / f"{arq.name}.tmp"
    tmp.write_text(json.dumps(asdict(perfil), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, arq)


def montar_persona(perfil: Perfil, nome: str, usuario: str) -> str:
    """Monta a persona na ordem fixa: cabeçalho, instruções, sobre a pessoa, produto."""
    cabecalho = ["# Perfil do agente"]
    nome = (nome or "").strip()
    usuario = (usuario or "").strip()
    if nome:
        cabecalho.append(f"Nome do assistente: {nome}")
    if usuario:
        cabecalho.append(f"Como chamar a pessoa: {usuario}")
    if perfil.tom.strip():
        cabecalho.append(f"Tom: {perfil.tom.strip()}")
    if perfil.personalidade.strip():
        cabecalho.append(f"Personalidade: {perfil.personalidade.strip()}")
    partes = ["\n".join(cabecalho)]
    if perfil.instrucoes.strip():
        partes.append(perfil.instrucoes.strip())
    if perfil.sobre_usuario.strip():
        partes.append(f"# Sobre a pessoa\n{perfil.sobre_usuario.strip()}")
    produto = _bloco_produto().strip()
    if produto and nome:
        # O exemplo do produto apresenta "o Vard, assistente de Fulano": troca pelos nomes reais.
        quem = f"Você é {nome}, assistente de {usuario}." if usuario else f"Você é {nome}."
        produto = produto.replace(IDENTIDADE_EXEMPLO, quem, 1)
    if produto:
        partes.append(produto)
    partes.append("Há habilidades cadastradas pelo usuário; antes de agir num pedido, consulte listar_habilidades do MCP de configurações, se a ferramenta estiver disponível.")
    return "\n\n".join(partes)


def _migrar_persona_md() -> Perfil:
    """C9: persona.md sem perfil.json importa o texto para instrucoes, sem apagar nada."""
    try:
        texto = modulo_config.arquivo_config("persona.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return Perfil()
    return Perfil(instrucoes=texto)


def _de_dict(dados: dict) -> Perfil:
    valores = {"versao": VERSAO}
    for campo in fields(Perfil):
        bruto = dados.get(campo.name)
        if campo.name == "versao":
            if isinstance(bruto, int) and not isinstance(bruto, bool):
                valores["versao"] = bruto
        elif isinstance(bruto, str):
            valores[campo.name] = bruto
        elif bruto is not None:
            log.warning("perfil.json: campo %s ilegível; usando o padrão", campo.name)
    return Perfil(**valores)


def _bloco_produto() -> str:
    try:
        return EXEMPLO_PERSONA.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
