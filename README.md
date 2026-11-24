# Capture agent for the U.are.U 4500

Use a **DigitalPersona / HID U.are.U 4500** fingerprint reader from any web page,
on **Linux** and **Windows**, without the vendor's SDK, browser plugins or the
DigitalPersona Lite Client.

The agent is a small local service. Your web app calls it on
`http://127.0.0.1:7501`, it waits for a finger, and it returns the fingerprint
**image** as a PNG. What you do with the image (enrolment, matching, storage) is
up to your app or your server; the agent never matches, stores or sends prints
anywhere.

- **Same image on both systems:** every image leaves the agent as 8-bit grey at
  500 ppi, so a print enrolled on Windows can be matched against one taken on Linux.
- **Bad presses are asked again:** a blank glass, a smudge left behind or a
  press too light to read is not sent; the agent waits for a better press inside
  the same request.
- **Live events:** your page can show "hold still" the moment a finger lands,
  "lift your finger" the moment the print is taken (on Linux the reader only
  hands the image over once the finger leaves the glass, so saying so is what
  makes a read fast) and "press a little firmer" when a press is rejected.
- **Nothing to configure:** a new website asks once on screen, "Allow … to use
  the fingerprint reader?", and the answer is remembered.
- **Check page:** open `http://127.0.0.1:7501` in a browser to see the reader,
  what is wrong if it isn't working, a test capture, the allowed sites and
  the last presses.
- **Panel icon** on Linux: green when the reader is ready.

| | Linux | Windows |
|---|---|---|
| How it reads the 4500 | [libfprint](https://fprint.freedesktop.org/) (`uru4000` driver) | Windows Biometric Framework (WBF driver), or the U.are.U SDK if the PC already has it |
| Package | `.deb` (Ubuntu 22.04+, Debian 12+, Pop!_OS) | setup `.exe` |
| Status | Working, used with a real 4500 | **Being verified** on a real PC: run `baas-probe.exe` (below) |

It was written for BAAS, a biometric ATM project, and works for any web app that
needs a fingerprint image.

## Download

Get the files from the [releases page](https://github.com/Invalid8/baas-capture-agent/releases).

## Linux

```bash
sudo apt install ./baas-capture-agent.deb
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

You don't need to remove anything. The agent reads the 4500 whichever way the PC
already uses it:

- **Windows' own fingerprint support** (the 4500's WBF driver, the one Windows
  Hello uses). Windows Update often installs it when the reader is plugged in.
- **The U.are.U SDK** (DigitalPersona's own driver), on PCs that already run
  DigitalPersona or other U.are.U software. The agent borrows the reader only while
  it reads a finger, so that software keeps working.

If the reader has no driver at all, the setup asks Windows to find one, and the
check page says what to do next, with a button.

**Check the reader first.** Download `baas-probe.exe`, double-click it and accept
the administrator prompt (Windows only hands raw fingerprint images to
administrators). It tells you, step by step:

1. whether it runs as administrator,
2. which ways to reach the reader this PC has (Windows' fingerprint support, the
   U.are.U SDK) and whether each sees the reader,
3. then asks for a finger on each one that does, and saves the images as
   `baas-probe-1.png` (and `-2.png`) next to the `.exe`.

If any step fails, the message says why.

Windows may show **"Windows protected your PC"** the first time, because the
program isn't signed yet: click **More info**, then **Run anyway**.

Then run **`baas-capture-agent-setup.exe`**. It installs the agent, starts it now
and with Windows at every boot as the LocalSystem account (a scheduled task: Windows
only hands fingerprint presses to a background program running as LocalSystem), and
opens the check page. Running a newer setup installs over the old one. On Windows
there is no panel icon and no pop-up; a new site is allowed on the check page. The
log is `C:\Windows\System32\config\systemprofile\AppData\Roaming\baas-capture-agent\capture.log`.
Uninstall from Settings > Apps.

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
| GET | `/events` | Server-sent events while capturing (below) |
| GET | `/` | The check page |

`/capture` also returns `ppi` (always 500), `attempts` and
`quality: {ink, coverage}` (the share of dark ridge pixels and of the image area
that holds a print).

```js
const events = new EventSource("http://127.0.0.1:7501/events");
events.onmessage = (m) => {
  const e = JSON.parse(m.data);
  // waiting · finger_on · captured (lift now) · reading · press_again {reason: blank|faint, say} · done · timeout · cancelled · error
};
```

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

The first time a website calls the agent, a window on the PC asks
**"Allow … to use the fingerprint reader?"**. Allow is remembered; Don't allow
holds until the agent restarts. If no window can be shown, the site waits on the
check page under "Sites that may use the reader" with an **Allow** button, and you
can remove a site there too. `http://localhost` and `http://127.0.0.1` on any port
are always allowed, for development.

To allow sites without asking, list them (comma-separated) in
`BAAS_AGENT_ORIGINS` in `/etc/baas-capture-agent.conf` on Linux, or pass
`--origins https://your.app` on the command line.

| Setting | Default | Meaning |
|---|---|---|
| `BAAS_AGENT_PORT` / `--port` | `7501` | Local port |
| `BAAS_AGENT_ORIGINS` / `--origins` | empty | Sites allowed without asking |
| `BAAS_AGENT_TIMEOUT` / `--timeout` | `30` | Seconds to wait for a finger |

## Privacy and security

- Listens on `127.0.0.1` only; nothing on the network can reach it.
- Answers only sites someone allowed on this PC, so an unknown website can't
  take a print; only the check page itself can change the list.
- Keeps no images and makes no outgoing connections. The capture log
  (`capture.log` in the agent's settings folder: `~/.config/baas-capture-agent`
  or `%APPDATA%\baas-capture-agent`) holds times, sites and quality numbers only.

## Troubleshooting

Start with the check page, `http://127.0.0.1:7501`: its Checks say what is wrong.

- **Linux, `connected: false`:** check `lsusb` shows `05ba:000a`, then unplug and
  replug the reader. Logs: `journalctl --user -u baas-capture-agent -f`.
- **Linux, "libfprint is not available":** `sudo apt install gir1.2-fprint-2.0 libfprint-2-2`.
- **Windows, the probe sees no reader:** plug the reader into another USB port, then
  look in Windows Update > Optional updates for a fingerprint driver.
- **Windows, "run the agent as Administrator":** right-click, Run as administrator.

## Develop

```bash
python3 -m unittest -v                        # fake reader, no hardware needed
python3 -m baas_capture_agent --port 7501     # Linux: needs libfprint
packaging/build-deb.sh                        # dist/baas-capture-agent_<version>_all.deb
```

GitHub Actions runs the tests on Linux and Windows, builds both `.exe` files and the
`.deb`, and publishes them on a `v*` tag.

## Status

The "blank" and "too faint" thresholds come from real 4500 presses on Linux:
an empty glass or a barely touching fingertip reads about 0.1% ink, half a
finger 0.4–1%, full presses 2–16%. On Windows both routes are built and unit-tested and the
Windows Biometric Framework answers in CI, but neither has yet captured from a real 4500.

## Licence

MIT. See [LICENSE](LICENSE).
