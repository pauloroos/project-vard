"""T7 (0.9): importar instalação anterior sem alterar a origem.

Origem: pasta explícita escolhida pelo usuário (instalação antiga no estilo da
fusão: `config/*.toml`, personas, `instalacao.json`, HUD `hud.config.json` e
`segredos.toml`). A origem é só lida — prévia, aplicação e retorno nunca
escrevem nela (os testes conferem o hash antes/depois).

Destino: pastas ativas (`VARD_CONFIG`/`VARD_DADOS`, nunca o repositório).
Categorias com lista de campos permitida; a prévia mostra categorias e
conflitos, nunca chaves. Aplicar faz backup externo do destino, staging,
verificação e gravação atômica; falhar retorna ao destino anterior. Reverter
restaura o backup sem apagar dado novo de uso. Campos da HUD voltam no
resultado para o painel gravar pelos acessores dele; chaves da HUD antiga
não são importadas (vão pelo cofre, no painel).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import tomli_w

from vard import config as modulo_config
from vard import instalacao as modulo_instalacao
from vard import segredos as modulo_segredos

log = logging.getLogger(__name__)

SCHEMA = 1
CATEGORIAS = ("chamada", "voz", "cerebro", "persona", "config_toml", "segredos")
ESCOLHAS = ("importar", "manter")

#: Campos da HUD que a importação pode trazer (nada secreto; chaves ficam de fora).
HUD_CHAMADA = ("nome", "variantes", "usuario")
HUD_VOZ = ("voz", "velocidade", "idioma", "voz_provedor", "voz_propria")
#: Chaves que, se existirem na HUD antiga, viram aviso (vão pelo cofre, no painel).
HUD_CHAVES = ("elevenlabs_chave", "gemini_chave")
#: De instalacao.json só entram estes; caminhos da máquina antiga nunca.
INSTALACAO_IMPORTAVEIS = ("modelo", "contexto")
#: TOMLs que o núcleo realmente lê (verificado no código); o resto é ignorado com aviso.
TOML_CONHECIDOS = ("delegada", "manha", "memoria", "noticias", "oficina",
                   "programas", "relatorios", "remoto", "repos", "reuniao")
#: Arquivos de persona cobertos pela categoria persona.
PERSONA_ARQUIVOS = ("persona.md", "persona-ata.md", "persona-manha.md")
#: Seções de segredos.toml que a importação pode preencher (só o vazio do destino).
SEGREDOS_SECOES = ("omniroute", "lmstudio", "telegram", "ai_memory", "remoto", "coolify", "google")
#: Seção desconhecida com um destes nomes sugere conta OAuth: aviso próprio, sem importar.
OAUTH_SINAIS = ("oauth", "conta", "login", "cookie", "sessao", "session", "token")
#: Texto de TOML com um destes trechos sugere comando antigo: pede revisão no painel.
COMANDO_SINAIS = ("command", "cmd.exe", ".exe", ".ps1", ".bat", "powershell")

_PREVIAS: dict[str, dict] = {}
_PREVIAS_MAX = 32


class OrigemInvalida(ValueError):
    """Pasta de origem ausente, não é diretório ou é o destino ativo."""


class PreviaDesconhecida(KeyError):
    """previa_id sem registro (reiniciou o núcleo ou id inventado)."""


class PreviaObsoleta(ValueError):
    """A origem mudou depois da prévia: refaça a prévia antes de aplicar."""


class EscolhaInvalida(ValueError):
    """Categoria desconhecida ou valor fora de importar/manter."""


class OperacaoDesconhecida(KeyError):
    """operacao_id sem manifesto de retorno."""


class FalhaAplicacao(RuntimeError):
    """Gravação falhou ou verificação não confirmou: destino restaurado."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha_arquivo(arq: Path) -> str:
    return hashlib.sha256(arq.read_bytes()).hexdigest()


def _pasta_retorno() -> Path:
    return modulo_config.pasta_dados() / "importacao-retorno"


def _resolver_origem(origem: str | Path) -> Path:
    if origem is None or (isinstance(origem, str) and not origem.strip()):
        raise OrigemInvalida("origem vazia")
    candidata = Path(origem).expanduser()
    try:
        resolvida = candidata.resolve()
    except OSError as exc:
        raise OrigemInvalida(f"origem inválida: {exc}") from exc
    if not resolvida.is_dir():
        raise OrigemInvalida("origem não é uma pasta")
    return resolvida


