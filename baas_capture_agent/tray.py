import json
import subprocess
import threading
import urllib.request
import webbrowser

REFRESH = 3.0
COLOURS = {"ready": (76, 195, 138), "busy": (242, 193, 78), "missing": (110, 112, 120)}
TASK = "BAAS Capture Agent"


def state(status: dict) -> str:
    if not status["connected"]:
        return "missing"
    return "busy" if status["capturing"] else "ready"


def label(status: dict) -> str:
    return {"ready": "Reader ready", "busy": "Reading a finger", "missing": "Reader not connected"}[state(status)]


def read_status(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{url}/status", timeout=1.5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def describe(status: dict | None) -> tuple[str, str]:
    if status is None:
        return "missing", "Capture agent not running"
    return state(status), label(status)


def task_command(action: str) -> list[str]:
    return ["schtasks", {"start": "/Run", "stop": "/End"}[action], "/TN", TASK]


def control_agent(action: str) -> None:
    """Start, stop or restart the agent's LocalSystem task (the icon runs elevated, so no prompt)."""
    for step in ("stop", "start") if action == "restart" else (action,):
        subprocess.run(
            task_command(step),
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def run(url: str, control=control_agent) -> None:
    """Windows notification-area icon for the agent's task. Hover shows the state; click opens the menu."""
    import pystray
    from PIL import Image, ImageDraw

    def picture(kind: str):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((8, 8, 56, 56), fill=COLOURS[kind])
        return image

    current = {"status": read_status(url)}
    if current["status"] is None:
        control("start")
    hidden = threading.Event()

    def running(_item) -> bool:
        return current["status"] is not None

    def act(action: str):
        def handler(icon, _item):
            control(action)
            current["status"] = read_status(url)
            show(icon)

        return handler

    def hide(icon, _item):
        hidden.set()
        icon.stop()

    def show(icon):
        kind, text = describe(current["status"])
        icon.icon = picture(kind)
        icon.title = f"BAAS capture agent · {text}"
        icon.update_menu()

    icon = pystray.Icon(
        "baas-capture-agent",
        picture("missing"),
        "BAAS capture agent",
        pystray.Menu(
            pystray.MenuItem(lambda _item: describe(current["status"])[1], None, enabled=False),
            pystray.MenuItem("Open the check page", lambda: webbrowser.open(url), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart agent", act("restart"), enabled=running),
            pystray.MenuItem("Stop agent", act("stop"), enabled=running),
            pystray.MenuItem("Start agent", act("start"), enabled=lambda item: not running(item)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Hide icon", hide),
        ),
    )

    def refresh():
        while not hidden.wait(REFRESH):
            current["status"] = read_status(url)
            show(icon)

    def start(i):
        i.visible = True
        show(i)

    threading.Thread(target=refresh, daemon=True).start()
    icon.run(setup=start)
