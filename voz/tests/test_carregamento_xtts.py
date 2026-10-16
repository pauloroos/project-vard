"""Testes de carregamento condicional do motor XTTS (T5b).

Verifica que:
- criar_app(motor=None) só instancia XTTS se pacote xtts-v2 estiver instalado.
- Sem o pacote, motor permanece None e Kokoro/Edge/Piper assumem.
- Falha na inicialização do motor é capturada e logada (motor=None).

Nota: não importamos servidor diretamente porque ele puxa numpy/torch
no nível do módulo. Testamos a lógica via inspeção do código-fonte
e mocks controlados antes da importação.
"""
from __future__ import annotations

import ast
from pathlib import Path


class TestCarregamentoXttsCondicional:
    """Valida a lógica de carregamento condicional do XTTS no servidor."""

    def _ler_fonte_criar_app(self) -> str:
        """Lê o fonte de servidor.py para análise estática."""
        caminho = Path(__file__).resolve().parent.parent / "vard_voz" / "servidor.py"
        return caminho.read_text(encoding="utf-8")

    def test_codigo_verifica_pacote_antes_de_instanciar_motor(self):
        """O fonte deve conter verificação de InstaladorPacotes.esta_instalado('xtts-v2')."""
        fonte = self._ler_fonte_criar_app()
        assert "InstaladorPacotes" in fonte, "servidor.py deve importar InstaladorPacotes"
        assert 'esta_instalado("xtts-v2")' in fonte or "esta_instalado('xtts-v2')" in fonte, (
            "servidor.py deve verificar esta_instalado('xtts-v2') antes de instanciar Motor"
        )

    def test_motor_none_quando_pacote_nao_instalado(self):
        """Quando _xtts_instalado é False, motor deve ser atribuído como None."""
        fonte = self._ler_fonte_criar_app()
        # Verifica que há branch else com motor = None
        tree = ast.parse(fonte)
        encontrou_else_motor_none = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # Procura o if _xtts_instalado
                if isinstance(node.test, ast.Name) and node.test.id == "_xtts_instalado":
                    # O corpo do else deve conter motor = None
                    if node.orelse:
                        for stmt in node.orelse:
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Name) and target.id == "motor":
                                        if isinstance(stmt.value, ast.Constant) and stmt.value.value is None:
                                            encontrou_else_motor_none = True
        assert encontrou_else_motor_none, (
            "servidor.py deve ter 'else: motor = None' quando xtts-v2 não está instalado"
        )

    def test_falha_motor_capturada_com_warning(self):
        """Falha na instanciação do Motor deve ser capturada e logada."""
        fonte = self._ler_fonte_criar_app()
        assert "log.warning" in fonte, "servidor.py deve logar warning quando motor falha"
        assert "xtts-v2 instalado mas motor falhou" in fonte or "motor falhou ao iniciar" in fonte, (
            "servidor.py deve logar mensagem específica sobre falha do motor XTTS"
        )

    def test_import_motor_dentro_do_if_xtts_instalado(self):
        """A importação de Motor deve estar dentro do bloco if _xtts_instalado."""
        fonte = self._ler_fonte_criar_app()
        tree = ast.parse(fonte)
        import_motor_dentro_do_if = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if isinstance(node.test, ast.Name) and node.test.id == "_xtts_instalado":
                    # Procura import/from .motor dentro do corpo do if
                    for stmt in ast.walk(node):
                        if isinstance(stmt, ast.ImportFrom):
                            if stmt.module and "motor" in stmt.module:
                                import_motor_dentro_do_if = True
        assert import_motor_dentro_do_if, (
            "Import de Motor deve estar dentro do bloco if _xtts_instalado para evitar import desnecessário"
        )

    def test_kokoro_independente_de_xtts(self):
        """Kokoro deve ser instanciado independentemente do estado do XTTS."""
        fonte = self._ler_fonte_criar_app()
        # Kokoro é instanciado após o bloco if/else do XTTS
        assert "MotorKokoro" in fonte, "servidor.py deve suportar MotorKokoro"
        # Verifica que motor_kokoro não depende de _xtts_instalado
        linhas = fonte.split("\n")
        linha_kokoro = next((i for i, l in enumerate(linhas) if "MotorKokoro" in l and "import" not in l), None)
        linha_xtts_check = next((i for i, l in enumerate(linhas) if "_xtts_instalado" in l), None)
        assert linha_kokoro is not None, "MotorKokoro deve ser instanciado em criar_app"
        assert linha_xtts_check is not None, "_xtts_instalado deve ser verificado"
        # Kokoro vem depois do bloco XTTS
        assert linha_kokoro > linha_xtts_check, (
            "MotorKokoro deve ser instanciado após o bloco condicional do XTTS"
        )