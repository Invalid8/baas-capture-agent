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


def run(out_dir: Path) -> int:
    from baas_capture_agent.winbio import WinBioReader

    print("BAAS capture agent - Windows reader check")
    print(f"1. Running as Administrator: {'yes' if is_admin() else 'NO (raw images need it; right-click > Run as administrator)'}")
    try:
        reader = WinBioReader()
    except OSError as exc:
        print(f"2. Windows Biometric Framework: NOT available ({exc})")
        return 2
    try:
        units = reader.unit_count()
    except ReaderError as exc:
        print(f"2. Fingerprint readers Windows can see: error ({exc})")
        return 3
    print(f"2. Fingerprint readers Windows can see: {units}")
    if units == 0:
        print("   Plug in the U.are.U 4500 and install its WBF driver (setup64.exe), then run this again.")
        return 3

    print(f"3. Place a finger on the reader now (waiting {TIMEOUT:.0f} s)...")
    try:
        capture = reader.capture(threading.Event(), TIMEOUT)
    except ReaderError as exc:
        print(f"   Capture failed: {exc}")
        return 4
    path = out_dir / "baas-probe.png"
    path.write_bytes(encode_grayscale(capture.pixels, capture.width, capture.height))
    ppi = f"{capture.ppi:.0f} ppi" if capture.ppi else "resolution not reported"
    print(f"   Got it: {capture.width} x {capture.height}, {ppi}")
    print(f"4. Saved the image to {path}")
    print("Send that PNG and this text back. Done.")
    return 0


def main() -> None:
    folder = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    code = run(folder)
    input("Press Enter to close.")
    sys.exit(code)


if __name__ == "__main__":
    main()
