"""MCP da mesa: ferramentas de Windows que o cérebro (OpenJarvis ou uma CLI) chama. Transporte stdio.

Cada ferramenta devolve uma frase em português e nunca levanta exceção:
o agente lê a frase e decide o que dizer ao usuário.

Coordenadas: tudo em pixels físicos da área de trabalho virtual (o processo é "per-monitor DPI
aware"). O print_da_tela devolve a origem do monitor e o fator de redução da imagem; x = origem_x +
px * fator e y = origem_y + py * fator levam um pixel da imagem ao x/y que clicar() espera. Os
retângulos de elementos_da_janela e de listar_monitores já estão nessas coordenadas.
"""
from __future__ import annotations

import datetime as dt
import functools
import math
import os
import subprocess
from pathlib import Path
from typing import Annotated

import mss
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from vard import config, janelas, monitores, navegadores, programas, segredos, teclado_mouse, uia
from vard.seguro import Frase

# Apelidos e sites do usuário vêm da configuração externa (VARD_CONFIG), nunca do repositório.
ARQUIVO_PROGRAMAS = config.arquivo_config("programas.toml")
APELIDOS = programas.carregar_apelidos(ARQUIVO_PROGRAMAS)
SITES_USUARIO = programas.carregar_sites(ARQUIVO_PROGRAMAS)
PASTA_PRINTS = segredos.PASTA / "prints"

# Maior imagem que o modelo vê sem a API reduzir de novo: assim o fator devolvido é exato.
PRINT_LADO_MAX = 1568
PRINT_PIXELS_MAX = 1_150_000

mcp = MCPServer("mesa")