def _e_ativo(caminho: Path) -> bool:
    """Origem igual ao destino ativo: importar seria no-op (não toca em nada)."""
    try:
        ativos = {modulo_config.pasta_config().resolve(), modulo_config.pasta_dados().resolve()}
    except OSError:
        return False
    return caminho in ativos


def _pasta_cfg(origem: Path) -> Path:
    """TOMLs/personas ficam em <origem>/config, ou na própria origem se ela já é a config."""
    sub = origem / "config"
    return sub if sub.is_dir() else origem


def _impressao(origem: Path) -> dict[str, str]:
    """SHA-256 dos arquivos conhecidos encontrados (amarra prévia/aplicar)."""
    mapa: dict[str, str] = {}
    for rel in _arquivos_conhecidos(origem):
        try:
            mapa[rel] = _sha_arquivo(origem / rel)
        except OSError:
            continue
    return mapa


def _arquivos_conhecidos(origem: Path) -> list[str]:
    achados: list[str] = []
    for nome in ("hud.config.json", "segredos.toml", "instalacao.json"):
        if (origem / nome).is_file():
            achados.append(nome)
    cfg = _pasta_cfg(origem)
    for nome in [*(f"{base}.toml" for base in TOML_CONHECIDOS), "perfil.json", *PERSONA_ARQUIVOS]:
        try:
            rel = (cfg / nome).relative_to(origem)
        except ValueError:
            continue
        if (cfg / nome).is_file():
            achados.append(rel.as_posix())
    return sorted(achados)


def _ler_json(arq: Path) -> dict | None:
    """JSON objeto, ou None se ausente; levanta ValueError se inválido."""
    try:
        bruto = arq.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{arq.name} ilegível") from exc
    try:
        dados = json.loads(bruto)
    except ValueError as exc:
        raise ValueError(f"{arq.name} inválido") from exc
    if not isinstance(dados, dict):
        raise ValueError(f"{arq.name} inválido")
    return dados


def _ler_toml(arq: Path) -> dict:
    try:
        with arq.open("rb") as f:
            dados = tomllib.load(f)
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ValueError(f"{arq.name} inválido") from exc
    return dados if isinstance(dados, dict) else {}


def _resumo(texto: str, limite: int = 120) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[:limite] + "…"


def _hud_origem(origem: Path) -> tuple[dict | None, str | None]:
    """HUD da origem: (dados, erro). Erro só quando o arquivo existe e não abre."""
    arq = origem / "hud.config.json"
    if not arq.is_file():
        return None, None
    try:
        return _ler_json(arq), None
    except ValueError:
        return None, "hud.config.json inválido"


def _hud_campo(origem_val, destino_val) -> tuple[bool, bool]:
    """(tem_origem, conflito): conflito só quando os dois lados têm e diferem."""
    tem = origem_val is not None and origem_val != "" and origem_val != []
    if not tem:
        return False, False
    if destino_val is None:
        return True, False
    return True, _normalizar(origem_val) != _normalizar(destino_val)


def _normalizar(valor):
    if isinstance(valor, list):
        return [str(v).strip().lower() for v in valor if str(v).strip()]
    if isinstance(valor, (int, float)):
        return valor
    return str(valor or "").strip()


def _categoria(base: str, titulo: str, estado: str) -> dict:
    return {"id": base, "titulo": titulo, "estado": estado, "itens": [], "avisos": []}


def previa(origem: str | Path, hud_atual: dict | None = None) -> dict:
    """Lê a origem (sem modificá-la) e devolve categorias/conflitos, sem chaves.

    `hud_atual`: HUD ativa (só campos comuns; segredos nunca entram aqui) para
    marcar conflitos de nome/voz. Sem ela, o destino desses itens fica vazio.
    """
    caminho = _resolver_origem(origem)
    if _e_ativo(caminho):
        registro = {"schema": SCHEMA, "previa_id": uuid.uuid4().hex, "origem": str(caminho),
                    "ja_ativo": True, "categorias": [], "avisos": ["origem é o destino ativo: nada a importar"],
                    "criado_em": _agora(), "_impressao": {}, "_hud_atual": {}}
        _guardar_previa(registro)
        return _publicar_previa(registro)
    hud = dict(hud_atual or {})
    registro = {"schema": SCHEMA, "previa_id": uuid.uuid4().hex, "origem": str(caminho),
                "ja_ativo": False, "categorias": [], "avisos": [],
                "criado_em": _agora(), "_impressao": _impressao(caminho), "_hud_atual": hud}
    _previa_chamada_voz(registro, caminho, hud)
    _previa_cerebro(registro, caminho)
    _previa_persona(registro, caminho)
    _previa_config_toml(registro, caminho)
    _previa_segredos(registro, caminho)
    _guardar_previa(registro)
    log.info("importacao prévia %s origem=%s categorias=%d", registro["previa_id"][:8],
             caminho, len(registro["categorias"]))
    return _publicar_previa(registro)


