# HoloVision — Local Network Operations Center

A **cross-protocol, local-first** operations center for your Wi-Fi/LAN. It maps
the subnet, inspects device telemetry and open service ports, and executes
control commands (power-on, media controls) — **all from your browser**, with
**no traffic routed through third-party cloud servers.**

## Why a local server + browser (not a pure web page)

A browser tab is sandboxed: JavaScript **cannot** ARP-scan the subnet,
port-scan hosts, read the ARP cache, do SSDP/mDNS multicast, or send
Wake-on-LAN packets. So HoloVision runs a **tiny local server** that does the
privileged network work, and your **browser is the UI**. There is no native app
to install and nothing leaves your machine — the server binds to `127.0.0.1`.

```
┌────────────┐   HTTP (localhost)   ┌───────────────────┐   raw LAN protocols
│  Browser   │ ───────────────────▶ │  server.py         │ ──────────────────▶  your devices
│  (the UI)  │ ◀─────────────────── │  (Python stdlib)   │   ICMP · ARP · TCP
└────────────┘        JSON          │  opscenter/*       │   SSDP · mDNS · WoL · UPnP
                                     └───────────────────┘
```

## Run it

Requires Python 3.9+. No install needed for the core:

```bash
cd HoloVision
python3 server.py
```

It prints a URL (default `http://127.0.0.1:8787`) and opens your browser.
Then click **Scan subnet**, then **SSDP/UPnP** and **mDNS** to enrich results.

Optional — enable mDNS/Bonjour discovery (Chromecast, AirPlay, HomeKit, Sonos):

```bash
pip install -r requirements.txt   # installs zeroconf
```

Flags: `--port N`, `--host ADDR` (keep loopback), `--no-browser`.

## What it does today

| Capability | Protocol | Notes |
|---|---|---|
| Subnet map | ICMP ping sweep + ARP cache | Alive hosts, MAC, vendor (offline OUI), reverse-DNS, latency |
| Port / service inspection | TCP connect scan | Common ports labelled (SSH, HTTP, MQTT, Chromecast, Roku, Plex, print…). No root needed |
| Service discovery | SSDP / UPnP | Fetches device descriptions → friendly name, model, services |
| Service discovery | mDNS / Bonjour | Optional (`zeroconf`): Cast, AirPlay, HomeKit, Sonos, printers |
| Power control | Wake-on-LAN | Magic packet to a device's MAC |
| Media control | UPnP AVTransport / RenderingControl | Play / Pause / Stop / Next / Prev, volume, mute on TVs, speakers, DLNA renderers |

## Security model

- Server binds to **loopback only** by default.
- Every control action (POST) requires a **per-run session token** injected into
  the UI at page load — so a stray web page hitting `127.0.0.1` can't drive it.
- **Host-header allow-list** rejects DNS-rebinding attempts.
- Do **not** pass `--host 0.0.0.0` unless you add your own auth; this tool is
  designed for a single trusted machine on a network you own.
- Only scan and control devices on networks you are authorized to operate.

## Architecture

```
HoloVision/
├── server.py              # loopback HTTP server, JSON API, token + host guards
├── opscenter/
│   ├── net.py             # local IP/subnet, ARP table, MAC-vendor, reverse-DNS
│   ├── discovery.py       # ping sweep, TCP port scan, SSDP/UPnP, mDNS
│   └── control.py         # Wake-on-LAN, UPnP AV media commands (SOAP)
├── web/index.html         # self-contained dashboard UI (no external assets)
└── requirements.txt       # optional: zeroconf for mDNS
```

### API (localhost)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/info` | local IP, subnet, mDNS availability |
| GET | `/api/scan?subnet=` | subnet device map |
| GET | `/api/ports?host=` | TCP port scan of one host |
| GET | `/api/ssdp` | SSDP/UPnP devices |
| GET | `/api/mdns` | mDNS services |
| POST | `/api/wol` | `{mac}` → Wake-on-LAN (token required) |
| POST | `/api/media` | `{location, control_url, command, value}` → UPnP control (token required) |

## Roadmap (natural next protocols to add — all local-first)

- **MQTT** client panel (subscribe/publish to a local broker or Home Assistant).
- **Matter / Home Assistant local API** for smart-home actions without vendor cloud.
- **Chromecast** control via the CASTv2 protocol (cast/stop/volume).
- **SSH agent** for real OS power states (shutdown/reboot) on opted-in hosts.
- Continuous telemetry (latency history, up/down transitions, alerts).
