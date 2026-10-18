"""Elementos clicáveis de uma janela pela UI Automation do Windows (pacote `uiautomation`).

Tudo que é COM roda numa única thread dedicada (a mesa chama as ferramentas em threads variadas e
os objetos da UI Automation não podem trocar de thread). A última lista de cada janela fica em
memória para `clicar_elemento("e3")`. Nunca lê o valor de campos: senha nunca sai daqui.
"""
from __future__ import annotations

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TempoEsgotado
from dataclasses import dataclass
from typing import Any, Callable

from vard.monitores import Retangulo

LIMITE_ELEMENTOS = 40
LIMITE_NOME = 80
LIMITE_VISITADOS = 15000          # uma página do YouTube passa de 5 mil nós
LIMITE_PROFUNDIDADE = 60
LIMITE_SEGUNDOS = 10.0
TEMPO_RESPOSTA = 20.0

CLICAVEIS = {
    "ButtonControl": "Botão", "HyperlinkControl": "Link", "MenuItemControl": "Menu", "TabItemControl": "Aba",
    "ListItemControl": "Item", "TreeItemControl": "Item", "CheckBoxControl": "Caixa", "RadioButtonControl": "Opção",
    "ComboBoxControl": "Lista", "EditControl": "Campo", "SplitButtonControl": "Botão", "DataItemControl": "Item",
    "MenuBarControl": "Menu", "ImageControl": "Imagem",
}
ID_CURTO = re.compile(r"^e(\d+)$", re.IGNORECASE)


@dataclass
class Elemento:
    id: str
    nome: str
    tipo: str
    ret: Retangulo
    senha: bool = False
    controle: Any = None           # objeto da UI Automation (só vale na thread dedicada)

    def linha(self) -> str:
        r = self.ret
        nome = self.nome if len(self.nome) <= LIMITE_NOME else self.nome[: LIMITE_NOME - 1] + "…"
        extra = " (campo de senha)" if self.senha else ""
        return f"- {self.id} {self.tipo} \"{nome}\"{extra} [{r.x},{r.y} {r.largura}x{r.altura}]"