def _guardar_previa(registro: dict) -> None:
    _PREVIAS[registro["previa_id"]] = registro
    while len(_PREVIAS) > _PREVIAS_MAX:
        velha = min(_PREVIAS.values(), key=lambda r: r["criado_em"])
        del _PREVIAS[velha["previa_id"]]


def _publicar_previa(registro: dict) -> dict:
    saida = {k: v for k, v in registro.items() if not k.startswith("_")}
    return copy.deepcopy(saida)


def _previa_chamada_voz(registro: dict, origem: Path, hud: dict) -> None:
    dados, erro = _hud_origem(origem)
    for base, titulo, campos in (("chamada", "Nome de chamada", HUD_CHAMADA),
                                 ("voz", "Voz e dispositivos", HUD_VOZ)):
        cat = _categoria(base, titulo, "ausente")
        if erro:
            cat["estado"] = "erro"
            cat["avisos"].append(erro)
        elif dados is not None:
            itens = []
            for campo in campos:
                tem, conflito = _hud_campo(dados.get(campo), hud.get(campo))
                if tem:
                    itens.append({"campo": campo, "origem": dados.get(campo),
                                  "destino": hud.get(campo), "conflito": conflito})
            if itens:
                todos_iguais = all(
                    i["destino"] is not None and _normalizar(i["origem"]) == _normalizar(i["destino"])
                    for i in itens)
                cat["estado"] = "igual" if todos_iguais else "pronta"
                cat["itens"] = itens
        registro["categorias"].append(cat)
    if dados is not None and any(_tem_valor(dados.get(c)) for c in HUD_CHAVES):
        registro["avisos"].append(
            "A HUD antiga tem chaves: grave pelo painel (cofre); chaves não são importadas")


def _previa_cerebro(registro: dict, origem: Path) -> None:
    cat = _categoria("cerebro", "Cérebro local", "ausente")
    arq = origem / "instalacao.json"
    if arq.is_file():
        try:
            dados = _ler_json(arq) or {}
        except ValueError:
            cat["estado"] = "erro"
            cat["avisos"].append("instalacao.json inválido")
            registro["categorias"].append(cat)
            return
        destino = modulo_instalacao.ler()
        for campo in INSTALACAO_IMPORTAVEIS:
            if campo in dados and dados[campo] not in (None, ""):
                d = destino.get(campo)
                cat["itens"].append({"campo": campo, "origem": dados[campo],
                                    "destino": d, "conflito": d not in (None, "", 0) and d != dados[campo]})
        caminhos = [k for k in ("raiz_codigo", "openjarvis_src", "openjarvis_home") if dados.get(k)]
        if caminhos:
            cat["avisos"].append("caminhos da máquina antiga ignorados: a raiz ativa não muda")
        cat["estado"] = "pronta" if cat["itens"] else "ausente"
        if cat["estado"] == "pronta" and all(
                i["destino"] not in (None, "", 0) and i["destino"] == i["origem"] for i in cat["itens"]):
            cat["estado"] = "igual"
    registro["categorias"].append(cat)


