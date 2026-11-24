import json
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

Prompt = Callable[[str], bool | None]


def normalise(origin: str) -> str:
    return origin.strip().rstrip("/")


def is_local(origin: str) -> bool:
    parts = urlsplit(origin)
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")


def well_formed(origin: str) -> bool:
    parts = urlsplit(origin)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.path and not parts.query


class OriginStore:
    """Sites allowed to use the reader: set on the command line, or approved once on this PC."""

    def __init__(self, path: Path, extra: tuple[str, ...] = (), prompt: Prompt | None = None):
        self._path = path
        self._fixed = {normalise(o) for o in extra if o.strip()}
        self._prompt = prompt
        self._lock = threading.Lock()
        self._asking: dict[str, threading.Event] = {}
        self._denied: set[str] = set()
        self._pending: set[str] = set()
        self._approved = self._load()

    def _load(self) -> set[str]:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return set()
        return {normalise(o) for o in data.get("approved", []) if isinstance(o, str)}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"approved": sorted(self._approved)}, indent=2))

    def known(self, origin: str | None) -> bool:
        if not origin:
            return False
        origin = normalise(origin)
        return is_local(origin) or origin in self._fixed or origin in self._approved

    def allow(self, origin: str | None) -> bool:
        """True if the site may use the reader, asking the person at the PC once if it is new."""
        if self.known(origin):
            return True
        if not origin or not well_formed(normalise(origin)):
            return False
        origin = normalise(origin)
        with self._lock:
            if origin in self._denied:
                return False
            asking = self._asking.get(origin)
            first = asking is None
            if first:
                asking = self._asking[origin] = threading.Event()
                self._pending.add(origin)
        if not first:
            asking.wait(120)
            return self.known(origin)
        answer = self._prompt(origin) if self._prompt else None
        with self._lock:
            if answer is True:
                self._approve(origin)
            elif answer is False:
                self._denied.add(origin)
                self._pending.discard(origin)
            del self._asking[origin]
        asking.set()
        return answer is True

    def _approve(self, origin: str) -> None:
        self._approved.add(origin)
        self._pending.discard(origin)
        self._denied.discard(origin)
        self._save()

    def approve(self, origin: str) -> None:
        with self._lock:
            self._approve(normalise(origin))

    def forget(self, origin: str) -> None:
        with self._lock:
            self._approved.discard(normalise(origin))
            self._save()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "preset": sorted(self._fixed),
                "approved": sorted(self._approved),
                "waiting": sorted(self._pending),
            }
