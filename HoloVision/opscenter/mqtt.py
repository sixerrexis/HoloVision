"""Minimal, dependency-free MQTT 3.1.1 client for local smart-home control.

Speaks just enough of the protocol (CONNECT / SUBSCRIBE / PUBLISH / PING) to
inspect device telemetry and send control commands to a *local* broker
(Mosquitto, Home Assistant, Zigbee2MQTT, Tasmota, ESPHome…). QoS 0 only, which
is what home automation almost always uses. Nothing leaves the LAN.

The HTTP server keeps a single long-lived `Session` (a broker connection can't
live inside one request/response) and the browser polls it for messages.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

_PROTOCOL = b"MQTT"
_LEVEL = 0x04  # MQTT 3.1.1


def _encode_len(n: int) -> bytes:
    """MQTT variable-length 'remaining length' encoding."""
    out = bytearray()
    while True:
        digit = n % 128
        n //= 128
        if n > 0:
            digit |= 0x80
        out.append(digit)
        if n == 0:
            return bytes(out)


def _encode_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


class MiniMQTT:
    """A tiny threaded MQTT client. One connection, QoS 0."""

    def __init__(self, host: str, port: int = 1883, client_id: str | None = None,
                 username: str | None = None, password: str | None = None,
                 keepalive: int = 45, max_messages: int = 500):
        self.host = host
        self.port = port
        self.client_id = client_id or f"holovision-{int(time.time())}"
        self.username = username or None
        self.password = password or None
        self.keepalive = keepalive
        self.max_messages = max_messages

        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._rx_lock = threading.Lock()
        self._messages: list[dict] = []
        self._seq = 0
        self._pid = 0
        self._running = False
        self._reader: threading.Thread | None = None
        self._last_ping = 0.0
        self.status = "disconnected"
        self.error: str | None = None
        self.subscriptions: list[str] = []

    # -- connection ------------------------------------------------------- #
    def connect(self, timeout: float = 6.0) -> None:
        flags = 0x02  # clean session
        payload = _encode_str(self.client_id)
        if self.username:
            flags |= 0x80
            payload += _encode_str(self.username)
            if self.password:
                flags |= 0x40
                payload += _encode_str(self.password)
        varhdr = _encode_str(_PROTOCOL.decode()) + bytes([_LEVEL, flags]) + \
            struct.pack("!H", self.keepalive)
        pkt = bytes([0x10]) + _encode_len(len(varhdr) + len(payload)) + varhdr + payload

        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        sock.settimeout(timeout)
        sock.sendall(pkt)
        ptype, body = self._read_packet(sock)
        if ptype != 0x20 or len(body) < 2 or body[1] != 0x00:
            code = body[1] if len(body) > 1 else -1
            sock.close()
            raise ConnectionError(f"CONNACK refused (code {code})")

        self._sock = sock
        self._running = True
        self.status = "connected"
        self.error = None
        self._last_ping = time.time()
        sock.settimeout(1.0)
        self._reader = threading.Thread(target=self._loop, daemon=True)
        self._reader.start()

    def disconnect(self) -> None:
        self._running = False
        with self._lock:
            if self._sock:
                try:
                    self._sock.sendall(bytes([0xE0, 0x00]))
                except OSError:
                    pass
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
        self.status = "disconnected"

    # -- operations ------------------------------------------------------- #
    def subscribe(self, topic: str, qos: int = 0) -> None:
        self._pid = (self._pid + 1) & 0xFFFF
        payload = _encode_str(topic) + bytes([qos & 0x03])
        varhdr = struct.pack("!H", self._pid or 1)
        pkt = bytes([0x82]) + _encode_len(len(varhdr) + len(payload)) + varhdr + payload
        with self._lock:
            if not self._sock:
                raise ConnectionError("not connected")
            self._sock.sendall(pkt)
        if topic not in self.subscriptions:
            self.subscriptions.append(topic)

    def publish(self, topic: str, payload: str, retain: bool = False,
                qos: int = 0) -> None:
        header = 0x30 | (0x01 if retain else 0x00) | ((qos & 0x03) << 1)
        varhdr = _encode_str(topic)
        body = payload.encode("utf-8")
        if qos > 0:
            self._pid = (self._pid + 1) & 0xFFFF
            varhdr += struct.pack("!H", self._pid or 1)
        pkt = bytes([header]) + _encode_len(len(varhdr) + len(body)) + varhdr + body
        with self._lock:
            if not self._sock:
                raise ConnectionError("not connected")
            self._sock.sendall(pkt)

    def messages_since(self, seq: int) -> list[dict]:
        with self._rx_lock:
            return [m for m in self._messages if m["seq"] > seq]

    # -- internals -------------------------------------------------------- #
    def _read_packet(self, sock: socket.socket) -> tuple[int, bytes]:
        first = sock.recv(1)
        if not first:
            raise ConnectionError("socket closed")
        ptype = first[0] & 0xF0
        # decode remaining length
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
        return ptype, body

    def _handle_publish(self, body: bytes) -> None:
        if len(body) < 2:
            return
        tlen = struct.unpack("!H", body[:2])[0]
        topic = body[2:2 + tlen].decode("utf-8", "replace")
        payload = body[2 + tlen:]  # QoS 0 → no packet id
        with self._rx_lock:
            self._seq += 1
            self._messages.append({
                "seq": self._seq,
                "topic": topic,
                "payload": payload.decode("utf-8", "replace"),
                "bytes": len(payload),
                "ts": time.time(),
            })
            if len(self._messages) > self.max_messages:
                self._messages = self._messages[-self.max_messages:]

    def _loop(self) -> None:
        while self._running and self._sock:
            try:
                ptype, body = self._read_packet(self._sock)
                if ptype == 0x30:
                    self._handle_publish(body)
                # 0x90 SUBACK, 0xD0 PINGRESP, 0x40 PUBACK → ignore
            except socket.timeout:
                pass
            except (OSError, ConnectionError) as exc:
                if self._running:
                    self.status = "error"
                    self.error = str(exc)
                self._running = False
                break
            # keepalive ping
            if time.time() - self._last_ping > self.keepalive * 0.7:
                try:
                    with self._lock:
                        if self._sock:
                            self._sock.sendall(bytes([0xC0, 0x00]))
                    self._last_ping = time.time()
                except OSError:
                    self._running = False
                    break


class Session:
    """Holds the process-wide single MQTT client for the web server."""

    def __init__(self):
        self._client: MiniMQTT | None = None
        self._lock = threading.Lock()

    def connect(self, host: str, port: int = 1883, username: str | None = None,
                password: str | None = None, topic: str | None = None) -> dict:
        with self._lock:
            if self._client:
                self._client.disconnect()
            client = MiniMQTT(host, int(port), username=username, password=password)
            client.connect()
            if topic:
                for t in [s.strip() for s in topic.split(",") if s.strip()]:
                    client.subscribe(t)
            self._client = client
        return self.status()

    def disconnect(self) -> dict:
        with self._lock:
            if self._client:
                self._client.disconnect()
                self._client = None
        return {"status": "disconnected"}

    def subscribe(self, topic: str) -> dict:
        with self._lock:
            if not self._client:
                raise ConnectionError("not connected")
            self._client.subscribe(topic)
        return self.status()

    def publish(self, topic: str, payload: str, retain: bool = False) -> dict:
        with self._lock:
            if not self._client:
                raise ConnectionError("not connected")
            self._client.publish(topic, payload, retain=retain)
        return {"ok": True, "topic": topic}

    def messages(self, since: int = 0) -> dict:
        with self._lock:
            client = self._client
        if not client:
            return {"status": "disconnected", "messages": [], "last_seq": since}
        msgs = client.messages_since(since)
        last = msgs[-1]["seq"] if msgs else since
        return {
            "status": client.status,
            "error": client.error,
            "subscriptions": client.subscriptions,
            "messages": msgs,
            "last_seq": last,
        }

    def status(self) -> dict:
        with self._lock:
            client = self._client
        if not client:
            return {"status": "disconnected", "subscriptions": []}
        return {
            "status": client.status,
            "error": client.error,
            "host": client.host,
            "port": client.port,
            "subscriptions": client.subscriptions,
        }