def _seguro(acao: str):
    """Garante o contrato da mesa: toda ferramenta devolve frase em português, nunca levanta.

    Frase e ValueError já trazem a frase pronta para a pessoa; o resto ganha o prefixo da ação.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except (Frase, ValueError) as exc:
                return str(exc)[:400]
            except ImportError as exc:
                return f"Não consegui {acao}: falta o pacote {exc.name or exc}; reinstale o núcleo do Vard."
            except Exception as exc:  # noqa: BLE001 — contrato da mesa
                return f"Não consegui {acao}: {type(exc).__name__}: {exc}"[:400]
        return wrapper
    return deco


# Descrições de parâmetros (vão no schema, fora da descrição curta da ferramenta).
Titulo = Annotated[str, Field(description="Trecho do título da janela (de listar_janelas). Vazio = janela ativa.")]
MonitorPedido = Annotated[int | str | None, Field(
    description="Número de listar_monitores (1 = mais à esquerda), 'principal' ou 'outro'. Vazio = o atual.")]
CoordX = Annotated[int, Field(description=(
    "x de tela em pixels físicos (área de trabalho virtual; monitores à esquerda do principal têm x negativo). "
    "Do print_da_tela: x = origem_x + px * fator."))]
CoordY = Annotated[int, Field(description="y de tela em pixels físicos. Do print_da_tela: y = origem_y + py * fator.")]


def _janela(titulo: str) -> janelas.Janela:
    if not (titulo or "").strip():
        j = janelas.ativa()
        if not j:
            raise Frase("Não há janela ativa agora; diga o título da janela.")
        return j
    j = janelas.escolher(janelas.listar(), titulo)
    if not j:
        raise Frase(f"Nenhuma janela com '{titulo}' no título.")
    return j


def _focar_para_entrada(titulo: str) -> str:
    """Foca a janela pedida antes de digitar/teclar. Devolve o sufixo da frase (' em X')."""
    if not (titulo or "").strip():
        return ""
    j = _janela(titulo)
    if not janelas.focar(j):
        raise Frase(f"O Windows recusou trazer '{j.titulo}' para a frente; nada foi digitado.")
    return f" em '{j.titulo}'"


def _conferir_ponto(x: int, y: int) -> monitores.Monitor:
    lista = monitores.listar()
    m = monitores.do_ponto(lista, x, y)
    if m is None:
        v = monitores.area_virtual(lista)
        raise Frase(f"O ponto ({x}, {y}) está fora dos monitores; a tela vai de ({v.x},{v.y}) a "
                    f"({v.direita - 1},{v.baixo - 1}).")
    return m


@mcp.tool()
@_seguro("abrir o site")
def abrir_url(url: str, navegador: Annotated[str, Field(
        description="brave, chrome, edge, firefox, opera, vivaldi... Vazio = navegador padrão.")] = "") -> str:
    """Abre um site (nome conhecido como youtube, domínio ou URL) no navegador padrão ou no navegador pedido."""
    if not url.strip():
        return "Diga qual site abrir."
    alvo = programas.normalizar_url(url, programas.carregar_sites(config.arquivo_config("programas.toml")))
    if not (navegador or "").strip():
        try:
            os.startfile(alvo)
        except OSError as exc:
            return f"Não consegui abrir {alvo}: {exc}"
        return f"Abri {alvo} no navegador."
    if alvo.startswith("-"):
        return f"Endereço inválido: {alvo}"
    achado = navegadores.resolver(navegador)
    if not achado:
        outros = navegadores.instalados()
        dica = f" Navegadores encontrados: {', '.join(outros)}." if outros else ""
        return f"Não encontrei o navegador '{navegador}' instalado neste PC.{dica}"
    nome, exe = achado
    try:
        # Sem herdar o stdio do MCP: o navegador vive sozinho, desligado deste processo.
        subprocess.Popen([exe, alvo], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    except OSError as exc:
        return f"Encontrei o {nome}, mas não consegui abrir: {exc}"
    return f"Abri {alvo} no {nome}."


@mcp.tool()
@_seguro("abrir o programa")
def abrir_programa(nome: str) -> str:
    """Abre um programa pelo nome falado (vscode, chrome, orca, terminal...)."""
    if not nome.strip():
        return "Diga qual programa abrir."
    alvo = programas.resolver_programa(nome, programas.carregar_apelidos(config.arquivo_config("programas.toml")))
    if not alvo:
        return f"Não encontrei o programa '{nome}' nos apelidos, no PATH nem no menu Iniciar."
    try:
        os.startfile(alvo)
    except OSError as exc:
        return f"Encontrei '{nome}' em {alvo}, mas não consegui abrir: {exc}"
    return f"Abri {nome}."


@mcp.tool()
@_seguro("listar as janelas")
def listar_janelas() -> str:
    """Lista as janelas visíveis (título, programa e monitor). Use antes de focar, mover ou fechar."""
    lista = janelas.listar()
    if not lista:
        return "Nenhuma janela visível."
    try:
        telas = monitores.listar()
    except Exception:  # noqa: BLE001 — o monitor é só informação extra
        telas = []

    def onde(j: janelas.Janela) -> str:
        if len(telas) < 2:
            return ""
        try:
            m = monitores.da_janela(telas, j.hwnd)
        except Exception:  # noqa: BLE001
            return ""
        return f" [monitor {m.indice}]" if m else ""

    texto = "\n".join(f"- {j.titulo} ({j.processo}){onde(j)}" for j in lista[:40])
    if len(lista) > 40:
        texto += f"\n(+{len(lista) - 40} janelas não listadas)"
    return texto


@mcp.tool()
@_seguro("focar a janela")
def focar_janela(titulo: str) -> str:
    """Traz para a frente a janela cujo título contém o trecho dado."""
    j = janelas.escolher(janelas.listar(), titulo)
    if not j:
        return f"Nenhuma janela com '{titulo}' no título."
    if janelas.focar(j):
        return f"Janela '{j.titulo}' em primeiro plano."
    return f"O Windows recusou trazer '{j.titulo}' para a frente."


@mcp.tool()
@_seguro("fechar a janela")
def fechar_janela(titulo: str) -> str:
    """Pede para fechar a janela cujo título contém o trecho (o programa pode perguntar 'salvar?')."""
    j = janelas.escolher(janelas.listar(), titulo)
    if not j:
        return f"Nenhuma janela com '{titulo}' no título."
    if janelas.fechar(j):
        return f"Pedi para fechar '{j.titulo}'."
    return f"A janela '{j.titulo}' já não existe."


@mcp.tool()
@_seguro("listar os monitores")
def listar_monitores() -> str:
    """Lista os monitores: número, nome, resolução, escala, área útil e qual é o principal."""
    lista = monitores.listar()
    if not lista:
        return "Não encontrei nenhum monitor."
    return "\n".join(monitores.descrever(m) for m in lista)


@mcp.tool()
@_seguro("mover a janela")
def mover_janela(
    titulo: Titulo = "",
    monitor: MonitorPedido = None,
    posicao: Annotated[str, Field(description=(
        "maximizar, minimizar, restaurar, esquerda, direita, cima, baixo, centro ou tela cheia. "
        "Vazio com monitor = leva para lá mantendo a proporção."))] = "",
    x: Annotated[int | None, Field(description="Distância da borda esquerda da área útil do monitor, em pixels.")] = None,
    y: Annotated[int | None, Field(description="Distância do topo da área útil do monitor, em pixels.")] = None,
    largura: int | None = None,
    altura: int | None = None,
) -> str:
    """Move, redimensiona, maximiza ou minimiza uma janela, inclusive para outro monitor. Título vazio = janela ativa."""
    j = _janela(titulo)
    lista = monitores.listar()
    origem = monitores.da_janela(lista, j.hwnd) or monitores.escolher(lista, None)
    destino = monitores.escolher(lista, monitor, origem)
    plano = janelas.mover(j, origem, destino, posicao, x, y, largura, altura)
    if plano.estado == "minimizar":
        return f"Minimizei '{j.titulo}'."
    onde = f" no monitor {destino.indice}" if len(lista) > 1 else ""
    if plano.estado == "maximizar":
        return f"Maximizei '{j.titulo}'{onde}."
    if plano.estado == "restaurar" and plano.ret is None:
        return f"Restaurei '{j.titulo}'."
    r = plano.ret
    canonica = janelas.normalizar_posicao(posicao)
    como = f", {canonica}" if canonica else ""
    return f"Coloquei '{j.titulo}'{onde}{como}: {r.largura}x{r.altura} em ({r.x},{r.y})."


@mcp.tool()
@_seguro("ler os elementos da janela")
def elementos_da_janela(
    titulo: Titulo = "",
    filtro: Annotated[str, Field(description="Trecho do nome do elemento (sem diferenciar acento ou caixa).")] = "",
) -> str:
    """Lista botões, links, campos e itens clicáveis de uma janela, com id curto (e1, e2...) e retângulo em pixels de tela."""
    j = _janela(titulo)
    lista = uia.listar(j.hwnd, filtro)
    return uia.texto_da_lista(j.titulo, lista, filtro)


@mcp.tool()
@_seguro("clicar no elemento")
def clicar_elemento(
    titulo: Titulo,
    nome_ou_id: Annotated[str, Field(description="Id da última elementos_da_janela (e3) ou trecho do nome do elemento.")],
) -> str:
    """Clica num elemento da janela pelo id de elementos_da_janela ou pelo nome. Se não achar, use print_da_tela e clicar."""
    if not (nome_ou_id or "").strip():
        return "Diga qual elemento clicar (id como e3 ou o nome)."
    j = _janela(titulo)
    elemento, casados, como = uia.acionar(j.hwnd, nome_ou_id)
    if casados == -1:
        return f"Liste antes com elementos_da_janela('{titulo}'): o id {nome_ou_id} vale para a última lista."
    if elemento is None:
        return (f"Não achei '{nome_ou_id}' em '{j.titulo}'. Use elementos_da_janela com filtro, "
                f"ou print_da_tela e clicar(x, y).")
    if not como:
        # Sem acionamento pela UI Automation: clique físico no centro do elemento.
        r = elemento.ret
        janelas.focar(j)
        teclado_mouse.clicar(r.x + r.largura // 2, r.y + r.altura // 2)
        como = "cliquei"
    extra = f" (havia {casados} parecidos; use o id para outro)" if casados > 1 else ""
    return f"{como.capitalize()} {elemento.tipo.lower()} \"{elemento.nome}\" em '{j.titulo}'.{extra}"


@mcp.tool()
@_seguro("clicar")
def clicar(
    x: CoordX,
    y: CoordY,
    botao: Annotated[str, Field(description="esquerdo, direito ou meio.")] = "esquerdo",
    duplo: bool = False,
) -> str:
    """Clica em x,y de tela (pixels físicos). Converta do print_da_tela pela origem e fator. Prefira clicar_elemento."""
    m = _conferir_ponto(x, y)
    teclado_mouse.clicar(x, y, botao, duplo)
    tipo = "Dei clique duplo" if duplo else "Cliquei"
    return f"{tipo} com o botão {botao} em ({x}, {y}), monitor {m.indice}."


@mcp.tool()
@_seguro("digitar")
def digitar(
    texto: str,
    janela: Annotated[str, Field(description="Trecho do título da janela para focar antes. Vazio = onde está o foco.")] = "",
) -> str:
    """Digita o texto onde está o foco do teclado (acentos funcionam; quebra de linha vira Enter)."""
    if not texto:
        return "Diga o que digitar."
    onde = _focar_para_entrada(janela)
    n = teclado_mouse.digitar(texto)
    # Nunca repete o texto na resposta: pode ser senha ditada.
    return f"Digitei {n} caracteres{onde}."


@mcp.tool()
@_seguro("apertar a tecla")
def teclar(
    combinacao: Annotated[str, Field(description="Ex.: enter, esc, tab, f5, ctrl+l, ctrl+shift+t, alt+tab, seta para baixo.")],
    janela: Annotated[str, Field(description="Trecho do título da janela para focar antes. Vazio = onde está o foco.")] = "",
    vezes: int = 1,
) -> str:
    """Aperta uma tecla ou combinação (ex.: enter, ctrl+l, alt+f4) na janela em foco."""
    teclado_mouse.interpretar(combinacao)   # valida antes de focar qualquer janela
    onde = _focar_para_entrada(janela)
    teclado_mouse.teclar(combinacao, vezes)
    repetido = f" {vezes} vezes" if vezes > 1 else ""
    return f"Apertei {combinacao.strip()}{repetido}{onde}."


@mcp.tool()
@_seguro("rolar")
def rolar(
    quantidade: Annotated[int, Field(description="Cliques da roda: positivo desce a página, negativo sobe (máx. 50).")],
    x: Annotated[int | None, Field(description="x de tela para levar o cursor antes (opcional).")] = None,
    y: Annotated[int | None, Field(description="y de tela para levar o cursor antes (opcional).")] = None,
) -> str:
    """Rola a roda do mouse onde está o cursor (ou em x,y). Positivo desce, negativo sobe."""
    if (x is None) != (y is None):
        return "Passe x e y juntos, ou nenhum dos dois."
    if x is not None and y is not None:
        _conferir_ponto(x, y)
    teclado_mouse.rolar(quantidade, x, y)
    sentido = "para baixo" if quantidade > 0 else "para cima"
    return f"Rolei {abs(quantidade)} {sentido}."


def fator_reducao(largura: int, altura: int) -> float:
    """Quanto dividir a imagem para caber no que o modelo enxerga sem nova redução (>= 1)."""
    return max(1.0, largura / PRINT_LADO_MAX, altura / PRINT_LADO_MAX,
               math.sqrt(largura * altura / PRINT_PIXELS_MAX))


def _regiao(monitor: int | str | None) -> tuple[monitores.Retangulo, str]:
    lista = monitores.listar()
    texto = str(monitor).strip().lower() if monitor is not None else ""
    if texto in ("0", "todos", "tudo", "todas"):
        return monitores.area_virtual(lista), "todos os monitores"
    m = monitores.escolher(lista, monitor)
    return m.tela, f"monitor {m.indice}"


@mcp.tool()
@_seguro("capturar a tela")
def print_da_tela(
    caminho: str = "",
    monitor: Annotated[int | str | None, Field(
        description="Número de listar_monitores, 'principal' (padrão) ou 'todos'.")] = None,
) -> str:
    """Captura um monitor (ou 'todos') em PNG; devolve o caminho e a origem/fator para converter pixel da imagem em x,y."""
    from PIL import Image

    # Só o nome do arquivo conta: nunca grava fora da pasta de prints nem sobrescreve nada existente.
    base = Path(caminho).stem if caminho.strip() else f"tela-{dt.datetime.now():%Y%m%d-%H%M%S}"
    base = base or "tela"
    destino = PASTA_PRINTS / f"{base}.png"
    n = 2
    while destino.exists():
        destino = PASTA_PRINTS / f"{base}-{n}.png"
        n += 1
    regiao, descricao = _regiao(monitor)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with mss.mss() as s:
            shot = s.grab({"left": regiao.x, "top": regiao.y, "width": regiao.largura, "height": regiao.altura})
        imagem = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        fator = fator_reducao(*imagem.size)
        if fator > 1:
            novo = (max(1, int(imagem.width / fator)), max(1, int(imagem.height / fator)))
            imagem = imagem.resize(novo, Image.Resampling.LANCZOS)
        fator = regiao.largura / imagem.width
        imagem.save(destino, "PNG")
    except Exception as exc:
        return f"Não consegui capturar a tela: {exc}"
    f = f"{fator:.4f}".rstrip("0").rstrip(".")
    return (f"Print salvo em {destino} ({descricao}, imagem {imagem.width}x{imagem.height}). "
            f"Pixel (px, py) da imagem = tela x = {regiao.x} + px*{f}, y = {regiao.y} + py*{f}.")


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


@mcp.tool()
@_seguro("ler a hora")
def hora_atual() -> str:
    """Devolve a data e a hora atuais do computador, em português."""
    agora = dt.datetime.now().astimezone()
    off = agora.utcoffset() or dt.timedelta(0)
    if off == dt.timedelta(hours=-4):
        zona = "horário de Manaus"
    else:
        h = int(off.total_seconds() // 60)
        zona = f"UTC{'-' if h < 0 else '+'}{abs(h) // 60:02d}:{abs(h) % 60:02d}"
    return (f"Agora são {agora.hour}h{agora.minute:02d} de {DIAS[agora.weekday()]}, {agora.day} de "
            f"{MESES[agora.month - 1]} de {agora.year} ({zona}).")


if __name__ == "__main__":
    from vard.instalaveis import limpar_ambiente_mcp
    limpar_ambiente_mcp()
    mcp.run()
