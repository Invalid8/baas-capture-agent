import ctypes
import sys
import threading
from pathlib import Path

from baas_capture_agent.png import encode_grayscale
from baas_capture_agent.reader import ReaderError

TIMEOUT = 30.0


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        return False


def _routes() -> list[tuple[str, object]]:
    from baas_capture_agent.dpfpdd import DpfpddReader
    from baas_capture_agent.winbio import WinBioReader

    found = []
    for label, route in (("Windows Biometric Framework (WBF driver)", WinBioReader), ("U.are.U SDK (DigitalPersona driver)", DpfpddReader)):
        try:
            reader = route()
        except OSError as exc:
            print(f"   {label}: not on this PC ({exc})")
            continue
        status = reader.status()
        print(f"   {label}: {'sees the reader' if status.connected else 'present, but sees no reader'}")
        found.append((label, reader, status.connected))
    return found


def run(out_dir: Path) -> int:
    print("BAAS capture agent - Windows reader check")
    print(f"1. Running as Administrator: {'yes' if is_admin() else 'NO (raw images need it; right-click > Run as administrator)'}")
    print("2. Ways to reach the reader:")
    routes = _routes()
    ready = [(label, reader) for label, reader, connected in routes if connected]
    if not ready:
        print("   No route sees the reader. Plug in the U.are.U 4500; if it is plugged in, install its WBF driver")
        print("   (Windows Update > Optional updates, or HID's setup64.exe), then run this again.")
        return 3

    code = 0
    for number, (label, reader) in enumerate(ready, start=1):
        print(f"3.{number} {label}: place a finger on the reader now, lift when it says Got it (waiting {TIMEOUT:.0f} s)...")
        try:
            capture = reader.capture(threading.Event(), TIMEOUT)
        except ReaderError as exc:
            print(f"     Capture failed: {exc}")
            code = 4
            continue
        path = out_dir / f"baas-probe-{number}.png"
        path.write_bytes(encode_grayscale(capture.pixels, capture.width, capture.height))
        ppi = f"{capture.ppi:.0f} ppi" if capture.ppi else "resolution not reported"
        print(f"     Got it: {capture.width} x {capture.height}, {ppi}. Saved {path}")
    print("Send the PNG files and this text back. Done.")
    return code


def main() -> None:
    folder = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    code = run(folder)
    input("Press Enter to close.")
    sys.exit(code)


if __name__ == "__main__":
    main()