def _previa_persona(registro: dict, origem: Path) -> None:
    cat = _categoria("persona", "Persona", "ausente")
    cfg = _pasta_cfg(origem)
    origem_perfil: dict = {}
    try:
        if (cfg / "perfil.json").is_file():
            origem_perfil = _ler_json(cfg / "perfil.json") or {}
        elif (cfg / "persona.md").is_file():
            origem_perfil = {"instrucoes": (cfg / "persona.md").read_text(encoding="utf-8")}
    except ValueError:
        cat["estado"] = "erro"
        cat["avisos"].append("perfil.json inválido")
    except (OSError, UnicodeDecodeError):
        cat["estado"] = "erro"
        cat["avisos"].append("persona ilegível")
    if cat["estado"] != "erro" and origem_perfil:
        from vard import perfil as modulo_perfil
        atual = modulo_perfil.ler()
        destino = {"tom": atual.tom, "personalidade": atual.personalidade,
                   "instrucoes": atual.instrucoes, "sobre_usuario": atual.sobre_usuario}
        for campo in ("tom", "personalidade", "instrucoes", "sobre_usuario"):
            o = str(origem_perfil.get(campo) or "")
            if o.strip():
                d = destino.get(campo, "")
                cat["itens"].append({"campo": campo, "origem": o,
                                    "destino": d, "conflito": bool(d.strip()) and d != o})
        if cat["itens"]:
            def _item_ok(i: dict) -> bool:
                if i.get("arquivo"):
                    return i["destino"] is not None and not i["conflito"]
                cheio = str(origem_perfil.get(i["campo"]) or "")
                return bool(cheio.strip()) and i["destino"] == cheio
            cat["estado"] = "igual" if all(_item_ok(i) for i in cat["itens"]) else "pronta"
    for nome in PERSONA_ARQUIVOS:
        if nome == "persona.md" and (cfg / "perfil.json").is_file():
            continue  # perfil.json manda; a md legada ao lado não duplica
        if (cfg / nome).is_file():
            try:
                texto = (cfg / nome).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                cat["avisos"].append(f"{nome} ilegível")
                continue
            alvo = modulo_config.arquivo_config(nome)
            existe = alvo.is_file()
            igual = existe and alvo.read_text(encoding="utf-8") == texto
            cat["itens"].append({"campo": nome, "origem": _resumo(texto),
                                "destino": _resumo(alvo.read_text(encoding="utf-8")) if existe else None,
                                "conflito": existe and not igual, "arquivo": True})
            if cat["estado"] == "ausente":
                cat["estado"] = "igual" if igual else "pronta"
    registro["categorias"].append(cat)


def _previa_config_toml(registro: dict, origem: Path) -> None:
    cat = _categoria("config_toml", "Configurações", "ausente")
    cfg = _pasta_cfg(origem)
    achados = erros = 0
    for base in TOML_CONHECIDOS:
        nome = f"{base}.toml"
        arq = cfg / nome
        if not arq.is_file():
            continue
        achados += 1
        try:
            texto = arq.read_text(encoding="utf-8")
            _ler_toml(arq)
        except ValueError:
            erros += 1
            cat["itens"].append({"campo": nome, "estado": "erro", "conflito": False,
                                "aviso": f"{nome} inválido: ignorado"})
            continue
        except (OSError, UnicodeDecodeError):
            erros += 1
            cat["itens"].append({"campo": nome, "estado": "erro", "conflito": False,
                                "aviso": f"{nome} ilegível: ignorado"})
            continue
        alvo = modulo_config.arquivo_config(nome)
        existe = alvo.is_file()
        conflito = existe and alvo.read_bytes() != arq.read_bytes()
        cat["itens"].append({"campo": nome, "estado": "pronta", "conflito": conflito})
        baixa = texto.lower()
        if any(s in baixa for s in COMANDO_SINAIS):
            cat["avisos"].append(f"{nome} cita programa antigo: revise no painel antes de usar")
    if achados:
        cat["estado"] = "erro" if erros == achados else "pronta"
        if cat["estado"] == "pronta" and not any(i.get("conflito") for i in cat["itens"] if i.get("estado") == "pronta"):
            prontas = [i for i in cat["itens"] if i.get("estado") == "pronta"]
            if prontas and all((modulo_config.arquivo_config(i["campo"]).is_file()) for i in prontas):
                cat["estado"] = "igual"
    try:
        todos = sorted(p.name for p in cfg.glob("*.toml") if p.is_file())
    except OSError:
        todos = []
    for nome in todos:
        if nome[:-5] not in TOML_CONHECIDOS:
            cat["avisos"].append(f"{nome} ignorado: formato desconhecido, não importado")
    registro["categorias"].append(cat)


def _tem_valor(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, dict):
        return any(_tem_valor(v) for v in valor.values())
    if isinstance(valor, list):
        return bool(valor)
    return True


