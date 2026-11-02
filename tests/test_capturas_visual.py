import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/provas/capturas-visual.py"
spec = importlib.util.spec_from_file_location("capturas_visual", SCRIPT)
capturas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capturas)


class CapturasSeguras(unittest.TestCase):
    def test_rede_permite_apenas_origem_e_simula_saude(self):
        class Contexto:
            def route(self, padrao, callback): self.callback = callback
            def route_web_socket(self, padrao, callback): self.websocket = callback
        class Rota:
            def __init__(self, url):
                self.request = type("Pedido", (), {"url": url})()
                self.acao = None
            def fulfill(self, **kwargs): self.acao = ("simulada", kwargs)
            def abort(self): self.acao = ("bloqueada",)
            def continue_(self): self.acao = ("permitida",)
        contexto = Contexto()
        capturas.configurar_rotas_mock(contexto, "http://127.0.0.1:5199")
        for url, esperado in [
            ("http://127.0.0.1:5199/index.html", "permitida"),
            ("http://127.0.0.1:5199/oj/health", "simulada"),
            ("http://127.0.0.1:5199/oj/v1/speech/health", "simulada"),
            ("http://127.0.0.1:5199/oj/outro", "bloqueada"),
            ("http://127.0.0.1:4710/saude", "bloqueada"),
            ("https://exemplo.invalid/", "bloqueada"),
        ]:
            rota = Rota(url)
            contexto.callback(rota)
            self.assertEqual(rota.acao[0], esperado, url)
        ws = type("WebSocket", (), {"close": lambda self: setattr(self, "fechado", True)})()
        contexto.websocket(ws)
        self.assertTrue(ws.fechado)

    def test_saida_deve_ser_explicita(self):
        with patch.object(sys, "argv", [str(SCRIPT)]), \
             patch.object(capturas.subprocess, "Popen", side_effect=AssertionError("início inesperado")), \
             self.assertRaises(SystemExit):
            capturas.main()

    def test_nao_sobrescreve_imagem_existente(self):
        with tempfile.TemporaryDirectory() as pasta:
            imagem = Path(pasta) / "hud.png"
            imagem.write_bytes(b"referencia")
            with patch.object(sys, "argv", [str(SCRIPT), "--saida", pasta]), \
                 patch.object(capturas.subprocess, "Popen") as iniciar, \
                 self.assertRaises(FileExistsError):
                capturas.main()
            self.assertEqual(imagem.read_bytes(), b"referencia")
            iniciar.assert_not_called()

    def test_nao_aceita_servidor_alheio_quando_vite_falha(self):
        class Processo:
            stdout = io.StringIO("Port 5199 is already in use\n")
            def poll(self):
                return 1
        with self.assertRaises(RuntimeError):
            capturas.esperar_servidor(Processo(), timeout=1)

    def test_aceita_aviso_de_prontidao_do_proprio_vite(self):
        class Processo:
            stdout = io.StringIO("  ➜  Local:   http://127.0.0.1:5199/\n")
            def poll(self):
                return None
        capturas.esperar_servidor(Processo(), timeout=1)


if __name__ == "__main__":
    unittest.main()
