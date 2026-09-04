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
| Smart-home hub | **MQTT 3.1.1** (built-in broker) | One-click bundled broker — your devices' "post office". No install, no admin |
| Smart-home control | **MQTT 3.1.1** (built-in client) | Watch live device telemetry, publish control commands. No cloud, no `pip install` |

## Smart-home (MQTT) — start here

### What's a broker (a.k.a. the "hub")?

A **broker** is a **post office for your smart-home devices**. Devices don't talk
to each other directly — each one drops off messages ("I'm a lamp, I just turned
ON") and subscribes to the mail it cares about ("tell me when someone sends a
command to `lamp/set`"). The broker sits in the middle and delivers each message
to whoever asked for it. **Nothing works until a broker is running.**

HoloVision **bundles its own broker** so you don't have to install anything.

### One-click setup

1. In the **MQTT Smart-Home Control** panel, click **▶ Start Hub & Connect**.
   That starts the bundled broker *and* connects the panel to it, watching all
   topics (`#`). The badge turns *running / connected*.
2. **Point your devices at the hub.** The panel shows the address to use — your
   computer's LAN IP and port `1883` (e.g. `192.168.1.20:1883`). In each device's
   settings (Tasmota, ESPHome, Zigbee2MQTT, a Home-Assistant MQTT integration),
   set the MQTT broker/host to that address. They'll appear in the **Live feed**
   as they connect and report state.
3. **Send a command.** Find a device's *set* topic in the feed, then use the
   **Publish** box — Topic + Payload. Examples:
   - Zigbee2MQTT light on → topic `zigbee2mqtt/Living Room Lamp/set`,
     payload `{"state":"ON"}` (or `{"brightness":128}` to dim).
   - Tasmota plug on → topic `cmnd/tasmota_plug/POWER`, payload `ON`.
   - ESPHome relay → topic `esphome/DEVICE/switch/relay/command`, payload `ON`.

   The **Quick presets** buttons pre-fill these shapes — replace `FRIENDLY_NAME` /
   `DEVICE` with your device's actual name. Tick **retain** for state the broker
   should remember across reconnects (use sparingly).

> **Tip:** don't know a device's command topic? Watch the feed while you toggle
> the device in its own app — its status topic reveals the naming, and the `/set`
> (or `cmnd/…`) variant is what you publish to.

### Already have a broker?

If you run Mosquitto or Home Assistant's broker, skip the hub: expand **Connect to
a different broker (advanced)**, enter its host/port (and username/password if
needed), and Connect. The bundled hub is the zero-setup option; Mosquitto is the
natural upgrade once you want persistence, TLS, and access control.

## Security model

- Server binds to **loopback only** by default.
- Every control action (POST) requires a **per-run session token** injected into
  the UI at page load — so a stray web page hitting `127.0.0.1` can't drive it.
- **Host-header allow-list** rejects DNS-rebinding attempts.
- Do **not** pass `--host 0.0.0.0` unless you add your own auth; this tool is
  designed for a single trusted machine on a network you own.
- The **bundled hub (broker)** listens on `0.0.0.0:1883` **on purpose** — your
  smart-home devices, which live elsewhere on the LAN, must be able to reach it
  (a loopback-only broker no device could connect to would be useless). It is an
  open, unauthenticated broker, so run it only on a home/trusted network. For an
  untrusted network, use Mosquitto with a username/password and TLS instead, and
  point the panel at it via the *advanced* connect form.
- Only scan and control devices on networks you are authorized to operate.

## Architecture

```
HoloVision/
├── server.py              # loopback HTTP server, JSON API, token + host guards
├── opscenter/
│   ├── net.py             # local IP/subnet, ARP table, MAC-vendor, reverse-DNS
│   ├── discovery.py       # ping sweep, TCP port scan, SSDP/UPnP, mDNS
│   ├── control.py         # Wake-on-LAN, UPnP AV media commands (SOAP)
│   ├── mqtt.py            # dependency-free MQTT 3.1.1 client + broker session
│   └── broker.py          # bundled MQTT broker ("the hub"): pub/sub, wildcards, retained
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
| POST | `/api/hub/start` | `{host?, port?}` → start the bundled broker (token required) |
| POST | `/api/hub/stop` | stop the bundled broker (token required) |
| GET | `/api/hub/status` | bundled-broker status: clients, retained, messages routed |

## Roadmap (natural next protocols to add — all local-first)

- **Matter / Home Assistant local API** for smart-home actions without vendor cloud.
- **Chromecast** control via the CASTv2 protocol (cast/stop/volume).
- **SSH agent** for real OS power states (shutdown/reboot) on opted-in hosts.
- Continuous telemetry (latency history, up/down transitions, alerts).