def _simples(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().strip().lower()


# --- Thread dedicada ---------------------------------------------------------------------------

_EXECUTOR: ThreadPoolExecutor | None = None


def _iniciar_thread() -> None:
    from vard import monitores

    monitores.ativar_dpi()   # antes do import: o uiautomation tentaria só o DPI por monitor v1
    import uiautomation

    uiautomation.InitializeUIAutomationInCurrentThread()


def _executar(fn: Callable[[], Any]) -> Any:
    """Roda `fn` na thread da UI Automation e espera a resposta (com limite de tempo)."""
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vard-uia", initializer=_iniciar_thread)
    try:
        return _EXECUTOR.submit(fn).result(timeout=TEMPO_RESPOSTA)
    except TempoEsgotado:
        raise RuntimeError("a janela demorou demais para responder à UI Automation") from None


def _raiz(hwnd: int):
    import uiautomation

    return uiautomation.ControlFromHandle(hwnd)


# --- Leitura -----------------------------------------------------------------------------------

_CACHE: dict[int, list[Elemento]] = {}


def _percorrer(raiz, limite_visitados: int = LIMITE_VISITADOS, limite_segundos: float = LIMITE_SEGUNDOS):
    """Busca em profundidade com limites de nós, profundidade e tempo (páginas web são enormes)."""
    fim = time.monotonic() + limite_segundos
    pilha = [(raiz, 0)]
    visitados = 0
    while pilha:
        atual, prof = pilha.pop()
        if visitados >= limite_visitados or time.monotonic() > fim:
            return
        visitados += 1
        if atual is not raiz:
            yield atual
        if prof >= LIMITE_PROFUNDIDADE:
            continue
        filhos = []
        try:
            filho = atual.GetFirstChildControl()
            while filho is not None and len(filhos) < 500:
                filhos.append(filho)
                filho = filho.GetNextSiblingControl()
        except Exception:  # noqa: BLE001 — um ramo ruim não derruba a busca
            pass
        pilha.extend((f, prof + 1) for f in reversed(filhos))


def _descrever(controle) -> tuple[str, str, Retangulo, bool, bool] | None:
    """(nome, tipo, retângulo, é senha, fora da tela) ou None se não for clicável."""
    try:
        tipo_bruto = controle.ControlTypeName
    except Exception:  # noqa: BLE001
        return None
    if tipo_bruto not in CLICAVEIS:
        return None
    try:
        nome = (controle.Name or "").strip()
        r = controle.BoundingRectangle
        ret = Retangulo.de_bordas(r.left, r.top, r.right, r.bottom)
        fora = bool(controle.IsOffscreen)
        senha = tipo_bruto == "EditControl" and bool(getattr(controle, "IsPassword", False))
    except Exception:  # noqa: BLE001
        return None
    if ret.largura <= 0 or ret.altura <= 0:
        return None
    if not nome:
        if tipo_bruto != "EditControl":
            return None
        nome = "(campo sem nome)"
    return " ".join(nome.split()), CLICAVEIS[tipo_bruto], ret, senha, fora


def coletar(raiz, filtro: str = "") -> list[Elemento]:
    """Todos os elementos clicáveis visíveis sob `raiz` que contêm o filtro no nome."""
    alvo = _simples(filtro)
    achados: list[Elemento] = []
    for controle in _percorrer(raiz):
        d = _descrever(controle)
        if d is None:
            continue
        nome, tipo, ret, senha, fora = d
        if fora or (alvo and alvo not in _simples(nome)):
            continue
        achados.append(Elemento(f"e{len(achados) + 1}", nome, tipo, ret, senha, controle))
    return achados


def listar(hwnd: int, filtro: str = "") -> list[Elemento]:
    """Lê os elementos da janela e guarda a lista para clicar por id depois."""
    def tarefa():
        raiz = _raiz(hwnd)
        if raiz is None:
            raise RuntimeError("a UI Automation não achou a janela")
        lista = coletar(raiz, filtro)
        _CACHE[hwnd] = lista
        return lista

    return _executar(tarefa)


def texto_da_lista(titulo: str, lista: list[Elemento], filtro: str = "") -> str:
    if not lista:
        if filtro:
            return f"Nenhum elemento com '{filtro}' em '{titulo}'. Tente outro filtro ou print_da_tela + clicar."
        return f"Não achei elementos clicáveis em '{titulo}'. Use print_da_tela e clicar(x, y)."
    mostrados = lista[:LIMITE_ELEMENTOS]
    cab = f"Elementos de '{titulo}' ([x,y largura x altura] em pixels de tela):"
    linhas = [cab, *(e.linha() for e in mostrados)]
    if len(lista) > LIMITE_ELEMENTOS:
        linhas.append(f"(+{len(lista) - LIMITE_ELEMENTOS} não listados; use filtro para achar outros)")
    return "\n".join(linhas)


# --- Clique ------------------------------------------------------------------------------------

def escolher(lista: list[Elemento], nome_ou_id: str) -> tuple[Elemento | None, int]:
    """Por id curto (e3) ou por nome: exato primeiro, depois trecho. Devolve (elemento, quantos casaram)."""
    pedido = (nome_ou_id or "").strip()
    m = ID_CURTO.match(pedido)
    if m:
        alvo = next((e for e in lista if e.id.lower() == pedido.lower()), None)
        return alvo, int(alvo is not None)
    chave = _simples(pedido)
    if not chave:
        return None, 0
    exatos = [e for e in lista if _simples(e.nome) == chave]
    if exatos:
        return exatos[0], len(exatos)
    parecidos = [e for e in lista if chave in _simples(e.nome)]
    return (parecidos[0] if parecidos else None), len(parecidos)


def _acionar(controle) -> str:
    """Invoke, Select ou Toggle pela UI Automation; '' se o elemento não aceitar nenhum."""
    for obter, acao, rotulo in (("GetInvokePattern", "Invoke", "acionei"),
                                ("GetSelectionItemPattern", "Select", "selecionei"),
                                ("GetTogglePattern", "Toggle", "alternei"),
                                ("GetExpandCollapsePattern", "Expand", "abri")):
        try:
            padrao = getattr(controle, obter)()
        except Exception:  # noqa: BLE001
            padrao = None
        if padrao:
            getattr(padrao, acao)()
            return rotulo
    return ""


def acionar(hwnd: int, nome_ou_id: str) -> tuple[Elemento | None, int, str]:
    """Acha o elemento (na última lista se for id) e aciona. Devolve (elemento, quantos casaram, como).

    `como` vazio = o elemento não aceita acionamento direto; quem chama clica no centro dele.
    quantos == -1: pediram um id, mas esta janela ainda não foi listada.
    """
    def tarefa():
        por_id = bool(ID_CURTO.match((nome_ou_id or "").strip()))
        lista = _CACHE.get(hwnd) if por_id else None
        if por_id and lista is None:
            return None, -1, ""          # id sem lista guardada desta janela
        if lista is None:
            raiz = _raiz(hwnd)
            if raiz is None:
                raise RuntimeError("a UI Automation não achou a janela")
            # Busca por nome não substitui a lista guardada: os ids que a CLI já viu continuam valendo.
            lista = coletar(raiz)
        elemento, casados = escolher(lista, nome_ou_id)
        if elemento is None:
            return None, casados, ""
        return elemento, casados, _acionar(elemento.controle)

    return _executar(tarefa)
