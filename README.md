# Capture agent for the U.are.U 4500

Use a **DigitalPersona / HID U.are.U 4500** fingerprint reader from any web page,
on **Linux** and **Windows**, without the vendor's SDK, browser plugins or the
DigitalPersona Lite Client.

The agent is a small local service. Your web app calls it on
`http://127.0.0.1:7501`, it waits for a finger, and it returns the fingerprint
**image** as a PNG. What you do with the image (enrolment, matching, storage) is
up to your app or your server; the agent never matches, stores or sends prints
anywhere.

| | Linux | Windows |
|---|---|---|
| How it reads the 4500 | [libfprint](https://fprint.freedesktop.org/) (`uru4000` driver) | Windows Biometric Framework (the 4500's WBF driver) |
| Package | `.deb` (Ubuntu 22.04+, Debian 12+, Pop!_OS) | `.exe` |
| Status | Working, used with a real 4500 | **Being verified** on a real PC: run `baas-probe.exe` (below) |

It was written for BAAS, a biometric ATM project, and works for any web app that
needs a fingerprint image.

## Download

Get the files from the [releases page](https://github.com/Invalid8/baas-capture-agent/releases).

## Linux

```bash
sudo apt install ./baas-capture-agent_<version>_all.deb
```

`apt` pulls in libfprint. The package adds a udev rule so the logged-in user can
open the reader without root, and a systemd user service that starts with the
desktop session. Check it:

```bash
systemctl --user status baas-capture-agent
curl http://127.0.0.1:7501/status
```

`"connected": true` with `"driver": "uru4000"` means the reader is ready.

## Windows

The 4500 needs its WBF driver. Windows Update often installs it when the reader is
plugged in; otherwise install HID's "U.are.U Fingerprint Reader Driver (WBF)".
Don't install the older **non-WBF** driver as well: the two conflict, and Windows
then shows no reader.

**Check the reader first.** Download `baas-probe.exe`, double-click it and accept
the administrator prompt (Windows only hands raw fingerprint images to
administrators). It tells you, step by step:

1. whether it runs as administrator,
2. how many fingerprint readers Windows can see,
3. then asks for a finger and saves the image as `baas-probe.png` next to the `.exe`.

If any step fails, the message says why.

`baas-capture-agent.exe` runs the same service as on Linux. It runs in a console
window for now; a Windows service and installer are planned.

## Using it from a web page

```js
const agent = "http://127.0.0.1:7501";

const status = await (await fetch(`${agent}/status`)).json();
if (!status.connected) throw new Error("Plug in the fingerprint reader");

const res = await fetch(`${agent}/capture`, { method: "POST" });
const { image, width, height } = await res.json(); // image: base64 PNG
```

| Method | Path | Result |
|---|---|---|
| GET | `/status` | `{connected, device, driver, capturing, version}` |
| POST | `/capture` | Waits for a finger, then `{image, width, height, device}` (image is a base64 PNG, 8-bit grey) |
| POST | `/cancel` | Stops a capture in progress: `{cancelled}` |

Errors are JSON, `{"detail": "..."}`:

| Status | Meaning |
|---|---|
| 503 | Reader not connected |
| 408 | No finger within the timeout |
| 409 | Reader busy, or the capture was cancelled |
| 403 | The page's origin is not allowed |

Chrome may ask the first time whether the site may reach devices on the local
network. Choose **Allow**.

## Which sites may use it

The agent only answers web pages whose origin it allows. `http://localhost` and
`http://127.0.0.1` on any port are always allowed, for development. Add your
site's origin, comma-separated:

- Linux: `BAAS_AGENT_ORIGINS` in `/etc/baas-capture-agent.conf`, then
  `systemctl --user restart baas-capture-agent`.
- Anywhere: `--origins https://your.app,https://other.app` on the command line.

| Setting | Default | Meaning |
|---|---|---|
| `BAAS_AGENT_PORT` / `--port` | `7501` | Local port |
| `BAAS_AGENT_ORIGINS` / `--origins` | `https://baas-app-kappa.vercel.app` | Allowed origins |
| `BAAS_AGENT_TIMEOUT` / `--timeout` | `30` | Seconds to wait for a finger |

## Privacy and security

- Listens on `127.0.0.1` only; nothing on the network can reach it.
- Answers only allowed origins, so an unknown website can't take a print.
- Keeps no images and makes no outgoing connections.

## Troubleshooting

- **Linux, `connected: false`:** check `lsusb` shows `05ba:000a`, then unplug and
  replug the reader. Logs: `journalctl --user -u baas-capture-agent -f`.
- **Linux, "libfprint is not available":** `sudo apt install gir1.2-fprint-2.0 libfprint-2-2`.
- **Windows, the probe sees 0 readers:** check Device Manager under "Biometric
  devices"; remove the non-WBF driver if both are installed.
- **Windows, "run the agent as Administrator":** right-click, Run as administrator.

## Develop

```bash
python3 -m unittest -v                        # fake reader, no hardware needed
python3 -m baas_capture_agent --port 7501     # Linux: needs libfprint
packaging/build-deb.sh                        # dist/baas-capture-agent_<version>_all.deb
```

GitHub Actions runs the tests on Linux and Windows, builds both `.exe` files and the
`.deb`, and publishes them on a `v*` tag.

## Roadmap

- Windows service and installer
- One image standard (500 ppi) on both systems
- Rejecting blank, smudged or too-faint presses before they are sent
- Live events (finger on, lift your finger) and a self-check page
- Approve a new site from a prompt on the PC instead of editing settings
