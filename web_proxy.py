#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class ProxyHandler(SimpleHTTPRequestHandler):
    backend_url = "http://127.0.0.1:8000"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/api/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", self.headers.get("Access-Control-Request-Headers", "*"))
            self.end_headers()
            return
        super().do_OPTIONS()

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self.proxy_request()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self.proxy_request()
            return
        self.send_error(404)

    def proxy_request(self) -> None:
        backend = urlparse(self.backend_url)
        target_path = self.path.removeprefix("/api") or "/"
        body_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(body_length) if body_length else None

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        headers["Host"] = backend.netloc

        connection_cls = http.client.HTTPSConnection if backend.scheme == "https" else http.client.HTTPConnection
        connection = connection_cls(backend.hostname, backend.port or (443 if backend.scheme == "https" else 80), timeout=120)
        try:
            connection.request(self.command, target_path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response_body)
        except Exception as exc:
            message = f"Launcher API proxy failed to reach backend {self.backend_url}: {exc}"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))
        finally:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve HyperSpeed UI and proxy /api to FastAPI.")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--directory", default=".", help="Static UI directory to serve.")
    args = parser.parse_args()

    ProxyHandler.backend_url = args.backend.rstrip("/")
    handler = partial(ProxyHandler, directory=args.directory)
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(
        f"Serving UI from {args.directory} on http://{args.bind}:{args.port}, proxying /api to {ProxyHandler.backend_url}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
