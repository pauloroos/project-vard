"""Configurações do Vard por stdio: respostas legíveis, sem acesso a chaves."""
from __future__ import annotations

import functools
import json
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer
from vard import ajustes, habilidades

mcp = MCPServer("configuracoes")


def _seguro(fn):
    @functools.wraps(fn)
    def executar(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as e:
            return str(e)
        except Exception:
            return "Não consegui concluir o ajuste. Confira os dados na tela de Configurações e tente novamente."
    return executar


def _texto(titulo, valor):
    return titulo + ":\n" + json.dumps(ajustes.sem_segredos(valor), ensure_ascii=False, indent=2)


def _confirmar(efeito):
    return efeito + ". Antes de executar, peça a confirmação do usuário."


@mcp.tool()
@_seguro
def ver_configuracoes() -> str:
    """Mostra aparência, voz, perfil e quem responde; nunca mostra chaves ou credenciais."""
    hud = ajustes.ler_documento("hud")
    hud.setdefault("usar_openjarvis", False)
    campos = ("nome", "cor_elementos", "opacidade_elementos", "voz_provedor", "voz_motor", "voz_propria", "voz_reserva_provedor", "voz_reserva_id", "cerebro", "usar_openjarvis")
    return _texto("Configurações atuais", {"widget": {k: hud[k] for k in campos if k in hud},
        "perfil": ajustes.ler_documento("perfil"), "quem_responde": ajustes.ler_documento("paineis").get("ativo")})


@mcp.tool()
@_seguro
def mudar_aparencia(cor: str | None = None, opacidade: float | None = None) -> str:
    """Muda a cor hexadecimal (#rrggbb), a opacidade dos elementos (0,2 a 1) ou as duas, imediatamente."""
    ajustes.mudar_aparencia(cor, opacidade)
    return "Aparência atualizada."


@mcp.tool()
@_seguro
def listar_vozes() -> str:
    """Lista motores e vozes cadastradas para escolher a voz principal e a reserva."""
    return _texto("Vozes de fábrica e cadastradas; XTTS e ElevenLabs usam os IDs cadastrados na tela", ajustes.listar_vozes())


@mcp.tool()
@_seguro
def escolher_voz(motor: str, principal: str, reserva: str = "") -> str:
    """Escolhe motor e IDs da voz principal e reserva do mesmo motor; reserva vazia desliga a reserva."""
    ajustes.escolher_voz(motor, principal, reserva)
    if motor in ("elevenlabs", "gemini"):
        return "Voz principal e reserva atualizadas. Se faltar autenticação, cadastre a chave na tela de Configurações."
    return "Voz principal e reserva atualizadas."


@mcp.tool()
@_seguro
def listar_provedores() -> str:
    """Lista provedores cadastrados, modelos, principal e reserva, sem credenciais."""
    return _texto("Provedores", ajustes.ler_documento("paineis"))


@mcp.tool()
@_seguro
def cadastrar_provedor(provedor: dict) -> str:
    """Cadastra id, nome, tipo, url_base e modelo de um provedor. Chaves só na tela de Configurações."""
    if ajustes.sem_segredos(provedor) != provedor:
        return "Cadastre a chave na tela de Configurações."
    ajustes.cadastrar_provedor(provedor)
    return "Provedor cadastrado. Se exigir autenticação, cadastre a chave na tela de Configurações."


@mcp.tool()
@_seguro
def editar_provedor(id: str, campos: dict) -> str:
    """Edita nome, endereço, modelo ou opções de um provedor cadastrado, sem alterar chaves."""
    if ajustes.sem_segredos(campos) != campos:
        return "Cadastre a chave na tela de Configurações."
    ajustes.editar_provedor(id, campos)
    return "Provedor atualizado."


@mcp.tool()
@_seguro
def remover_provedor(id: str, confirmado: bool = False) -> str:
    """Remove um provedor e limpa sua seleção como principal ou reserva; exige confirmação."""
    if confirmado is not True:
        return _confirmar(f"Vou remover o provedor {id} e limpar sua seleção como principal ou reserva, sem desinstalar programas")
    ajustes.remover_provedor(id)
    return "Removi o provedor."


@mcp.tool()
@_seguro
def escolher_quem_responde(ativo: str, reserva: str | None = None, confirmado: bool = False) -> str:
    """Troca quem responde para um ID cadastrado ou openjarvis e define a reserva; exige confirmação."""
    if confirmado is not True:
        return _confirmar(f"Vou usar {ativo} para responder e {reserva or 'nenhum provedor'} como reserva; as próximas perguntas usarão esta escolha")
    ajustes.escolher_quem_responde(ativo, reserva)
    return "Quem responde foi atualizado."


@mcp.tool()
@_seguro
def testar_provedor(id: str) -> str:
    """Testa a conexão do provedor cadastrado pelo núcleo, sem trocar quem responde ou mostrar a chave."""
    return _texto("Teste do provedor", ajustes.http_local("POST", "/configuracoes/provedores/" + quote(id, safe="") + "/testar"))


@mcp.tool()
@_seguro
def listar_instalaveis() -> str:
    """Lista programas disponíveis para instalação, tamanho informado e estado, sem instalar nada."""
    return _texto("Instaláveis", ajustes.http_local("GET", "/instalaveis"))


@mcp.tool()
@_seguro
def instalar(id: str, confirmado: bool = False) -> str:
    """Instala um item do catálogo pelo núcleo após confirmação; informe antes o tamanho e o efeito."""
    if confirmado is not True:
        item = next(i for i in ajustes.http_local("GET", "/instalaveis")["itens"] if i["id"] == id)
        tamanho = f"{item['tamanho_mb']} MB" if item.get("tamanho_mb") is not None else "tamanho não informado pelo fornecedor"
        return _confirmar(f"Vou instalar {item['nome']} ({tamanho}); isso baixa arquivos e adiciona o programa ao computador")
    return _texto("Instalação solicitada", ajustes.http_local("POST", "/instalaveis/" + quote(id, safe="") + "/instalar", {"confirmado": True}))


@mcp.tool()
@_seguro
def andamento_instalacao(id: str) -> str:
    """Consulta estado e progresso da instalação já iniciada, sem iniciar outra instalação."""
    return _texto("Andamento", ajustes.http_local("GET", "/instalaveis/" + quote(id, safe="") + "/andamento"))


@mcp.tool()
@_seguro
def listar_habilidades() -> str:
    """Consulta receitas ligadas do usuário, com nome, quando usar e instruções; consulte antes de agir."""
    return _texto("Habilidades ligadas", ajustes.listar_habilidades())


@mcp.tool()
@_seguro
def cadastrar_habilidade(habilidade: dict) -> str:
    """Ensina uma receita com id, nome, quando (lista de exemplos) e instrucoes; começa como treinada."""
    ajustes.cadastrar_habilidade(habilidade)
    return "Habilidade cadastrada como treinada."


@mcp.tool()
@_seguro
def editar_habilidade(id: str, campos: dict) -> str:
    """Edita nome, exemplos, instruções ou ligada; receita volta a treinada. Também vale para as de fábrica:
    conversa, computador, oficina, consultas, memoria, reuniao, sistema, resumo-manha, pesquisa, agente-remoto."""
    ajustes.editar_habilidade(id, campos)
    return "Habilidade atualizada."


@mcp.tool()
@_seguro
def excluir_habilidade(id: str, confirmado: bool = False) -> str:
    """Exclui definitivamente uma receita do usuário, após confirmação. Fábrica não se exclui: restaure ou desligue."""
    if confirmado is not True and id not in habilidades.IDS_FABRICA:
        return _confirmar(f"Vou excluir a receita {id}; suas instruções deixarão de estar disponíveis")
    ajustes.excluir_habilidade(id)
    return "Habilidade excluída."


@mcp.tool()
@_seguro
def restaurar_habilidade(id: str) -> str:
    """Volta uma habilidade de fábrica ao nome, exemplos e instruções de fábrica; ligada/desligada não muda."""
    ajustes.restaurar_habilidade(id)
    return "Habilidade de fábrica restaurada ao padrão."


@mcp.tool()
@_seguro
def marcar_habilidade_validada(id: str) -> str:
    """Marca uma receita como validada depois de funcionar e registra a data da validação."""
    ajustes.marcar_habilidade_validada(id)
    return "Habilidade marcada como validada."


@mcp.tool()
@_seguro
def listar_programas() -> str:
    """Lista apelidos de programas e sites cadastrados em programas.toml."""
    return _texto("Programas e sites", ajustes.ler_documento("programas"))


@mcp.tool()
@_seguro
def cadastrar_programa(nome: str, destino: str, site: bool = False) -> str:
    """Cadastra um apelido para executável ou, com site=true, para um endereço de site."""
    ajustes.cadastrar_programa(nome, destino, site)
    return "Programa ou site cadastrado."


@mcp.tool()
@_seguro
def remover_programa(nome: str, site: bool = False, confirmado: bool = False) -> str:
    """Remove um apelido de programa ou site; não desinstala o programa e exige confirmação."""
    if confirmado is not True:
        return _confirmar(f"Vou remover o apelido {nome}; o programa continuará instalado")
    ajustes.remover_programa(nome, site)
    return "Apelido removido."


@mcp.tool()
@_seguro
def ver_telegram() -> str:
    """Mostra se o Telegram está ligado, o chat permitido, se o bot está guardado no cofre e o que há no OpenJarvis; nunca o token."""
    from vard import telegram as tg_mod, telegram_migracao
    estado = tg_mod.estado()
    return _texto("Telegram", {"ligado": estado["ligado"], "chat_permitido": estado["chat_permitido"],
        "bot_guardado": estado["token_configurado"], "do_openjarvis": telegram_migracao.previa()})


def _sincronizar_telegram() -> None:
    """O poller vive no processo do núcleo: avisa para reler a configuração (núcleo fora = vale no próximo início)."""
    try:
        ajustes.http_local("POST", "/telegram/sincronizar")
    except Exception:  # noqa: BLE001
        pass


@mcp.tool()
@_seguro
def configurar_telegram(ligado: bool, chat: str = "") -> str:
    """Liga ou desliga o Telegram e define o chat permitido; o token só é gravado pela tela."""
    from vard import telegram as tg_mod
    tg_mod.configurar(ligado, chat)
    _sincronizar_telegram()
    return "Telegram atualizado."


@mcp.tool()
@_seguro
def trazer_telegram_do_openjarvis(substituir: bool = False) -> str:
    """Traz o Telegram do OpenJarvis para o Vard: token direto para o cofre (não passa por aqui), chats e ligado.

    Não altera o OpenJarvis. Se o Vard já tiver Telegram, pede confirmação e só substitui com substituir=true.
    Depois de trazido, o OpenJarvis precisa ficar desligado: dois programas no mesmo bot brigam pelas mensagens.
    """
    r = ajustes.http_local("POST", "/telegram/trazer_openjarvis", {"substituir": substituir is True})
    if not r.get("ok") and r.get("motivo") == "ja_configurado":
        return _confirmar("O Vard já tem um Telegram configurado; vou substituí-lo pelo do OpenJarvis (chame de novo com substituir=true)")
    campos = {k: r[k] for k in ("ok", "mudou", "fonte", "chats", "ligado", "rodando", "detalhe", "aviso") if k in r}
    return _texto("Telegram do OpenJarvis", campos)


if __name__ == "__main__":
    from vard.instalaveis import limpar_ambiente_mcp
    limpar_ambiente_mcp()
    mcp.run()
