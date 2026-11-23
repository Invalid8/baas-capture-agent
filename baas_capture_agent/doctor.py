import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

VENDOR = "05ba"
UDEV_RULE = Path("/usr/lib/udev/rules.d/70-baas-capture-agent.rules")


WBF_DRIVER = "https://www.hidglobal.com/media/4171"
WINDOWS_UPDATE = "ms-settings:windowsupdate-optionalupdates"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    say: str
    link: str | None = None
    link_label: str | None = None


def run(reader_connected: bool, route: str | None = None) -> list[dict]:
    checks = _windows(reader_connected, route) if sys.platform == "win32" else _linux(reader_connected)
    return [asdict(c) for c in checks]


def usb_readers(root: Path = Path("/sys/bus/usb/devices")) -> list[Path]:
    found = []
    for device in sorted(root.glob("*")):
        try:
            if (device / "idVendor").read_text().strip() == VENDOR:
                found.append(device)
        except OSError:
            continue
    return found


def device_node(device: Path) -> Path | None:
    try:
        bus = int((device / "busnum").read_text())
        dev = int((device / "devnum").read_text())
    except (OSError, ValueError):
        return None
    return Path(f"/dev/bus/usb/{bus:03d}/{dev:03d}")


def plugged_readers(root: Path = Path("/sys/bus/usb/devices")) -> tuple[str, ...]:
    """Where each U.are.U reader sits on the USB bus right now; a replug gives it a new address."""
    return tuple(node.as_posix() if (node := device_node(d)) else d.name for d in usb_readers(root))


def _linux(reader_connected: bool) -> list[Check]:
    readers = usb_readers()
    if not readers:
        return [Check("USB", False, "No U.are.U reader is plugged in. Plug it in, or try another USB port.")]
    checks = [Check("USB", True, "The U.are.U reader is plugged in.")]
    node = device_node(readers[0])
    if node is not None and not os.access(node, os.R_OK | os.W_OK):
        rule = "is installed" if UDEV_RULE.exists() else "is missing (reinstall the .deb)"
        checks.append(
            Check("Permission", False, f"This user can't open the reader. The udev rule {rule}; unplug and replug the reader.")
        )
    else:
        checks.append(Check("Permission", True, "This user can open the reader."))
    checks.append(
        Check("libfprint", True, "libfprint is using the reader.")
        if reader_connected
        else Check("libfprint", False, "libfprint can't use the reader. Unplug and replug it; if that fails, restart the agent.")
    )
    return checks


def parse_pnputil(text: str) -> list[dict[str, str]]:
    devices, current = [], {}
    for line in text.splitlines():
        if ":" not in line:
            if current:
                devices.append(current)
                current = {}
            continue
        key, _, value = line.partition(":")
        current[key.strip()] = value.strip()
    if current:
        devices.append(current)
    return [d for d in devices if f"VID_{VENDOR.upper()}" in d.get("Instance ID", "").upper()]


def windows_checks(devices: list[dict[str, str]], reader_connected: bool, route: str | None = None) -> list[Check]:
    if not devices:
        return [Check("USB", False, "Windows doesn't see a U.are.U reader. Plug it in, or try another USB port.")]
    device = devices[0]
    name = device.get("Device Description", "U.are.U reader")
    checks = [Check("USB", True, f"Windows sees the {name}.")]
    if not device.get("Driver Name") and device.get("Status", "").lower() != "started":
        checks.append(
            Check(
                "Driver",
                False,
                "The reader has no driver yet. Open Windows Update > Optional updates, tick the fingerprint driver "
                "and install it. If none is listed, get the U.are.U WBF driver from HID.",
                WINDOWS_UPDATE,
                "Open Windows Update",
            )
        )
        return checks
    if device.get("Class Name", "").lower() != "biometric":
        if reader_connected and route == "dpfpdd":
            checks.append(
                Check(
                    "Driver",
                    True,
                    "The reader uses DigitalPersona's own driver. The agent reads it through the U.are.U SDK, so your "
                    "other DigitalPersona software keeps working.",
                )
            )
        else:
            checks.append(
                Check(
                    "Driver",
                    False,
                    "The reader uses DigitalPersona's own driver, but the U.are.U SDK that goes with it isn't installed. "
                    "Reinstall your DigitalPersona software, or install HID's U.are.U WBF driver instead.",
                    WBF_DRIVER,
                    "Get the WBF driver",
                )
            )
        return checks
    if device.get("Status", "").lower() != "started":
        checks.append(Check("Driver", False, f"The WBF driver isn't running ({device.get('Status', 'unknown')}). Replug the reader."))
        return checks
    checks.append(Check("Driver", True, "The U.are.U WBF driver is running."))
    checks.append(
        Check("Windows Biometric Framework", True, "Windows hands the reader to this agent.")
        if reader_connected
        else Check("Windows Biometric Framework", False, "Windows can't open the reader for this agent. Restart the PC.")
    )
    return checks


def _windows(reader_connected: bool, route: str | None) -> list[Check]:
    try:
        text = subprocess.run(
            ["pnputil", "/enum-devices", "/connected"], capture_output=True, text=True, timeout=15, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return [Check("Driver", reader_connected, "Couldn't ask Windows about its drivers (pnputil).")]
    return windows_checks(parse_pnputil(text), reader_connected, route)
