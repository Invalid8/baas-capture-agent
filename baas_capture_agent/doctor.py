import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

VENDOR = "05ba"
UDEV_RULE = Path("/usr/lib/udev/rules.d/70-baas-capture-agent.rules")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    say: str


def run(reader_connected: bool) -> list[dict]:
    checks = _windows(reader_connected) if sys.platform == "win32" else _linux(reader_connected)
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


def windows_checks(devices: list[dict[str, str]], reader_connected: bool) -> list[Check]:
    if not devices:
        return [Check("USB", False, "Windows doesn't see a U.are.U reader. Plug it in, or try another USB port.")]
    device = devices[0]
    name = device.get("Device Description", "U.are.U reader")
    checks = [Check("USB", True, f"Windows sees the {name}.")]
    if device.get("Class Name", "").lower() != "biometric":
        checks.append(
            Check(
                "Driver",
                False,
                "The reader uses the older (non-WBF) driver. Uninstall it in Device Manager and install the "
                "U.are.U WBF driver.",
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


def _windows(reader_connected: bool) -> list[Check]:
    try:
        text = subprocess.run(
            ["pnputil", "/enum-devices", "/connected"], capture_output=True, text=True, timeout=15, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return [Check("Driver", reader_connected, "Couldn't ask Windows about its drivers (pnputil).")]
    return windows_checks(parse_pnputil(text), reader_connected)
