"""Linux panel icon (StatusNotifier / AppIndicator), run as its own process beside the agent."""

import os
import sys
import tempfile
import webbrowser
from pathlib import Path

from baas_capture_agent.tray import COLOURS, describe, read_status

REFRESH_MS = 3000
CIRCLE = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="24" fill="rgb{}"/></svg>'


def icons(folder: Path) -> dict[str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for kind, colour in COLOURS.items():
        path = folder / f"baas-reader-{kind}.svg"
        path.write_text(CIRCLE.format(colour))
        paths[kind] = str(path)
    return paths


def main(url: str) -> None:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
        from gi.repository import GLib, Gtk
    except (ImportError, ValueError):
        sys.exit(0)

    paths = icons(Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())) / "baas-capture-agent")
    indicator = AppIndicator.Indicator.new(
        "baas-capture-agent", paths["missing"], AppIndicator.IndicatorCategory.HARDWARE
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    indicator.set_title("Fingerprint reader")

    menu = Gtk.Menu()
    line = Gtk.MenuItem(label="Checking the reader…")
    line.set_sensitive(False)
    page = Gtk.MenuItem(label="Open the check page")
    page.connect("activate", lambda _item: webbrowser.open(url))
    for item in (line, page):
        menu.append(item)
    menu.show_all()
    indicator.set_menu(menu)

    def refresh():
        kind, text = describe(read_status(url))
        indicator.set_icon_full(paths[kind], text)
        line.set_label(text)
        return True

    refresh()
    GLib.timeout_add(REFRESH_MS, refresh)
    Gtk.main()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7501")
