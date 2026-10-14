"""Orca de mentira para os testes da oficina e da vigia."""
from vard.orca_cli import ErroOrca, Leitura


class FakeOrca:
    def __init__(self, *, exit=False, idle=False, saida="", tela="", falha=None, bloqueio="", antes_de_ler=None,
                 ao_criar_worktree=None, ao_criar_terminal=None):
        self.exit, self.idle, self.saida, self.tela, self.falha = exit, idle, saida, tela, falha
        self.bloqueio, self.antes_de_ler = bloqueio, antes_de_ler   # antes_de_ler: simula outro processo mexendo na loja
        self.ao_criar_worktree, self.ao_criar_terminal = ao_criar_worktree, ao_criar_terminal   # outro processo no meio
        self.chamadas: list[tuple] = []

    def _talvez_falhe(self, nome):
        if self.falha == nome:
            raise ErroOrca("boom", nome)

    def criar_worktree(self, repo_caminho, nome):
        self._talvez_falhe("criar_worktree")
        self.chamadas.append(("criar_worktree", repo_caminho, nome))
        if self.ao_criar_worktree:
            self.ao_criar_worktree()
        return {"worktree": f"r1::X:/wt/{nome}", "caminho": f"X:/wt/{nome}", "branch": nome}

    def criar_terminal(self, worktree, comando, titulo, shell=""):
        self._talvez_falhe("criar_terminal")
        self.chamadas.append(("criar_terminal", worktree, comando, titulo, shell))
        if self.ao_criar_terminal:
            self.ao_criar_terminal()
        return "term_1"

    def esperar(self, terminal, condicao, timeout_ms):
        self._talvez_falhe("esperar")
        self.chamadas.append(("esperar", terminal, condicao))
        if self.antes_de_ler and condicao == "tui-idle":
            self.antes_de_ler()
        if condicao == "exit":
            return self.exit, ""
        return self.idle, self.bloqueio

    def ler(self, terminal, cursor=None, limite=400):
        self.chamadas.append(("ler", terminal, cursor))
        return Leitura(self.saida, (cursor or 0) + (1 if self.saida else 0))

    def ler_tela(self, terminal):
        return self.tela

    def enviar(self, terminal, texto):
        self.chamadas.append(("enviar", terminal, texto))

    def fechar_terminal(self, terminal):
        self.chamadas.append(("fechar_terminal", terminal))

    def remover_worktree(self, worktree, forcar=False):
        self.chamadas.append(("remover_worktree", worktree, forcar))
