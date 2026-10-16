"""LM Studio sintético: socket reservado pelo SO, HTTP/SSE reais, nenhum processo filho."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def provedor_falso():
    estado = {"instancia": "anterior", "modelo": "antigo", "recusar_descarga": False,
              "interromper": False, "requisicoes": [], "sse": [], "atraso": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def responder(self, dados, status=200):
            corpo = json.dumps(dados).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            estado["requisicoes"].append(["GET", self.path])
            self.responder({"models": [
                {"type": "llm", "key": m, "loaded_instances": [
                    {"id": estado["instancia"], "config": {"context_length": 4096}}
                ] if estado["instancia"] and estado["modelo"] == m else []}
                for m in ("antigo", "novo")
            ]})

        def do_POST(self):
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            estado["requisicoes"].append(["POST", self.path, corpo])
            if self.path.endswith("/unload"):
                if not estado["recusar_descarga"]:
                    estado["instancia"] = None
                return self.responder({"instance_id": corpo["instance_id"]})
            if self.path.endswith("/load"):
                estado["modelo"] = corpo["model"]
                estado["instancia"] = "instancia-nova"
                return self.responder({"instance_id": "instancia-nova"})
            if self.path == "/v1/chat/completions":
                if corpo["model"] not in ("anterior", "instancia-nova", "novo", "antigo"):
                    return self.responder({"erro": "modelo_inexistente"}, 404)
                if estado["atraso"]:
                    threading.Event().wait(estado["atraso"])
                if corpo.get("tools") and not any(m["role"] == "tool" for m in corpo["messages"]):
                    delta = {"tool_calls": [{"index": 0, "id": "hora-1", "function": {
                        "name": "hora", "arguments": "{}"}}]}
                else:
                    resultado = next((m["content"] for m in corpo["messages"] if m["role"] == "tool"), "pronto")
                    delta = {"content": resultado}
                fluxo = 'data: ' + json.dumps({"choices": [{"delta": delta}]}) + '\n\n'
                if not estado["interromper"]:
                    fluxo += 'data: [DONE]\n\n'
                estado["sse"].append(fluxo)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    self.wfile.write(fluxo.encode())
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                return
            self.responder({}, 404)

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    servidor.daemon_threads = True
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}", estado
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