def _previa_segredos(registro: dict, origem: Path) -> None:
    cat = _categoria("segredos", "Segredos", "ausente")
    arq = origem / "segredos.toml"
    if arq.is_file():
        try:
            dados = _ler_toml(arq)
        except ValueError:
            cat["estado"] = "erro"
            cat["avisos"].append("segredos.toml inválido")
            registro["categorias"].append(cat)
            return
        try:
            destino = modulo_segredos.carregar()
        except (FileNotFoundError, ValueError, OSError):
            destino = {}
        for secao in SEGREDOS_SECOES:
            bloco = dados.get(secao)
            if not isinstance(bloco, dict) or not _tem_valor(bloco):
                continue
            d = destino.get(secao)
            destino_tem = isinstance(d, dict) and _tem_valor(d)
            conflito = bool(destino_tem and d != bloco)
            cat["itens"].append({"campo": secao, "origem_tem": True,
                                "destino_tem": destino_tem, "conflito": conflito})
        for secao in dados:
            if secao in SEGREDOS_SECOES:
                continue
            baixa = str(secao).lower()
            if any(s in baixa for s in OAUTH_SINAIS):
                registro["avisos"].append(
                    f"conta {secao} ignorada: OAuth e logins ficam na máquina antiga")
            else:
                cat["avisos"].append(f"seção {secao} ignorada: desconhecida, não importada")
        cat["estado"] = "pronta" if cat["itens"] else "ausente"
        if cat["estado"] == "pronta" and not any(i["conflito"] for i in cat["itens"]):
            # Sem conflito só quando o destino já tem tudo: senão ainda há o que preencher.
            _, faltam = modulo_segredos.mesclar_novos(destino, dados, SEGREDOS_SECOES)
            if not faltam:
                cat["estado"] = "igual"
    registro["categorias"].append(cat)


def aplicar(previa_id: str, escolhas: dict | None = None, hud_atual: dict | None = None) -> dict:
    """Aplica a prévia identificada; rejeita origem alterada depois dela.

    `escolhas`: categoria → importar|manter (ausente = manter, o conservador).
    `hud_atual`: HUD ativa atual (atualiza o retrato da prévia; sem ela vale o
    da prévia). O que o painel gravar a partir do `hud` devolvido conta como
    aplicado: repetir a mesma chamada é idempotente.
    Só a prévia identificada vale; origem alterada levanta PreviaObsoleta e
    nada é escrito. Falha no meio restaura o destino e levanta FalhaAplicacao.
    """
    registro = _PREVIAS.get(previa_id or "")
    if registro is None:
        raise PreviaDesconhecida(previa_id or "")
    if isinstance(hud_atual, dict):
        registro["_hud_atual"] = dict(hud_atual)
    escolhas = dict(escolhas or {})
    for cat_id, valor in escolhas.items():
        if cat_id not in CATEGORIAS:
            raise EscolhaInvalida(f"categoria desconhecida: {cat_id}")
        if valor not in ESCOLHAS:
            raise EscolhaInvalida(f"escolha inválida para {cat_id}: {valor}")
    if registro["ja_ativo"]:
        return {"ok": True, "previa_id": previa_id, "operacao_id": None,
                "aplicadas": [], "inalteradas": [], "hud": None, "avisos": registro["avisos"]}
    origem = Path(registro["origem"])
    _resolver_origem(origem)
    if _impressao(origem) != registro["_impressao"]:
        raise PreviaObsoleta("origem alterada depois da prévia")
    por_id = {c["id"]: c for c in registro["categorias"]}
    plano = {cid: escolhas.get(cid, "manter") for cid in CATEGORIAS if cid in por_id}
    operacao_id = uuid.uuid4().hex
    backup = _pasta_retorno() / operacao_id
    arquivos: list[dict] = []
    hud_aplicado: dict = {}
    aplicadas: list[str] = []
    inalteradas: list[str] = []
    avisos: list[str] = []
    try:
        for cid, escolha in plano.items():
            if escolha != "importar" or por_id[cid]["estado"] in ("ausente", "igual", "erro"):
                if escolha == "importar" and por_id[cid]["estado"] in ("igual",):
                    inalteradas.append(cid)
                continue
            if cid in ("chamada", "voz"):
                mudancas = _aplicar_hud(registro, cid)
                if mudancas:
                    hud_aplicado.update(mudancas)
                    aplicadas.append(cid)
                else:
                    inalteradas.append(cid)
            elif cid == "cerebro":
                if _aplicar_cerebro(registro, origem, backup, arquivos):
                    aplicadas.append(cid)
                else:
                    inalteradas.append(cid)
            elif cid == "persona":
                if _aplicar_persona(registro, origem, backup, arquivos):
                    aplicadas.append(cid)
                else:
                    inalteradas.append(cid)
            elif cid == "config_toml":
                feito, pulados = _aplicar_config_toml(registro, origem, backup, arquivos)
                if feito:
                    aplicadas.append(cid)
                else:
                    inalteradas.append(cid)
                avisos.extend(pulados)
            elif cid == "segredos":
                if _aplicar_segredos(registro, origem, backup, arquivos):
                    aplicadas.append(cid)
                else:
                    inalteradas.append(cid)
        _verificar_aplicacao(arquivos)
    except FalhaAplicacao:
        _restaurar(backup, arquivos)
        _remover_backup(backup)
        raise
    except OSError as exc:
        _restaurar(backup, arquivos)
        _remover_backup(backup)
        raise FalhaAplicacao(f"gravação falhou: {exc}") from exc
    if not aplicadas and not hud_aplicado:
        _remover_backup(backup)
        return {"ok": True, "previa_id": previa_id, "operacao_id": None,
                "aplicadas": [], "inalteradas": inalteradas, "hud": None, "avisos": avisos}
    manifesto = {"operacao_id": operacao_id, "previa_id": previa_id, "origem": str(origem),
                 "escolhas": plano, "aplicadas": aplicadas, "arquivos": arquivos,
                 "hud_anterior": registro["_hud_atual"], "hud_aplicado": hud_aplicado,
                 "criado_em": _agora(), "revertida_em": None}
    backup.mkdir(parents=True, exist_ok=True)
    _gravar_atomico(backup / "retorno.json",
                    json.dumps(manifesto, ensure_ascii=False, indent=2).encode("utf-8"))
    hud_saida = {**registro["_hud_atual"], **hud_aplicado} if hud_aplicado else None
    if hud_aplicado:
        registro["_hud_atual"].update(hud_aplicado)  # repetir a mesma chamada não reaplica
    log.info("importacao aplicou %s categorias=%s", operacao_id[:8], aplicadas)
    return {"ok": True, "previa_id": previa_id, "operacao_id": operacao_id,
            "aplicadas": aplicadas, "inalteradas": inalteradas,
            "hud": hud_saida, "avisos": avisos}


