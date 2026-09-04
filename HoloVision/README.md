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

## Desktop shortcut

Create a double-clickable shortcut so you don't need a terminal each time:

```bash
cd HoloVision
python3 make_shortcut.py            # add it
python3 make_shortcut.py --remove   # remove it later
```

- **Linux** → `~/.local/share/applications/holovision-ops.desktop` and a copy on
  your Desktop. On first launch the file manager may ask you to *Allow Launching*
  — accept once. (Runs in a terminal so you can see the URL and press Ctrl+C.)
- **macOS** → `~/Desktop/HoloVision Ops Center.command`. Double-click to launch;
  the first time, right-click → **Open** to clear Gatekeeper.
- **Windows** → a `.lnk` on your Desktop (created via PowerShell).

Double-clicking starts the local server and opens `http://127.0.0.1:8787`.

## What it does today

| Capability | Protocol | Notes |
|---|---|---|
| Subnet map | ICMP ping sweep + ARP cache | Alive hosts, MAC, vendor (offline OUI), reverse-DNS, latency |
| Port / service inspection | TCP connect scan | Common ports labelled (SSH, HTTP, MQTT, Chromecast, Roku, Plex, print…). No root needed |
| Service discovery | SSDP / UPnP | Fetches device descriptions → friendly name, model, services |
| Service discovery | mDNS / Bonjour | Optional (`zeroconf`): Cast, AirPlay, HomeKit, Sonos, printers |
| Power control | Wake-on-LAN | Magic packet to a device's MAC |
| Media control | UPnP AVTransport / RenderingControl | Play / Pause / Stop / Next / Prev, volume, mute on TVs, speakers, DLNA renderers |
| Smart-home control | **MQTT 3.1.1** (built-in client) | Connect to a local broker, watch live device telemetry, publish control commands. No cloud, no `pip install` |

## Using the MQTT smart-home panel

The panel talks to a **local MQTT broker** — the hub most DIY smart-home stacks
already run (Mosquitto, Home Assistant's built-in broker, Zigbee2MQTT, Tasmota,
ESPHome). Everything stays on your LAN.

1. **Point it at your broker.** In the *MQTT Smart-Home Control* panel, enter the
   broker **host** (e.g. your Home Assistant IP or `localhost`) and **port**
   (`1883` plain, or your TLS-terminated port). Add **username/password** only if
   your broker requires them. Click **Connect** — the badge turns *connected*.
2. **Watch telemetry.** Set the **Subscribe topic** to `#` to see everything, or
   scope it (`zigbee2mqtt/#`, `homeassistant/#`, `tasmota/#`). The **Live feed**
   streams messages as devices report state; use the **filter** box to narrow by
   topic.
3. **Send a command.** Find a device's *set* topic in the feed, then use the
   **Publish** box — Topic + Payload. Examples:
   - Zigbee2MQTT light on → topic `zigbee2mqtt/Living Room Lamp/set`,
     payload `{"state":"ON"}` (or `{"brightness":128}` to dim).
   - Tasmota plug on → topic `cmnd/tasmota_plug/POWER`, payload `ON`.
   - ESPHome relay → topic `esphome/DEVICE/switch/relay/command`, payload `ON`.

   The **Quick presets** buttons pre-fill these shapes — replace `FRIENDLY_NAME` /
   `DEVICE` with your device's actual name. Tick **retain** for state the broker
   should remember across reconnects (use sparingly).

> **Tip:** if you don't know a device's command topic, watch the feed while you
> toggle the device in its own app — its status topic reveals the naming, and the
> `/set` (or `cmnd/…`) variant is what you publish to.

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
│   ├── control.py         # Wake-on-LAN, UPnP AV media commands (SOAP)
│   └── mqtt.py            # dependency-free MQTT 3.1.1 client + broker session
├── web/index.html         # self-contained dashboard UI (no external assets)
├── make_shortcut.py       # create/remove the desktop shortcut (Linux/macOS/Win)
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
| POST | `/api/mqtt/connect` | `{host, port, username?, password?, topic?}` → open broker session (token required) |
| POST | `/api/mqtt/subscribe` | `{topic}` → subscribe (token required) |
| POST | `/api/mqtt/publish` | `{topic, payload, retain?}` → send command (token required) |
| POST | `/api/mqtt/disconnect` | close broker session (token required) |
| GET | `/api/mqtt/messages?since=` | poll live feed since a sequence number |
| GET | `/api/mqtt/status` | broker connection status |

## Roadmap (natural next protocols to add — all local-first)

- **Matter / Home Assistant local API** for smart-home actions without vendor cloud.
- **Chromecast** control via the CASTv2 protocol (cast/stop/volume).
- **SSH agent** for real OS power states (shutdown/reboot) on opted-in hosts.
- Continuous telemetry (latency history, up/down transitions, alerts).
