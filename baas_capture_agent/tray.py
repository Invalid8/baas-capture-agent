import threading
import webbrowser

REFRESH = 3.0
COLOURS = {"ready": (76, 195, 138), "busy": (242, 193, 78), "missing": (110, 112, 120)}


def state(status: dict) -> str:
    if not status["connected"]:
        return "missing"
    return "busy" if status["capturing"] else "ready"


def label(status: dict) -> str:
    return {"ready": "Reader ready", "busy": "Reading a finger", "missing": "Reader not connected"}[state(status)]


def run(agent, url: str, stop_server) -> None:
    """Windows notification-area icon. Blocks until Quit."""
    import pystray
    from PIL import Image, ImageDraw

    def picture(kind: str):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((8, 8, 56, 56), fill=COLOURS[kind])
        return image

    current = {"status": agent.status()}
    quitting = threading.Event()

    def quit_agent(icon, _item):
        quitting.set()
        icon.stop()
        stop_server()

    icon = pystray.Icon(
        "baas-capture-agent",
        picture(state(current["status"])),
        "Fingerprint reader",
        pystray.Menu(
            pystray.MenuItem(lambda _item: label(current["status"]), None, enabled=False),
            pystray.MenuItem("Open the check page", lambda: webbrowser.open(url), default=True),
            pystray.MenuItem("Quit", quit_agent),
        ),
    )

    def refresh():
        while not quitting.wait(REFRESH):
            current["status"] = agent.status()
            icon.icon = picture(state(current["status"]))
            icon.title = f"Fingerprint reader · {label(current['status'])}"
            icon.update_menu()

    threading.Thread(target=refresh, daemon=True).start()
    icon.run()