def _aplicar_hud(registro: dict, cid: str) -> dict:
    """Campos da HUD: voltam no resultado para o painel gravar (o núcleo não grava HUD)."""
    campos = HUD_CHAMADA if cid == "chamada" else HUD_VOZ
    cat = next(c for c in registro["categorias"] if c["id"] == cid)
    mudancas = {}
    for item in cat["itens"]:
        if item["campo"] in campos and item.get("origem") not in (None, "", []):
            atual = registro["_hud_atual"].get(item["campo"])
            if _normalizar(item["origem"]) != _normalizar(atual):
                mudancas[item["campo"]] = item["origem"]
    return mudancas


def _aplicar_cerebro(registro: dict, origem: Path, backup: Path, arquivos: list) -> bool:
    try:
        dados = _ler_json(origem / "instalacao.json") or {}
    except ValueError:
        return False
    atual = modulo_instalacao.ler()
    novos = {c: dados[c] for c in INSTALACAO_IMPORTAVEIS
             if dados.get(c) not in (None, "") and dados.get(c) != atual.get(c)}
    if not novos:
        return False
    destino = modulo_instalacao.arquivo()
    _copiar_backup(destino, backup, arquivos)
    saida = {**atual, **novos}
    _gravar_atomico(destino, json.dumps(saida, ensure_ascii=False, indent=2).encode("utf-8"))
    _registrar_escrita(destino, backup, arquivos)
    return True


