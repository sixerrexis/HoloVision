"""Device & service discovery: ping/ARP sweep, TCP port scan, SSDP/UPnP, mDNS.

Everything here stays on the local link. Nothing is sent to a third-party
cloud service. Standard library only, except optional `zeroconf` for mDNS which
is auto-detected and gracefully skipped if absent.
"""

from __future__ import annotations

import concurrent.futures
import platform
import re
import socket
import struct
import subprocess
import time
import urllib.request
from xml.etree import ElementTree as ET

from . import net

# Common ports worth probing on a home LAN, with friendly service labels.
COMMON_PORTS: dict[int, str] = {
    22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 139: "SMB", 443: "HTTPS",
    445: "SMB", 515: "Printer", 554: "RTSP", 631: "IPP/Print", 1883: "MQTT",
    1900: "SSDP/UPnP", 2323: "IoT-Telnet", 3389: "RDP", 5000: "UPnP/HTTP",
    5353: "mDNS", 548: "AFP", 8008: "Chromecast", 8009: "Chromecast",
    8060: "Roku", 8080: "HTTP-alt", 8443: "HTTPS-alt", 8883: "MQTT-TLS",
    9100: "RAW-Print", 32400: "Plex", 62078: "Apple-sync",
}


def _ping_cmd(ip: str) -> list[str]:
    if platform.system() == "Windows":
        return ["ping", "-n", "1", "-w", "800", ip]
    # -c1 one echo, -W1 one-second wait (Linux); macOS uses -t for ttl so keep -W.
    return ["ping", "-c", "1", "-W", "1", ip]


def ping(ip: str) -> float | None:
    """Return round-trip time in ms, or None if the host does not answer."""
    try:
        proc = subprocess.run(
            _ping_cmd(ip), capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    m = re.search(r"time[=<]\s*([\d.]+)\s*ms", proc.stdout)
    return float(m.group(1)) if m else 0.0


def sweep(subnet: str | None = None, workers: int = 128) -> list[dict]:
    """Ping-sweep a subnet and merge with the ARP cache. Returns device dicts."""
    subnet = subnet or net.get_subnet()
    hosts = net.hosts_in(subnet)
    alive: dict[str, dict] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        results = ex.map(lambda ip: (ip, ping(ip)), hosts)
        for ip, rtt in results:
            if rtt is not None:
                alive[ip] = {"ip": ip, "rtt_ms": rtt}

    # Fold in ARP entries (catches hosts that ignore ICMP but answered ARP).
    arp = net.arp_table()
    for ip, mac in arp.items():
        if ip in net.hosts_in(subnet) or ip in alive:
            entry = alive.setdefault(ip, {"ip": ip, "rtt_ms": None})
            entry["mac"] = mac
            entry["vendor"] = net.mac_vendor(mac)

    for ip, entry in alive.items():
        entry.setdefault("mac", None)
        entry.setdefault("vendor", None)
        entry["hostname"] = net.reverse_dns(ip)

    return sorted(alive.values(), key=lambda d: tuple(int(x) for x in d["ip"].split(".")))


def _probe_port(ip: str, port: int, timeout: float) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((ip, port)) == 0


def scan_ports(
    ip: str, ports: list[int] | None = None, timeout: float = 0.6, workers: int = 64
) -> list[dict]:
    """TCP connect-scan (no root needed). Returns list of open ports w/ labels."""
    ports = ports or list(COMMON_PORTS)
    open_ports: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_probe_port, ip, p, timeout): p for p in ports}
        for fut in concurrent.futures.as_completed(futs):
            p = futs[fut]
            try:
                if fut.result():
                    open_ports.append({"port": p, "service": COMMON_PORTS.get(p, "?")})
            except OSError:
                pass
    return sorted(open_ports, key=lambda d: d["port"])


# --------------------------------------------------------------------------- #
# SSDP / UPnP
# --------------------------------------------------------------------------- #
SSDP_ADDR = ("239.255.255.250", 1900)
_SSDP_MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    "ST: ssdp:all\r\n\r\n"
)


