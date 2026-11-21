"""A stand-in model server for CI: the two endpoints the service and the chart use, with one fixed answer.

    python tests/fake_model.py        # listens on 0.0.0.0:8080; standard library only
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWER = "This is the stub model server."


class Handler(BaseHTTPRequestHandler):
    def reply(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # /health, as llama.cpp's server answers it
        self.reply({"status": "ok"})

    def do_POST(self):  # /v1/chat/completions
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.reply({"choices": [{"message": {"role": "assistant", "content": ANSWER}}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
