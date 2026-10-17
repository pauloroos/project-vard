"""Oficina: contrato de habilidades.json compartilhado com a tela e o Rust.

Fábrica fica no código; o arquivo contém receitas do usuário, IDs desligados e, em "fabrica",
os ajustes opcionais (nome, quando, instrucoes) de cada capacidade de fábrica, apagados ao restaurar o padrão.
Datas UTC ISO 8601 com segundos ou milissegundos; campos desconhecidos são preservados.
Leitura inválida levanta ValueError sem apagar ou substituir o arquivo.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile

from .config import arquivo_config

IDS_FABRICA = ("conversa", "computador", "oficina", "consultas", "memoria", "reuniao", "sistema", "resumo-manha", "pesquisa", "agente-remoto")
HABILIDADES_PADRAO = {"versao": 1, "habilidades": [], "desligadas": []}
HABILIDADES_FABRICA = [
    {"id": id_, "nome": nome, "quando": frases, "situacao": "capaz", "ligada": True}
    for id_, nome, frases in [
        ("conversa", "Conversa", ["que horas são?", "me explica ..."]),
        ("computador", "Computador", ["abre o YouTube", "o que está na minha tela?", "organiza as janelas"]),
        ("oficina", "Oficina", ["manda o Codex criar um teste no projeto", "como está a tarefa 3?", "aprova a tarefa 3"]),
        ("consultas", "Consultas", ["pede ao Claude pra ver as issues do Linear", "pergunta ao Codex o que tenho na agenda"]),
        ("memoria", "Memória", ["lembra que ...", "o que eu pedi pra você lembrar sobre ..."]),
        ("reuniao", "Reunião", ["acompanha a reunião", "encerra a reunião", "gera a ata"]),
        ("sistema", "Sistema", ["modo jogo", "volta do jogo", "bom dia, vamos começar o dia"]),
        ("resumo-manha", "Resumo da manhã", ["bom dia, qual é o resumo de hoje?", "me dá o resumo da manhã"]),
        ("pesquisa", "Pesquisa", ["pesquisa sobre ...", "busca informações sobre ..."]),
        ("agente-remoto", "Agente remoto", ["roda o agente remoto", "executa a tarefa remota"]),
    ]
]


def _objeto(valor, campos):
    if not isinstance(valor, dict):
        raise ValueError("Objeto inválido em habilidades.json")
    return valor


def _texto(valor):
    # \s inclui NEL e separadores de controle; BOM também conta como espaço, como no TS.
    return isinstance(valor, str) and bool(re.search(r"[^\s\ufeff]", valor))


def _tamanho_texto(valor: str) -> int:
    """Unidades UTF-16, como maxlength no HTML e String.length no TypeScript."""
    return len(valor.encode("utf-16-le", errors="surrogatepass")) // 2


def _data(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z", valor, re.ASCII):
        return False
    try:
        datetime.strptime(valor, "%Y-%m-%dT%H:%M:%S.%fZ" if "." in valor else "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def _validar_textos(h, exigir: bool) -> None:
    """Nome, quando e instrucoes: obrigatórios nas receitas; opcionais (se presentes, válidos) nos ajustes de fábrica."""
    def presente(campo):
        return exigir or campo in h
    quando = h.get("quando")
    if ((presente("nome") and not _texto(h.get("nome"))) or (presente("instrucoes") and not _texto(h.get("instrucoes")))
            or (presente("quando") and (not isinstance(quando, list) or not quando or not all(_texto(f) for f in quando)))):
        raise ValueError("Preencha nome, frases de exemplo e instruções")
    if "nome" in h and _tamanho_texto(h["nome"]) > 80:
        raise ValueError("Nome deve ter até 80 caracteres")
    if "quando" in h and len(h["quando"]) > 10:
        raise ValueError("Use até 10 frases de exemplo")
    if "quando" in h and any(_tamanho_texto(f) > 200 for f in h["quando"]):
        raise ValueError("Cada frase deve ter até 200 caracteres")
    if "instrucoes" in h and _tamanho_texto(h["instrucoes"]) > 4000:
        raise ValueError("Instruções devem ter até 4000 caracteres")


def validar_habilidades(raw) -> dict:
    """Valida e devolve cópia normalizada; desligadas ausente vira lista vazia."""
    obj = _objeto(raw, ("versao", "habilidades", "desligadas"))
    if isinstance(obj.get("versao"), bool) or obj.get("versao") != 1 or not isinstance(obj.get("habilidades"), list):
        raise ValueError("Versão ou lista de habilidades inválida")
    if len(obj["habilidades"]) > 200:
        raise ValueError("Cadastre até 200 habilidades")
    desligadas = obj.get("desligadas", [])
    if not isinstance(desligadas, list) or any(not isinstance(id_, str) or id_ not in IDS_FABRICA for id_ in desligadas) or len(set(desligadas)) != len(desligadas):
        raise ValueError("Lista de habilidades de fábrica desligadas inválida")
    ids = set(IDS_FABRICA)
    for bruto in obj["habilidades"]:
        h = _objeto(bruto, ("id", "nome", "quando", "instrucoes", "ligada", "situacao", "criada_em", "validada_em"))
        id_ = h.get("id")
        if not isinstance(id_, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", id_) or id_ in ids:
            raise ValueError("ID de habilidade inválido ou repetido")
        ids.add(id_)
        _validar_textos(h, exigir=True)
        if not isinstance(h.get("ligada"), bool) or h.get("situacao") not in ("treinada", "validada") or not _data(h.get("criada_em")):
            raise ValueError("Estado ou data de criação inválidos")
        if "validada_em" not in h or (h["validada_em"] is not None if h["situacao"] == "treinada" else not _data(h["validada_em"])):
            raise ValueError("Data de validação incompatível com a situação")
    if "fabrica" in obj:
        fabrica = obj["fabrica"]
        if not isinstance(fabrica, dict) or any(id_ not in IDS_FABRICA or not isinstance(a, dict) for id_, a in fabrica.items()):
            raise ValueError("Ajustes de fábrica inválidos")
        for ajuste in fabrica.values():
            _validar_textos(ajuste, exigir=False)
    return deepcopy({**obj, "desligadas": desligadas})


def fabrica_ligadas(cfg: dict) -> list[dict]:
    """Capacidades de fábrica personalizadas e ligadas, já com os ajustes aplicados sobre o padrão."""
    ajustes = cfg.get("fabrica", {})
    return [{**padrao, **ajustes[padrao["id"]]} for padrao in deepcopy(HABILIDADES_FABRICA)
            if padrao["id"] in ajustes and padrao["id"] not in cfg["desligadas"]]


def tem_ligadas(cfg: dict) -> bool:
    """Há algo que o agente deve consultar: receita do usuário ligada ou fábrica personalizada ligada."""
    return any(h["ligada"] for h in cfg["habilidades"]) or bool(fabrica_ligadas(cfg))


def caminho() -> Path:
    return arquivo_config("habilidades.json")


def ler_habilidades() -> dict:
    try:
        texto = caminho().read_text(encoding="utf-8")
    except FileNotFoundError:
        return deepcopy(HABILIDADES_PADRAO)
    return validar_habilidades(json.loads(texto))


def gravar_habilidades(valor: dict) -> None:
    """Valida antes de escrever e troca atomicamente, com temporário exclusivo."""
    cfg = validar_habilidades(valor)
    destino = caminho()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="habilidades.", suffix=".tmp", dir=destino.parent, delete=False) as arq:
            temporario = Path(arq.name)
            json.dump(cfg, arq, ensure_ascii=False, indent=2)
            arq.flush()
            os.fsync(arq.fileno())
        os.replace(temporario, destino)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
