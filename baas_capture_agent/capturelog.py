import threading
from collections import deque
from datetime import datetime
from pathlib import Path

KEEP = 50
MAX_BYTES = 1_000_000


class CaptureLog:
    """One plain line per press: on screen, in the agent's console or journal, and in capture.log."""

    def __init__(self, path: Path | None):
        self._path = path
        self._lines: deque[dict] = deque(maxlen=KEEP)
        self._lock = threading.Lock()

    def add(self, site: str | None, result: str, **details) -> dict:
        entry = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "site": site or "-", "result": result, **details}
        line = " ".join(
            [entry["at"], entry["site"], result, *(f"{key}={value}" for key, value in details.items() if value is not None)]
        )
        with self._lock:
            self._lines.appendleft(entry)
            print(line, flush=True)
            if self._path:
                self._write(line)
        return entry

    def _write(self, line: str) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists() and self._path.stat().st_size > MAX_BYTES:
                self._path.replace(self._path.with_suffix(".old.log"))
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def recent(self) -> list[dict]:
        with self._lock:
            return list(self._lines)
