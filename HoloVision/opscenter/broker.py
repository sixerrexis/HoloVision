"""A tiny, dependency-free MQTT 3.1.1 broker bundled with HoloVision.

This is the "post office" your smart-home devices connect to. It runs entirely
inside the HoloVision folder — no separate install, no admin rights, no config
files. QoS 0, wildcard subscriptions (+ and #), and retained messages, which
covers what Zigbee2MQTT / Tasmota / ESPHome / Home Assistant use day to day.

For a bigger setup you can graduate to Mosquitto later; the client panel talks
to either one identically.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

from .mqtt import _encode_len, _encode_str  # reuse the wire helpers


def topic_matches(filt: str, topic: str) -> bool:
    """MQTT topic-filter match, honouring '+' (one level) and '#' (rest)."""
    fs = filt.split("/")
    ts = topic.split("/")
    for i, part in enumerate(fs):
        if part == "#":
            return True
        if i >= len(ts):
            return False
        if part == "+":
            continue
        if part != ts[i]:
            return False
    return len(fs) == len(ts)


class _Client:
    __slots__ = ("sock", "addr", "cid", "subs", "lock", "alive")

    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.cid = ""
        self.subs: list[str] = []
        self.lock = threading.Lock()
        self.alive = True

    def send(self, data: bytes) -> None:
        with self.lock:
            if self.alive:
                self.sock.sendall(data)


class Broker:
    """Minimal threaded MQTT broker. Start once, serves the whole LAN."""

    def __init__(self, host: str = "0.0.0.0", port: int = 1883):
        self.host = host
        self.port = port
        self._srv: socket.socket | None = None
        self._clients: set[_Client] = set()
        self._retained: dict[str, bytes] = {}
        self._lock = threading.Lock()
        self._running = False
        self._accept_thread: threading.Thread | None = None
        self.started_at: float | None = None
        self.messages_routed = 0
        self.error: str | None = None

    # -- lifecycle -------------------------------------------------------- #
    def start(self) -> None:
        if self._running:
            return
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(64)
        srv.settimeout(1.0)
        self._srv = srv
        self._running = True
        self.error = None
        self.started_at = time.time()
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        self._running = False
        with self._lock:
            for c in list(self._clients):
                c.alive = False
                try:
                    c.sock.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None
        self.started_at = None

    def status(self) -> dict:
        with self._lock:
            clients = [
                {"id": c.cid or "(anon)", "addr": c.addr[0], "subs": list(c.subs)}
                for c in self._clients
            ]
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "clients": clients,
            "client_count": len(clients),
            "retained": len(self._retained),
            "messages_routed": self.messages_routed,
            "uptime_s": int(time.time() - self.started_at) if self.started_at else 0,
            "error": self.error,
        }

    # -- connection handling ---------------------------------------------- #
    def _accept_loop(self) -> None:
        while self._running and self._srv:
            try:
                sock, addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(sock, addr), daemon=True).start()

    def _serve(self, sock: socket.socket, addr) -> None:
        client = _Client(sock, addr)
        try:
            sock.settimeout(65)
            while self._running:
                first, body = self._read_packet(sock)
                ptype = first & 0xF0
                if ptype == 0x10:      # CONNECT
                    client.cid = self._parse_connect_cid(body)
                    sock.sendall(bytes([0x20, 0x02, 0x00, 0x00]))  # CONNACK ok
                    with self._lock:
                        self._clients.add(client)
                elif ptype == 0x80:    # SUBSCRIBE (0x82 header, masked to 0x80)
                    self._handle_subscribe(client, body)
                elif ptype == 0x30:    # PUBLISH
                    self._handle_publish(body, retain=bool(first & 0x01))
                elif ptype == 0xC0:    # PINGREQ
                    sock.sendall(bytes([0xD0, 0x00]))  # PINGRESP
                elif ptype == 0xE0:    # DISCONNECT
                    break
                # other packet types (UNSUBSCRIBE, etc.) ignored
        except (OSError, ConnectionError, IndexError, struct.error):
            pass
        finally:
            client.alive = False
            with self._lock:
                self._clients.discard(client)
            try:
                sock.close()
            except OSError:
                pass

    # -- packet handlers -------------------------------------------------- #
    def _handle_subscribe(self, client: _Client, body: bytes) -> None:
        pid = body[:2]
        i = 2
        granted = bytearray()
        added: list[str] = []
        while i < len(body):
            tlen = struct.unpack("!H", body[i:i + 2])[0]
            i += 2
            topic = body[i:i + tlen].decode("utf-8", "replace")
            i += tlen
            i += 1  # requested QoS byte
            if topic not in client.subs:
                client.subs.append(topic)
            added.append(topic)
            granted.append(0x00)  # granted QoS 0
        client.send(bytes([0x90]) + _encode_len(len(pid) + len(granted)) + pid + bytes(granted))
        # deliver matching retained messages to the new subscriber
        with self._lock:
            retained = list(self._retained.items())
        for topic, payload in retained:
            if any(topic_matches(f, topic) for f in added):
                self._deliver(client, topic, payload, retain=True)

    def _handle_publish(self, body: bytes, retain: bool = False) -> None:
        tlen = struct.unpack("!H", body[:2])[0]
        topic = body[2:2 + tlen].decode("utf-8", "replace")
        payload = body[2 + tlen:]
        # (QoS 0 assumed; if a device used QoS 1 the packet id would sit here —
        # we keep it simple and treat everything as QoS 0.)
        if not topic:
            return
        with self._lock:
            self.messages_routed += 1
            if retain:
                # A zero-length retained payload clears the stored value (spec).
                if payload:
                    self._retained[topic] = payload
                else:
                    self._retained.pop(topic, None)
            targets = [
                c for c in self._clients
                if any(topic_matches(f, topic) for f in c.subs)
            ]
        for c in targets:
            self._deliver(c, topic, payload, retain=False)

    def _deliver(self, client: _Client, topic: str, payload: bytes,
                 retain: bool) -> None:
        header = 0x30 | (0x01 if retain else 0x00)
        varhdr = _encode_str(topic)
        pkt = bytes([header]) + _encode_len(len(varhdr) + len(payload)) + varhdr + payload
        try:
            client.send(pkt)
        except OSError:
            client.alive = False

    # -- low-level -------------------------------------------------------- #
    @staticmethod
    def _parse_connect_cid(body: bytes) -> str:
        # skip protocol name + level(1) + flags(1) + keepalive(2), then client id
        i = 0
        nlen = struct.unpack("!H", body[i:i + 2])[0]
        i += 2 + nlen + 1 + 1 + 2
        clen = struct.unpack("!H", body[i:i + 2])[0]
        i += 2
        return body[i:i + clen].decode("utf-8", "replace")

    @staticmethod
    def _read_packet(sock: socket.socket) -> tuple[int, bytes]:
        """Return (full first header byte, body). Caller masks 0xF0 for the type
        and keeps the low nibble for flags such as PUBLISH's retain bit."""
        first = sock.recv(1)
        if not first:
            raise ConnectionError("socket closed")
        mult, length = 1, 0
        while True:
            b = sock.recv(1)
            if not b:
                raise ConnectionError("socket closed")
            length += (b[0] & 0x7F) * mult
            if not (b[0] & 0x80):
                break
            mult *= 128
        body = b""
        while len(body) < length:
            chunk = sock.recv(length - len(body))
            if not chunk:
                raise ConnectionError("socket closed")
            body += chunk
        return first[0], body


class BrokerManager:
    """Process-wide single broker for the web server to start/stop."""

    def __init__(self):
        self._broker: Broker | None = None
        self._lock = threading.Lock()

    def start(self, host: str = "0.0.0.0", port: int = 1883) -> dict:
        with self._lock:
            if self._broker and self._broker._running:
                return self._broker.status()
            broker = Broker(host, int(port))
            try:
                broker.start()
            except OSError as exc:
                raise ConnectionError(
                    f"Could not start hub on {host}:{port} — {exc}. "
                    "Another broker may already be using that port."
                ) from exc
            self._broker = broker
            return broker.status()

    def stop(self) -> dict:
        with self._lock:
            if self._broker:
                self._broker.stop()
            return {"running": False}

    def status(self) -> dict:
        with self._lock:
            if not self._broker:
                return {"running": False, "clients": [], "client_count": 0}
            return self._broker.status()
