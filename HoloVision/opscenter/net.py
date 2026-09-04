"""Low-level network helpers: local IP/subnet detection, ARP table parsing,
and a small offline MAC-vendor lookup. Standard library only."""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess

# A tiny built-in OUI (first 3 MAC bytes) -> vendor map. Offline and partial by
# design; enough to recognise the most common device makers on a home LAN.
# Format keys are uppercase, no separators.
_OUI = {
    "FCFBFB": "Cisco", "001A11": "Google", "F4F5D8": "Google", "3C5AB4": "Google",
    "DA0F00": "Apple", "F0F61C": "Apple", "A4B197": "Apple", "8866A5": "Apple",
    "AC BC 32".replace(" ", ""): "Apple", "D0817A": "Apple",
    "B827EB": "Raspberry Pi", "DC A6 32".replace(" ", ""): "Raspberry Pi",
    "E45F01": "Raspberry Pi", "2CCF67": "Raspberry Pi",
    "001788": "Philips Hue", "ECB5FA": "Philips Hue",
    "18B430": "Nest", "641666": "Nest",
    "50C7BF": "TP-Link", "9C5322": "TP-Link", "E848B8": "TP-Link",
    "44650D": "Amazon", "68 37 E9".replace(" ", ""): "Amazon", "FCA667": "Amazon",
    "000C43": "Samsung", "8CC8CD": "Samsung", "F0728C": "Samsung",
    "00 1E 8C".replace(" ", ""): "ASUS", "AC22 0B".replace(" ", ""): "ASUS",
    "B0A737": "Roku", "CC6DA0": "Roku",
    "D8EB46": "Sonos", "5CAAFD": "Sonos", "949F3E": "Sonos",
    "00 21 6A".replace(" ", ""): "Intel", "3C970E": "Intel",
}


def get_local_ip() -> str:
    """Best-effort primary outbound IPv4 address (no packets are actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def get_subnet(prefix: int = 24) -> str:
    """Return the local /prefix network in CIDR form, e.g. '192.168.1.0/24'."""
    ip = get_local_ip()
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    return str(net)


def hosts_in(subnet: str) -> list[str]:
    return [str(h) for h in ipaddress.ip_network(subnet, strict=False).hosts()]


def normalize_mac(mac: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", mac).upper()


def mac_vendor(mac: str) -> str:
    key = normalize_mac(mac)[:6]
    return _OUI.get(key, "Unknown")


def reverse_dns(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None


def arp_table() -> dict[str, str]:
    """Return {ip: MAC} from the OS ARP cache. Works on Linux, macOS, Windows."""
    table: dict[str, str] = {}
    system = platform.system()
    try:
        if system == "Linux":
            with open("/proc/net/arp", encoding="ascii") as fh:
                next(fh, None)  # header
                for line in fh:
                    cols = line.split()
                    if len(cols) >= 4 and cols[3] != "00:00:00:00:00:00":
                        table[cols[0]] = cols[3].upper()
            if table:
                return table
        # macOS / Windows / Linux fallback: parse `arp -a`
        out = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=5
        ).stdout
        for m in re.finditer(
            r"(\d{1,3}(?:\.\d{1,3}){3}).*?([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})",
            out,
        ):
            table[m.group(1)] = m.group(2).replace("-", ":").upper()
    except (OSError, subprocess.SubprocessError, StopIteration):
        pass
    return table