def ssdp_discover(timeout: float = 3.0) -> list[dict]:
    """Broadcast an SSDP M-SEARCH and collect unique UPnP device descriptions."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    try:
        sock.sendto(_SSDP_MSEARCH.encode("ascii"), SSDP_ADDR)
    except OSError:
        sock.close()
        return []

    seen: dict[str, dict] = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65507)
        except socket.timeout:
            break
        except OSError:
            break
        headers = _parse_ssdp(data.decode("utf-8", "replace"))
        location = headers.get("location")
        if location and location not in seen:
            seen[location] = {
                "ip": addr[0],
                "location": location,
                "st": headers.get("st", ""),
                "server": headers.get("server", ""),
            }
    sock.close()

    for info in seen.values():
        info.update(_describe_upnp(info["location"]))
    return list(seen.values())


def _parse_ssdp(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip().lower()] = v.strip()
    return out


def _describe_upnp(location: str) -> dict:
    """Fetch and parse a UPnP device description XML for name + services."""
    try:
        with urllib.request.urlopen(location, timeout=3) as resp:
            xml = resp.read()
    except OSError:
        return {"friendly_name": None, "device_type": None, "services": []}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {"friendly_name": None, "device_type": None, "services": []}

    ns = re.match(r"\{.*\}", root.tag)
    ns = ns.group(0) if ns else ""
    dev = root.find(f"{ns}device")
    if dev is None:
        return {"friendly_name": None, "device_type": None, "services": []}

    def text_of(tag: str) -> str | None:
        el = dev.find(f"{ns}{tag}")
        return el.text if el is not None else None

    services = []
    for svc in dev.iter(f"{ns}service"):
        st = svc.find(f"{ns}serviceType")
        cu = svc.find(f"{ns}controlURL")
        services.append(
            {
                "type": st.text if st is not None else None,
                "control_url": cu.text if cu is not None else None,
            }
        )
    return {
        "friendly_name": text_of("friendlyName"),
        "device_type": text_of("deviceType"),
        "manufacturer": text_of("manufacturer"),
        "model": text_of("modelName"),
        "services": services,
    }


# --------------------------------------------------------------------------- #
# mDNS (optional, needs `zeroconf`)
# --------------------------------------------------------------------------- #
_MDNS_SERVICES = [
    "_googlecast._tcp.local.", "_airplay._tcp.local.", "_raop._tcp.local.",
    "_spotify-connect._tcp.local.", "_http._tcp.local.", "_ipp._tcp.local.",
    "_printer._tcp.local.", "_hap._tcp.local.", "_homekit._tcp.local.",
    "_sonos._tcp.local.", "_smb._tcp.local.", "_ssh._tcp.local.",
]


def mdns_available() -> bool:
    try:
        import zeroconf  # noqa: F401
        return True
    except ImportError:
        return False


def mdns_discover(timeout: float = 3.0) -> list[dict]:
    """Browse common mDNS/Bonjour service types. Empty list if zeroconf absent."""
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        return []

    found: list[dict] = []

    class _Listener(ServiceListener):
        def add_service(self, zc, type_, name):  # noqa: D401,N802
            info = zc.get_service_info(type_, name, timeout=1500)
            if not info:
                return
            addrs = [socket.inet_ntoa(a) for a in info.addresses if len(a) == 4]
            found.append(
                {
                    "name": name,
                    "type": type_,
                    "addresses": addrs,
                    "port": info.port,
                    "server": info.server,
                }
            )

        def update_service(self, *a):  # noqa: N802
            pass

        def remove_service(self, *a):  # noqa: N802
            pass

    zc = Zeroconf()
    listener = _Listener()
    browsers = [ServiceBrowser(zc, svc, listener) for svc in _MDNS_SERVICES]
    time.sleep(timeout)
    for b in browsers:
        b.cancel()
    zc.close()
    return found
