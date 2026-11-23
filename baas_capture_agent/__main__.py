import argparse
import os
import sys

from baas_capture_agent import __version__
from baas_capture_agent.server import HOST, CaptureAgent, make_server

DEFAULT_PORT = 7501
DEFAULT_ORIGINS = "https://baas-app-kappa.vercel.app"
DEFAULT_TIMEOUT = 30.0


def parse_origins(value: str) -> tuple[str, ...]:
    return tuple(o.strip().rstrip("/") for o in value.split(",") if o.strip())


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
        description="Local fingerprint capture service for the BAAS kiosk (127.0.0.1 only).",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("BAAS_AGENT_PORT", DEFAULT_PORT)))
    parser.add_argument(
        "--origins",
        default=os.environ.get("BAAS_AGENT_ORIGINS", DEFAULT_ORIGINS),
        help="Comma-separated kiosk origins allowed to call the agent",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("BAAS_AGENT_TIMEOUT", DEFAULT_TIMEOUT)),
        help="Seconds to wait for a finger",
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    reader = open_reader()

    origins = parse_origins(args.origins)
    server = make_server(CaptureAgent(reader, args.timeout), args.port, origins)
    print(f"baas-capture-agent {__version__} on http://{HOST}:{args.port} for {', '.join(origins)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
