# BAAS capture agent

A small local service that lets the BAAS web kiosk read a fingerprint from a
DigitalPersona **U.are.U 4500** on **Linux**. It captures one image through
libfprint (`uru4000` driver) and returns it as a PNG. All matching happens on the
BAAS backend.

- Listens on `127.0.0.1:7501` only. It is never reachable from the network.
- Answers only the kiosk's own origin (`https://baas-app-kappa.vercel.app`), plus
  `http://localhost` and `http://127.0.0.1` on any port for development.
- Starts with the desktop session as a systemd user service.
- On Windows the kiosk uses the DigitalPersona Lite Client instead, not this agent.

## Install (Ubuntu 22.04+ / Pop!_OS / Debian 12+)

```bash
sudo apt install ./baas-capture-agent_0.1.0_all.deb
```

`apt` also installs libfprint and its udev rules, so the logged-in user can open
the reader without root. The service starts straight away for anyone logged in,
and for every user at their next login.

Check it is running and sees the reader:

```bash
systemctl --user status baas-capture-agent
curl http://127.0.0.1:7501/status
```

`"connected": true` with `"driver": "uru4000"` means the 4500 is ready.

The first time the kiosk calls the agent, Chrome may ask to allow access to
devices on the local network. Choose **Allow**.

## API

| Method | Path | Result |
|---|---|---|
| GET | `/status` | `{connected, device, driver, capturing, version}` |
| POST | `/capture` | Waits for a finger, then returns `{image (base64 PNG), width, height, device}` |
| POST | `/cancel` | Stops a capture in progress: `{cancelled}` |

Errors use the backend's shape, `{"detail": "..."}`:

| Status | Detail |
|---|---|
| 503 | Fingerprint reader not connected |
| 408 | No finger detected (after `BAAS_AGENT_TIMEOUT` seconds) |
| 409 | Reader is busy / Capture cancelled |
| 403 | Origin not allowed |

## Configuration

Edit `/etc/baas-capture-agent.conf`, then run
`systemctl --user restart baas-capture-agent`.

| Variable | Default | Meaning |
|---|---|---|
| `BAAS_AGENT_PORT` | `7501` | Local port |
| `BAAS_AGENT_ORIGINS` | `https://baas-app-kappa.vercel.app` | Kiosk origins, comma-separated |
| `BAAS_AGENT_TIMEOUT` | `30` | Seconds to wait for a finger |

## Troubleshooting

- `connected: false`: check that `lsusb` shows `05ba:000a` (U.are.U 4500), then
  unplug the reader and plug it back in.
- "libfprint is not available" in the log: run
  `sudo apt install gir1.2-fprint-2.0 libfprint-2-2`.
- To see the logs: `journalctl --user -u baas-capture-agent -f`.

## Develop

```bash
python3 -m unittest -v                        # tests use a fake reader, no hardware needed
python3 -m baas_capture_agent --port 7501     # needs libfprint installed
packaging/build-deb.sh                        # writes dist/baas-capture-agent_<version>_all.deb
```
