"""Local-first control actions: Wake-on-LAN and UPnP AV media control.

No cloud, no vendor account. Wake-on-LAN speaks broadcast UDP; media control
speaks SOAP directly to the device's own UPnP AVTransport / RenderingControl
endpoints. Standard library only.
"""

from __future__ import annotations

import socket
import urllib.parse
import urllib.request

from . import net

# --------------------------------------------------------------------------- #
# Wake-on-LAN
# --------------------------------------------------------------------------- #


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a Wake-on-LAN magic packet to the given MAC address."""
    hexmac = net.normalize_mac(mac)
    if len(hexmac) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    packet = b"\xff" * 6 + bytes.fromhex(hexmac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast, port))


# --------------------------------------------------------------------------- #
# UPnP AV media control (SOAP)
# --------------------------------------------------------------------------- #
_AVT = "urn:schemas-upnp-org:service:AVTransport:1"
_RC = "urn:schemas-upnp-org:service:RenderingControl:1"

_SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    "<s:Body><u:{action} xmlns:u=\"{service}\">{args}</u:{action}></s:Body>"
    "</s:Envelope>"
)


def _soap(control_url: str, service: str, action: str, args: dict[str, str]) -> str:
    body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
    payload = _SOAP_ENVELOPE.format(action=action, service=service, args=body)
    req = urllib.request.Request(
        control_url,
        data=payload.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{service}#{action}"',
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8", "replace")


def _resolve_control_url(location: str, control_url: str) -> str:
    """UPnP control URLs may be relative to the device description location."""
    return urllib.parse.urljoin(location, control_url)


def media_command(
    location: str, control_url: str, command: str, value: str | None = None
) -> str:
    """Issue an AVTransport / RenderingControl command to a UPnP renderer.

    `location` is the device-description URL (for resolving relative paths).
    `control_url` is the AVTransport (or RenderingControl for volume) controlURL.
    `command` is one of: play, pause, stop, next, previous, setvolume, mute, unmute.
    """
    url = _resolve_control_url(location, control_url)
    cmd = command.lower()
    if cmd == "play":
        return _soap(url, _AVT, "Play", {"InstanceID": "0", "Speed": "1"})
    if cmd == "pause":
        return _soap(url, _AVT, "Pause", {"InstanceID": "0"})
    if cmd == "stop":
        return _soap(url, _AVT, "Stop", {"InstanceID": "0"})
    if cmd == "next":
        return _soap(url, _AVT, "Next", {"InstanceID": "0"})
    if cmd == "previous":
        return _soap(url, _AVT, "Previous", {"InstanceID": "0"})
    if cmd == "setvolume":
        vol = str(max(0, min(100, int(value or "20"))))
        return _soap(url, _RC, "SetVolume",
                     {"InstanceID": "0", "Channel": "Master", "DesiredVolume": vol})
    if cmd in ("mute", "unmute"):
        return _soap(url, _RC, "SetMute",
                     {"InstanceID": "0", "Channel": "Master",
                      "DesiredMute": "1" if cmd == "mute" else "0"})
    raise ValueError(f"Unknown media command: {command!r}")