def _aplicar_persona(registro: dict, origem: Path, backup: Path, arquivos: list) -> bool:
    from vard import perfil as modulo_perfil
    cfg = _pasta_cfg(origem)
    fez = False
    campos = [i for i in next(c for c in registro["categorias"] if c["id"] == "persona")["itens"]
              if not i.get("arquivo")]
    if campos:
        origem_perfil: dict = {}
        if (cfg / "perfil.json").is_file():
            origem_perfil = _ler_json(cfg / "perfil.json") or {}
        elif (cfg / "persona.md").is_file():
            origem_perfil = {"instrucoes": (cfg / "persona.md").read_text(encoding="utf-8")}
        atual = modulo_perfil.ler()
        novo = modulo_perfil.Perfil(
            tom=str(origem_perfil.get("tom") or "") or atual.tom,
            personalidade=str(origem_perfil.get("personalidade") or "") or atual.personalidade,
            instrucoes=str(origem_perfil.get("instrucoes") or "") or atual.instrucoes,
            sobre_usuario=str(origem_perfil.get("sobre_usuario") or "") or atual.sobre_usuario,
        )
        atual_dict = {"tom": atual.tom, "personalidade": atual.personalidade,
                      "instrucoes": atual.instrucoes, "sobre_usuario": atual.sobre_usuario}
        novo_dict = {"tom": novo.tom, "personalidade": novo.personalidade,
                     "instrucoes": novo.instrucoes, "sobre_usuario": novo.sobre_usuario}
        if novo_dict != atual_dict:
            destino = modulo_perfil.caminho()
            _copiar_backup(destino, backup, arquivos)
            modulo_perfil.gravar(novo)
            _registrar_escrita(destino, backup, arquivos)
            fez = True
    for item in next(c for c in registro["categorias"] if c["id"] == "persona")["itens"]:
        if not item.get("arquivo"):
            continue
        src = cfg / item["campo"]
        dst = modulo_config.arquivo_config(item["campo"])
        if _copiar_arquivo(src, dst, backup, arquivos):
            fez = True
    return fez


def _aplicar_config_toml(registro: dict, origem: Path, backup: Path, arquivos: list) -> tuple[bool, list[str]]:
    cfg = _pasta_cfg(origem)
    cat = next(c for c in registro["categorias"] if c["id"] == "config_toml")
    fez = False
    pulados: list[str] = []
    for item in cat["itens"]:
        if item.get("estado") != "pronta":
            pulados.append(item.get("aviso", f"{item['campo']} inválido: ignorado"))
            continue
        if _copiar_arquivo(cfg / item["campo"], modulo_config.arquivo_config(item["campo"]),
                           backup, arquivos):
            fez = True
    return fez, pulados


def _aplicar_segredos(registro: dict, origem: Path, backup: Path, arquivos: list) -> bool:
    try:
        dados = _ler_toml(origem / "segredos.toml")
    except ValueError:
        return False
    try:
        destino_atual = modulo_segredos.carregar()
    except (FileNotFoundError, ValueError, OSError):
        destino_atual = {}
    mesclado, preenchidos = modulo_segredos.mesclar_novos(destino_atual, dados, SEGREDOS_SECOES)
    if not preenchidos:
        return False
    destino = modulo_config.arquivo_segredos()
    _copiar_backup(destino, backup, arquivos)
    _gravar_atomico(destino, tomli_w.dumps(mesclado).encode("utf-8"))
    _registrar_escrita(destino, backup, arquivos)
    # Confirma a leitura pelo armazenamento vigente antes de concluir.
    try:
        relido = modulo_segredos.carregar(destino)
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise FalhaAplicacao(f"verificação dos segredos falhou: {exc}") from exc
    for secao, chaves in preenchidos.items():
        for chave in chaves:
            if "." in chave:
                parte, sub = chave.split(".", 1)
                obtido = (relido.get(secao) or {}).get(parte, {})
                esperado = ((mesclado.get(secao) or {}).get(parte) or {}).get(sub)
                ok = isinstance(obtido, dict) and obtido.get(sub) == esperado
            else:
                ok = (relido.get(secao) or {}).get(chave) == (mesclado.get(secao) or {}).get(chave)
            if not ok:
                raise FalhaAplicacao(f"verificação dos segredos falhou em {secao}")
    return True


def _copiar_backup(destino: Path, backup: Path, arquivos: list) -> None:
    for reg in arquivos:
        if reg["destino"] == str(destino):
            return
    if destino.is_file():
        backup.mkdir(parents=True, exist_ok=True)
        nome = f"{len(arquivos):02d}-{destino.name}.bak"
        (backup / nome).write_bytes(destino.read_bytes())
        arquivos.append({"destino": str(destino), "backup": nome, "tinha_antes": True,
                         "sha_antes": _sha_arquivo(destino), "sha_depois": None})
    else:
        arquivos.append({"destino": str(destino), "backup": None, "tinha_antes": False,
                         "sha_antes": None, "sha_depois": None})


