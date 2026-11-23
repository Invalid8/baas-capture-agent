import shutil
import subprocess
import sys
from urllib.parse import urlsplit

TITLE = "Fingerprint reader"
WAIT_SECONDS = 90


def question(origin: str) -> str:
    return f"Allow {urlsplit(origin).hostname} to use the fingerprint reader?\n\n{origin}\n\nYou will only be asked once."


def ask(origin: str) -> bool | None:
    """Ask the person at this PC. None when no window can be shown (approve it on the agent's page instead)."""
    if sys.platform == "win32":
        return _ask_windows(origin)
    return _ask_zenity(origin)


def _ask_windows(origin: str) -> bool | None:
    import ctypes

    MB_YESNO, MB_ICONQUESTION, MB_TOPMOST, MB_SETFOREGROUND, IDYES = 0x4, 0x20, 0x40000, 0x10000, 6
    flags = MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND
    answer = ctypes.windll.user32.MessageBoxW(None, question(origin), TITLE, flags)
    return None if answer == 0 else answer == IDYES


def _ask_zenity(origin: str) -> bool | None:
    zenity = shutil.which("zenity")
    if zenity is None:
        return None
    try:
        result = subprocess.run(
            [zenity, "--question", f"--title={TITLE}", f"--text={question(origin)}", "--ok-label=Allow",
             "--cancel-label=Don't allow", "--no-markup", f"--timeout={WAIT_SECONDS}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=WAIT_SECONDS + 5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {0: True, 1: False}.get(result.returncode)
