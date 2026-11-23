import argparse
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from baas_capture_agent import __version__, prompt
from baas_capture_agent.capturelog import CaptureLog
from baas_capture_agent.events import EventHub
from baas_capture_agent.origins import OriginStore
from baas_capture_agent.server import HOST, CaptureAgent, make_server

DEFAULT_PORT = 7501
DEFAULT_TIMEOUT = 30.0


def parse_origins(value: str) -> tuple[str, ...]:
    return tuple(o.strip().rstrip("/") for o in value.split(",") if o.strip())


def config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "baas-capture-agent"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "baas-capture-agent"


def open_reader():
    if sys.platform == "win32":
        from baas_capture_agent.winbio import WinBioReader

        return WinBioReader()
    try:
        from baas_capture_agent.reader import LibfprintReader

        return LibfprintReader()
    except (ImportError, ValueError) as exc:
        sys.exit(f"libfprint is not available ({exc}). Install gir1.2-fprint-2.0 and libfprint-2-2.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="baas-capture-agent",
        description="Local fingerprint capture service for web pages (127.0.0.1 only).",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("BAAS_AGENT_PORT", DEFAULT_PORT)))
    parser.add_argument(
        "--origins",
        default=os.environ.get("BAAS_AGENT_ORIGINS", ""),
        help="Extra sites allowed without asking, comma-separated",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("BAAS_AGENT_TIMEOUT", DEFAULT_TIMEOUT)),
        help="Seconds to wait for a finger",
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    url = f"http://{HOST}:{args.port}"
    folder = config_dir()
    reader = open_reader()
    origins = OriginStore(folder / "sites.json", parse_origins(args.origins), prompt.ask)
    agent = CaptureAgent(reader, args.timeout, EventHub(), CaptureLog(folder / "capture.log"))
    try:
        server = make_server(agent, args.port, origins)
    except OSError:
        if sys.platform == "win32":
            webbrowser.open(url)
        sys.exit(f"The agent is already running on {url}")
    print(f"baas-capture-agent {__version__} on {url} (open it in a browser to check the reader)", flush=True)
    try:
        if sys.platform == "win32":
            from baas_capture_agent import tray

            threading.Thread(target=server.serve_forever, daemon=True).start()
            tray.run(agent, url, server.shutdown)
        else:
            panel = subprocess.Popen([sys.executable, "-m", "baas_capture_agent.tray_linux", url])
            try:
                server.serve_forever()
            finally:
                panel.terminate()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
