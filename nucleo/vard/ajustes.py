"""Ajustes compartilhados pela tela e pelo MCP, sem acesso ao cofre.

Atualizações preservam campos que esta versão não conhece. A troca atômica usa
temporário exclusivo na mesma pasta e nunca substitui um documento inválido.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
import tomllib
from urllib.parse import urlsplit

import httpx
import tomli_w

from . import config, habilidades, programas

PROVEDORES_VOZ = ("propria", "openjarvis", "elevenlabs", "gemini")
PAINEIS_PADRAO = {"versao": 1, "provedores": [], "ativo": None, "reserva": None,
    "agentes": {a: {"padrao": "", "modelos": []} for a in ("claude", "codex", "opencode", "agy")}, "mcps": []}


def caminho_hud() -> Path:
    """Mesmo diretório do Tauri; o supervisor informa a pasta para builds de dev."""
    pasta = os.environ.get("VARD_HUD_CONFIG_DIR", "").strip()
    if pasta:
        return Path(pasta) / "hud.config.json"
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / "io.github.pauloroos.vard" / "hud.config.json"


def caminho(arquivo: str) -> Path:
    if arquivo == "hud":
        return caminho_hud()
    nomes = {"paineis": "paineis.json", "perfil": "perfil.json", "programas": "programas.toml", "habilidades": "habilidades.json"}
    if arquivo not in nomes:
        raise ValueError("Arquivo de configuração desconhecido")
    return config.arquivo_config(nomes[arquivo])


def _objeto(valor):
    if not isinstance(valor, dict):
        raise ValueError("A configuração deve ser um objeto")
    return valor


def validar_documento(arquivo: str, valor) -> dict:
    """Mesmo contrato de src/config/ajustes.ts e dos validadores da tela."""
    obj = deepcopy(_objeto(valor))
    if arquivo == "habilidades":
        return habilidades.validar_habilidades(obj)
    if arquivo == "hud":
        if "usar_openjarvis" in obj and not isinstance(obj["usar_openjarvis"], bool):
            raise ValueError("Usar OpenJarvis deve ser booleano")
        for chave in ("cor_elementos", "voz_motor", "voz_propria", "voz", "elevenlabs_voz", "gemini_voz", "voz_reserva_motor", "voz_reserva_id", "cerebro"):
            if chave in obj and not isinstance(obj[chave], str):
                raise ValueError("O ajuste deve ser texto")
        cor = obj.get("cor_elementos", "")
        if cor and not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
            raise ValueError("Use uma cor hexadecimal com seis dígitos")
        op = obj.get("opacidade_elementos", 1)
        if isinstance(op, bool) or not isinstance(op, (int, float)) or not math.isfinite(op) or not 0.2 <= op <= 1:
            raise ValueError("A opacidade deve ficar entre 0,2 e 1")
        for campo, validos in (("voz_provedor", PROVEDORES_VOZ), ("voz_reserva_provedor", (*PROVEDORES_VOZ, "nenhuma")), ("cerebro", ("openjarvis", "proprio"))):
            if campo in obj and obj[campo] not in validos:
                raise ValueError("Provedor ou cérebro inválido")
    elif arquivo == "perfil":
        if type(obj.get("versao")) not in (int, float) or obj["versao"] != 1:
            raise ValueError("Versão de perfil inválida")
        for campo in ("tom", "personalidade", "instrucoes", "sobre_usuario"):
            if campo in obj and not isinstance(obj[campo], str):
                raise ValueError("O campo do perfil deve ser texto")
            obj.setdefault(campo, "")
    elif arquivo == "programas":
        for campo in ("apelidos", "sites"):
            secao = _objeto(obj.get(campo, {}))
            if any(not isinstance(v, str) for v in secao.values()):
                raise ValueError("Os destinos dos programas e sites devem ser texto")
    elif arquivo == "paineis":
        if type(obj.get("versao")) not in (int, float) or obj["versao"] != 1:
            raise ValueError("Versão de painéis inválida")
        if not isinstance(obj.get("provedores"), list) or not isinstance(obj.get("mcps"), list):
            raise ValueError("Provedores e MCPs devem ser listas")
        for p in obj["provedores"]:
            _objeto(p)
            if any(not isinstance(p.get(c), str) for c in ("id", "nome", "tipo", "modelo")) or not p["id"] or not p["tipo"]:
                raise ValueError("Preencha os campos do provedor")
            if p["tipo"] in ("cli-claude", "cli-agy"):
                if p.get("url_base", "") != "" or "credencial_ref" in p:
                    raise ValueError("A CLI não aceita URL nem credencial")
                for c in ("yolo", "enxuto"):
                    if c in p and not isinstance(p[c], bool):
                        raise ValueError("Opção da CLI inválida")
                if "esforco" in p and not isinstance(p["esforco"], str):
                    raise ValueError("Esforço da CLI inválido")
                p.setdefault("url_base", "")
                p.setdefault("yolo", True)
                p.setdefault("enxuto", False)
            elif not isinstance(p.get("url_base"), str):
                raise ValueError("Preencha o endereço do provedor")
            if "credencial_ref" in p and not isinstance(p["credencial_ref"], str):
                raise ValueError("Referência de credencial inválida")
        for c in ("ativo", "reserva"):
            if c not in obj or (obj[c] is not None and not isinstance(obj[c], str)):
                raise ValueError("Escolha de provedor inválida")
        agentes = _objeto(obj.get("agentes"))
        for a in PAINEIS_PADRAO["agentes"]:
            e = _objeto(agentes.get(a))
            if not isinstance(e.get("padrao"), str) or not isinstance(e.get("modelos"), list) or any(not isinstance(m, str) for m in e["modelos"]):
                raise ValueError("Escolha de agente inválida")
        for m in obj["mcps"]:
            _objeto(m)
            if not isinstance(m.get("id"), str) or not m["id"] or not isinstance(m.get("nome"), str) or not isinstance(m.get("habilitado"), bool):
                raise ValueError("MCP inválido")
            if "command" in m:
                if not isinstance(m["command"], str) or not m["command"] or ("args" in m and (not isinstance(m["args"], list) or any(not isinstance(a, str) for a in m["args"]))):
                    raise ValueError("Comando MCP inválido")
            elif not isinstance(m.get("url"), str) or not m["url"]:
                raise ValueError("MCP precisa de comando ou URL")
            if "credencial_ref" in m and not isinstance(m["credencial_ref"], str):
                raise ValueError("Referência de credencial inválida")
    else:
        raise ValueError("Arquivo de configuração desconhecido")
    return obj


def ler_documento(arquivo: str) -> dict:
    if arquivo == "habilidades":
        return habilidades.ler_habilidades()
    try:
        texto = caminho(arquivo).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return deepcopy({"paineis": PAINEIS_PADRAO, "perfil": {"versao": 1}, "programas": {"apelidos": {}, "sites": {}}}.get(arquivo, {}))
    return validar_documento(arquivo, tomllib.loads(texto) if arquivo == "programas" else json.loads(texto))


def gravar_documento(arquivo: str, valor: dict) -> None:
    valor = validar_documento(arquivo, valor)
    if arquivo == "habilidades":
        habilidades.gravar_habilidades(valor)
        return
    alvo = caminho(arquivo)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=alvo.parent, prefix=alvo.stem + ".", suffix=".tmp", delete=False) as arq:
            tmp = Path(arq.name)
            arq.write(tomli_w.dumps(valor) if arquivo == "programas" else json.dumps(valor, ensure_ascii=False, indent=2))
            arq.flush()
            os.fsync(arq.fileno())
        os.replace(tmp, alvo)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


def mudar_aparencia(cor: str | None = None, opacidade: float | None = None) -> None:
    """Muda a cor, a opacidade ou as duas; o que não vier fica como está."""
    if cor is None and opacidade is None:
        raise ValueError("Diga a cor ou a opacidade a mudar.")
    cfg = ler_documento("hud")
    if cor is not None:
        cfg["cor_elementos"] = cor
    if opacidade is not None:
        cfg["opacidade_elementos"] = opacidade
    gravar_documento("hud", cfg)


def sem_segredos(valor):
    """Remove inclusive campos futuros sensíveis, sem consultar o cofre."""
    if isinstance(valor, dict):
        return {k: sem_segredos(v) for k, v in valor.items() if not re.search(r"chave|token|secret|senha|password|api.?key|credencial", k, re.I)}
    if isinstance(valor, list):
        return [sem_segredos(v) for v in valor]
    return valor


def recusar_segredos(valor) -> None:
    if sem_segredos(valor) != valor:
        raise ValueError("Cadastre a chave na tela de Configurações")


def cadastrar_provedor(provedor: dict) -> None:
    recusar_segredos(provedor)
    cfg = ler_documento("paineis")
    if any(p["id"] == provedor.get("id") for p in cfg["provedores"]):
        raise ValueError("Já existe um provedor com esse ID")
    cfg["provedores"].append(deepcopy(provedor))
    gravar_documento("paineis", cfg)


def editar_provedor(id: str, campos: dict) -> None:
    recusar_segredos(campos)
    if "id" in campos and campos["id"] != id:
        raise ValueError("O ID do provedor não pode mudar")
    cfg = ler_documento("paineis")
    p = next(p for p in cfg["provedores"] if p["id"] == id)
    p.update(campos)
    gravar_documento("paineis", cfg)


def remover_provedor(id: str) -> None:
    cfg = ler_documento("paineis")
    if not any(p["id"] == id for p in cfg["provedores"]):
        raise ValueError("Provedor não encontrado")
    cfg["provedores"] = [p for p in cfg["provedores"] if p["id"] != id]
    for campo in ("ativo", "reserva"):
        if cfg[campo] == id:
            cfg[campo] = None
    gravar_documento("paineis", cfg)


def escolher_quem_responde(ativo: str, reserva: str | None) -> None:
    cfg = ler_documento("paineis")
    ids = {p["id"] for p in cfg["provedores"]}
    if ativo != "openjarvis" and ativo not in ids or reserva is not None and reserva not in ids or ativo == reserva:
        raise ValueError("Escolha provedores cadastrados e diferentes")
    cfg.update(ativo=None if ativo == "openjarvis" else ativo, reserva=reserva)
    gravar_documento("paineis", cfg)
    hud = ler_documento("hud")
    hud["cerebro"] = "openjarvis" if ativo == "openjarvis" else "proprio"
    gravar_documento("hud", hud)


def escolher_voz(motor: str, principal: str, reserva: str = "") -> None:
    cfg = ler_documento("hud")
    provedor = motor if motor in PROVEDORES_VOZ else "propria"
    if motor not in (*PROVEDORES_VOZ, "kokoro", "edge", "piper", "xtts", ""):
        raise ValueError("Motor de voz desconhecido")
    campo = {"propria": "voz_propria", "openjarvis": "voz", "elevenlabs": "elevenlabs_voz", "gemini": "gemini_voz"}[provedor]
    cfg.update(voz_provedor=provedor, voz_motor=motor if provedor == "propria" else "", **{campo: principal},
        voz_reserva_provedor=provedor if reserva else "nenhuma", voz_reserva_motor=motor if provedor == "propria" else "", voz_reserva_id=reserva)
    gravar_documento("hud", cfg)


def listar_vozes() -> dict:
    recurso = Path(__file__).with_name("vozes.json")
    if not recurso.is_file():
        recurso = Path(__file__).resolve().parents[2] / "config/vozes.json"
    catalogo = json.loads(recurso.read_text(encoding="utf-8"))
    cadastradas = [p for p in ler_documento("paineis")["provedores"] if p["tipo"] in ("suad", "kokoro", "elevenlabs", "gemini", "fish")]
    return {"catalogo": catalogo, "cadastradas": cadastradas}


def listar_habilidades() -> list[dict]:
    return [h for h in habilidades.ler_habilidades()["habilidades"] if h["ligada"]]


def cadastrar_habilidade(campos: dict) -> None:
    cfg = habilidades.ler_habilidades()
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cfg["habilidades"].append({**campos, "situacao": "treinada", "criada_em": agora, "validada_em": None, "ligada": campos.get("ligada", True)})
    habilidades.gravar_habilidades(cfg)


def editar_habilidade(id: str, campos: dict) -> None:
    if set(campos) - {"nome", "quando", "instrucoes", "ligada"}:
        raise ValueError("Edite nome, exemplos, instruções ou ligada")
    cfg = habilidades.ler_habilidades()
    h = next(h for h in cfg["habilidades"] if h["id"] == id)
    h.update(campos)
    h.update(situacao="treinada", validada_em=None)
    habilidades.gravar_habilidades(cfg)


def excluir_habilidade(id: str) -> None:
    cfg = habilidades.ler_habilidades()
    if not any(h["id"] == id for h in cfg["habilidades"]):
        raise ValueError("Habilidade não encontrada")
    cfg["habilidades"] = [h for h in cfg["habilidades"] if h["id"] != id]
    habilidades.gravar_habilidades(cfg)


def marcar_habilidade_validada(id: str) -> None:
    cfg = habilidades.ler_habilidades()
    h = next(h for h in cfg["habilidades"] if h["id"] == id)
    h.update(situacao="validada", validada_em=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
    habilidades.gravar_habilidades(cfg)


def cadastrar_programa(nome: str, destino: str, site: bool = False) -> None:
    if not isinstance(nome, str) or not nome.strip() or not isinstance(destino, str) or not destino.strip():
        raise ValueError("Informe nome e destino")
    cfg = ler_documento("programas")
    cfg.setdefault("sites" if site else "apelidos", {})[programas._simples(nome)] = destino
    gravar_documento("programas", cfg)


def remover_programa(nome: str, site: bool = False) -> None:
    cfg = ler_documento("programas")
    chave = programas._simples(nome)
    secao = cfg.setdefault("sites" if site else "apelidos", {})
    if chave not in secao:
        raise ValueError(f"Não achei o programa {nome}")
    del secao[chave]
    gravar_documento("programas", cfg)


def http_local(metodo: str, rota: str, corpo: dict | None = None):
    """Instalação e teste ficam no processo do servidor, com autenticação local."""
    base = os.environ.get("VARD_NUCLEO_URL", "").strip() or ler_documento("hud").get("ponte_url", "http://127.0.0.1:4700")
    url = urlsplit(base)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1") or url.username or url.password:
        raise ValueError("O núcleo precisa de um endereço HTTP local")
    token = os.environ.get("VARD_TOKEN", "")
    with httpx.Client(timeout=15, trust_env=False) as cliente:
        resposta = cliente.request(metodo, base.rstrip("/") + rota, json=corpo,
            headers={"Authorization": "Bearer " + token} if token else {})
        resposta.raise_for_status()
        return resposta.json()
