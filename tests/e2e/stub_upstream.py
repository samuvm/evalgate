"""Deterministic OpenAI-compatible upstream for the e2e adoption test. Standard library only.

The answer is derived from the sha256 of the EXACT request bytes: if the proxy altered a single byte of
the request, the app's output would change and G-ADOPTION would count the diff. The response is valid
against the pinned OpenAI schema and deliberately non-canonical (indentation, unicode) so that any
re-serialization by the proxy is visible too.

Usage: python stub_upstream.py --port 18001
"""

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        digest = hashlib.sha256(body).hexdigest()
        response = {
            "id": f"chatcmpl-stub-{digest[:10]}",
            "object": "chat.completion",
            "created": 1789000000,
            "model": json.loads(body).get("model", "stub"),
            "choices": [
                {
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"Respuesta simulada · {digest[:16]} · ñ",
                        "refusal": None,
                    },
                }
            ],
            "usage": {
                "prompt_tokens": len(body) // 4,
                "completion_tokens": 9,
                "total_tokens": len(body) // 4 + 9,
            },
        }
        payload = json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    ThreadingHTTPServer(("127.0.0.1", parser.parse_args().port), Handler).serve_forever()
