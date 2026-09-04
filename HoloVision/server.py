#!/usr/bin/env python3
"""HoloVision Local Network Operations Center — local web server.

Run:  python3 server.py
Then open the URL it prints (default http://127.0.0.1:8787).

The server binds to loopback only and does the privileged network work
(scanning, SSDP/mDNS, Wake-on-LAN, UPnP control) that a browser tab cannot do
on its own. Your browser is just the UI. No traffic is routed through any
third-party cloud service.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from opscenter import __version__, control, discovery, net

WEB_DIR = pathlib.Path(__file__).parent / "web"
# Per-run token: pages from other origins can reach 127.0.0.1, so control
# actions (POST) require this token, handed to our own UI at page load.
SESSION_TOKEN = secrets.token_urlsafe(24)


class OpsHandler(BaseHTTPRequestHandler):
    server_version = f"HoloVision/{__version__}"
    protocol_version = "HTTP/1.1"

    # ---- helpers -------------------------------------------------------- #
    def _host_ok(self) -> bool:
        """Reject requests whose Host header isn't loopback (anti DNS-rebinding)."""
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "::1", "")

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: pathlib.Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._send_json({"error": "not found"}, 404)
            return
        # Inject the session token into the page so our own UI can authenticate.
        if content_type.startswith("text/html"):
            data = data.replace(b"__SESSION_TOKEN__", SESSION_TOKEN.encode())
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def _token_ok(self, body: dict) -> bool:
        token = self.headers.get("X-Ops-Token") or body.get("token")
        return secrets.compare_digest(str(token or ""), SESSION_TOKEN)

    def log_message(self, fmt, *args):  # quieter console
        return

    # ---- routing -------------------------------------------------------- #
    def do_GET(self):
        if not self._host_ok():
            self._send_json({"error": "forbidden host"}, 403)
            return
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/api/info":
            self._send_json(
                {
                    "version": __version__,
                    "local_ip": net.get_local_ip(),
                    "subnet": net.get_subnet(),
                    "mdns_available": discovery.mdns_available(),
                }
            )
            return
        if path == "/api/scan":
            subnet = q.get("subnet", [None])[0]
            self._send_json({"devices": discovery.sweep(subnet)})
            return
        if path == "/api/ports":
            host = q.get("host", [None])[0]
            if not host:
                self._send_json({"error": "host required"}, 400)
                return
            self._send_json({"host": host, "open": discovery.scan_ports(host)})
            return
        if path == "/api/ssdp":
            self._send_json({"devices": discovery.ssdp_discover()})
            return
        if path == "/api/mdns":
            self._send_json(
                {"available": discovery.mdns_available(),
                 "services": discovery.mdns_discover()}
            )
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._host_ok():
            self._send_json({"error": "forbidden host"}, 403)
            return
        body = self._read_body()
        if not self._token_ok(body):
            self._send_json({"error": "invalid token"}, 403)
            return
        path = urlparse(self.path).path

        try:
            if path == "/api/wol":
                mac = body.get("mac")
                if not mac:
                    self._send_json({"error": "mac required"}, 400)
                    return
                control.wake_on_lan(mac, body.get("broadcast", "255.255.255.255"))
                self._send_json({"ok": True, "sent_to": mac})
                return
            if path == "/api/media":
                result = control.media_command(
                    body["location"], body["control_url"],
                    body["command"], body.get("value"),
                )
                self._send_json({"ok": True, "response": result[:2000]})
                return
        except (KeyError, ValueError) as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        except OSError as exc:
            self._send_json({"error": f"network error: {exc}"}, 502)
            return
        self._send_json({"error": "not found"}, 404)


def main() -> None:
    parser = argparse.ArgumentParser(description="HoloVision LAN Ops Center")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default loopback; do not expose publicly)")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true",
                        help="don't auto-open the browser")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), OpsHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"HoloVision Ops Center v{__version__}")
    print(f"  Serving on {url}")
    print(f"  Local IP: {net.get_local_ip()}   Subnet: {net.get_subnet()}")
    print(f"  mDNS (zeroconf) available: {discovery.mdns_available()}")
    print("  Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
