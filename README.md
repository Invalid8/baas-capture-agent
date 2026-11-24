# Capture agent for the U.are.U 4500

Use a **DigitalPersona / HID U.are.U 4500** fingerprint reader from any web page,
on **Windows** and **Linux**, with no browser plugin and no vendor SDK to buy.

The agent is a small local service on `http://127.0.0.1:7501`. Your page asks it
for a fingerprint, it waits for a finger and returns the **image** as a PNG.
Matching, enrolment and storage stay with your app; the agent never matches,
keeps or sends prints anywhere.

It was written for BAAS, a biometric ATM project, and works for any web app that
needs a fingerprint image.

## What it does

- **One image format everywhere:** 8-bit grey at 500 ppi, so a print enrolled on
  Windows matches one taken on Linux.
- **Asks again for bad presses:** an empty glass or a press too light to read is
  never sent; the agent waits for a better one inside the same request.
- **Tells the page what is happening:** live events say when a finger lands, when
  to lift it, and when to press firmer.
- **Shows its state:** a check page at `http://127.0.0.1:7501` and an icon by the
  clock (Windows) or in the panel (Linux).

| | Windows | Linux |
|---|---|---|
| Reads the 4500 through | Windows Biometric Framework (HID's WBF driver), or the U.are.U SDK if the PC already has it | [libfprint](https://fprint.freedesktop.org/) (`uru4000` driver) |
| Install | `baas-capture-agent-setup.exe` | `baas-capture-agent.deb` (Ubuntu 22.04+, Debian 12+, Pop!_OS) |
| Starts | with Windows, at boot | with your desktop session |

Downloads: [latest release](https://github.com/Invalid8/baas-capture-agent/releases/latest).

## Install on Windows

**1. The reader's driver (once per PC).** Windows has no driver for the 4500 and
Windows Update doesn't offer one. Download HID's
[DigitalPersona 4500 WBF driver](https://www.hidglobal.com/media/4171), unzip it,
run `setup\setup64.exe`, then restart the PC. (HID's licence doesn't allow
shipping their driver inside this setup.) A PC that already runs DigitalPersona
software doesn't need this step; the agent uses the U.are.U SDK it has.

**2. The agent.** Run `baas-capture-agent-setup.exe`. If Windows says **"Windows
protected your PC"** (the program isn't code-signed yet), click **More info**,
then **Run anyway**. The setup:

- installs the agent and starts it with Windows at every boot, as the LocalSystem
  account (Windows only hands fingerprint presses to a background program running
  as LocalSystem);
- puts an icon by the clock, now and at every sign-in. Hover shows the state; click
  it to open the check page or restart, stop or start the agent. If Windows hides
  it under **^**, drag it onto the taskbar;
- opens the check page.

A newer setup installs over the old one. Uninstall from **Settings > Apps**.

## Install on Linux

```bash
sudo apt install ./baas-capture-agent.deb
```

`apt` pulls in libfprint. The package lets the signed-in user open the reader
without root (a udev rule) and starts the agent with the desktop session (a
systemd user service).

## Check that it works

Open **http://127.0.0.1:7501**. The page shows:

- **Reader:** "Ready to use", or the one thing to do (plug it in, install the driver).
- **Checks:** USB, driver and the route the agent reads through.
- **Test the reader:** press **Test**, place a finger, and the print appears.
- **Sites that may use the reader** and **Recent presses**.

## Use it from a web page

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
| POST | `/capture` | Waits for a finger, then `{image, width, height, ppi, device, attempts, quality}` |
| POST | `/cancel` | Stops this site's capture: `{cancelled}` |
| GET | `/events` | Live events (below) |
| GET | `/` | The check page |

`ppi` is always 500. `quality` is `{ink, coverage}`: the share of dark ridge
pixels and of the image area that holds a print.

```js
const events = new EventSource("http://127.0.0.1:7501/events");
events.onmessage = (m) => {
  const e = JSON.parse(m.data);
  // waiting · finger_on · captured (lift now) · reading · press_again {reason, say} · done · timeout · cancelled · error
};
```

Errors are JSON, `{"detail": "..."}`:

| Status | Meaning |
|---|---|
| 503 | Reader not connected |
| 408 | No finger within the timeout |
| 409 | Reader busy, or the capture was cancelled |
| 403 | The site is not allowed |

Chrome may ask once whether the site may reach devices on the local network;
choose **Allow**.

## Which sites may use it

- The BAAS kiosk and console are built in.
- `http://localhost` and `http://127.0.0.1` on any port are always allowed, for
  development.
- Any other site waits on the check page under **Sites that may use the reader**
  until someone clicks **Allow** (on Linux a window also asks). Sites can be
  removed there too.

To allow sites up front, pass `--origins https://your.app` (comma-separated), or
set `BAAS_AGENT_ORIGINS` in `/etc/baas-capture-agent.conf` on Linux.

| Setting | Default | Meaning |
|---|---|---|
| `BAAS_AGENT_PORT` / `--port` | `7501` | Local port |
| `BAAS_AGENT_ORIGINS` / `--origins` | empty | Sites allowed without asking |
| `BAAS_AGENT_TIMEOUT` / `--timeout` | `30` | Seconds to wait for a finger |

## Privacy and security

- Listens on `127.0.0.1` only; nothing on the network can reach it.
- Answers only sites allowed on this PC; only the check page can change that list.
- A site can cancel only its own capture.
- Keeps no images and makes no outgoing connections. The capture log holds times,
  sites and quality numbers only.

## Troubleshooting

Start with the check page: its **Checks** say what is wrong.

**Windows**

- *"The reader has no driver yet":* install HID's WBF driver (above) and restart.
- *The page doesn't load:* click the icon by the clock and choose **Start agent**,
  or open **Fingerprint reader icon** from the Start menu.
- *Log:* `C:\Windows\System32\config\systemprofile\AppData\Roaming\baas-capture-agent\capture.log`

**Linux**

- *`connected: false`:* check `lsusb` shows `05ba:000a`, then unplug and replug the reader.
- *"libfprint is not available":* `sudo apt install gir1.2-fprint-2.0 libfprint-2-2`.
- *Logs:* `journalctl --user -u baas-capture-agent -f`; capture log in `~/.config/baas-capture-agent/capture.log`.

`baas-probe.exe` (in each release) is a step-by-step reader check for Windows
when the agent itself can't say what is wrong.

## Develop

```bash
python3 -m unittest discover -s tests           # fake readers, no hardware needed
python3 -m baas_capture_agent --port 7501       # Linux: needs libfprint
packaging/build-deb.sh                          # dist/baas-capture-agent_<version>_all.deb
```

GitHub Actions runs the tests on Linux and Windows and, on a `v*` tag, builds the
setup `.exe`, the `.deb` and the probe and publishes them with the notes from
[CHANGELOG.md](CHANGELOG.md).

## Status

- **Linux:** used with a real 4500 (blank and faint thresholds set from real presses).
- **Windows:** the WBF route installs and sees the reader on a real PC; reading a
  press needs 0.2.7 (the agent runs as LocalSystem), which is being confirmed.

## Licence

MIT. See [LICENSE](LICENSE).