def _registrar_escrita(destino: Path, backup: Path, arquivos: list) -> None:
    for reg in arquivos:
        if reg["destino"] == str(destino):
            try:
                reg["sha_depois"] = _sha_arquivo(destino)
            except OSError:
                reg["sha_depois"] = None
            return
    _copiar_backup(destino, backup, arquivos)
    _registrar_escrita(destino, backup, arquivos)


def _copiar_arquivo(src: Path, dst: Path, backup: Path, arquivos: list) -> bool:
    try:
        conteudo = src.read_bytes()
    except OSError:
        return False
    if dst.is_file() and dst.read_bytes() == conteudo:
        return False
    _copiar_backup(dst, backup, arquivos)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _gravar_atomico(dst, conteudo)
    _registrar_escrita(dst, backup, arquivos)
    return True


def _gravar_atomico(destino: Path, conteudo: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.parent / f"{destino.name}.tmp"
    try:
        tmp.write_bytes(conteudo)
        os.replace(tmp, destino)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _verificar_aplicacao(arquivos: list) -> None:
    for reg in arquivos:
        if reg["sha_depois"] is None and reg["backup"] is not None:
            try:
                reg["sha_depois"] = _sha_arquivo(Path(reg["destino"]))
            except OSError as exc:
                raise FalhaAplicacao(f"verificação falhou em {reg['destino']}: {exc}") from exc


def _restaurar(backup: Path, arquivos: list) -> None:
    for reg in reversed(arquivos):
        destino = Path(reg["destino"])
        try:
            if reg["tinha_antes"] and reg["backup"]:
                _gravar_atomico(destino, (backup / reg["backup"]).read_bytes())
            elif not reg["tinha_antes"] and destino.is_file():
                destino.unlink()
        except OSError:
            log.warning("importacao: retorno parcial em %s", destino)


def _remover_backup(backup: Path) -> None:
    try:
        if backup.is_dir():
            for arq in sorted(backup.iterdir()):
                arq.unlink()
            backup.rmdir()
    except OSError:
        pass


def reverter(operacao_id: str) -> dict:
    """Restaura o destino do manifesto; não apaga dado novo de uso.

    Arquivo criado pela importação e alterado depois é mantido (com aviso);
    o resto volta ao backup. Reverter duas vezes é no-op.
    """
    manifesto_arq = _pasta_retorno() / (operacao_id or "") / "retorno.json"
    try:
        manifesto = json.loads(manifesto_arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise OperacaoDesconhecida(operacao_id or "") from None
    if not isinstance(manifesto, dict) or manifesto.get("operacao_id") != operacao_id:
        raise OperacaoDesconhecida(operacao_id or "")
    if manifesto.get("revertida_em"):
        return {"ok": True, "operacao_id": operacao_id, "restaurados": [],
                "mantidos": [], "avisos": ["já revertida"], "hud_anterior": manifesto.get("hud_anterior")}
    backup = manifesto_arq.parent
    restaurados: list[str] = []
    mantidos: list[str] = []
    avisos: list[str] = []
    for reg in manifesto.get("arquivos", []):
        destino = Path(reg["destino"])
        nome = destino.name
        if reg.get("tinha_antes") and reg.get("backup"):
            try:
                _gravar_atomico(destino, (backup / reg["backup"]).read_bytes())
                restaurados.append(nome)
            except OSError as exc:
                avisos.append(f"{nome} não voltou: {exc}")
        elif not reg.get("tinha_antes"):
            if not destino.is_file():
                continue
            atual = _sha_arquivo(destino)
            if atual == reg.get("sha_depois"):
                try:
                    destino.unlink()
                    restaurados.append(nome)
                except OSError as exc:
                    avisos.append(f"{nome} não saiu: {exc}")
            else:
                mantidos.append(nome)
                avisos.append(f"{nome} alterado depois da importação: mantido")
    manifesto["revertida_em"] = _agora()
    _gravar_atomico(manifesto_arq,
                    json.dumps(manifesto, ensure_ascii=False, indent=2).encode("utf-8"))
    log.info("importacao reverteu %s restaurados=%d", operacao_id[:8], len(restaurados))
    return {"ok": True, "operacao_id": operacao_id, "restaurados": restaurados,
            "mantidos": mantidos, "avisos": avisos,
            "hud_anterior": manifesto.get("hud_anterior")}
