import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baas_capture_agent import __main__ as entry
from baas_capture_agent import prompt
from baas_capture_agent import tray as panel_icon
from baas_capture_agent.reader import UnavailableReader


class FakeServer:
    def __init__(self):
        self.served = False

    def serve_forever(self):
        self.served = True
        raise KeyboardInterrupt

    def shutdown(self):
        pass

    def server_close(self):
        pass


class ServiceModeTest(unittest.TestCase):
    def run_main(self, *argv):
        server = FakeServer()
        tray = mock.MagicMock()
        made = {}

        def make_server(agent, port, origins, token=None):
            made["origins"] = origins
            return server

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            entry, "config_dir", return_value=Path(folder)
        ), mock.patch.object(entry, "open_reader", return_value=UnavailableReader("none")), mock.patch.object(
            entry, "make_server", side_effect=make_server
        ), mock.patch.object(entry.subprocess, "Popen") as popen, mock.patch.object(
            entry.webbrowser, "open"
        ) as browser, mock.patch.object(sys, "platform", "win32"), mock.patch.object(
            panel_icon, "run", tray.run
        ):
            entry.main(list(argv))
        return server, made["origins"], popen, browser, tray

    def test_service_mode_serves_with_no_icon_pop_up_or_browser(self):
        server, origins, popen, browser, tray = self.run_main("--service")
        self.assertTrue(server.served)
        tray.run.assert_not_called()
        popen.assert_not_called()
        browser.assert_not_called()
        self.assertIsNone(origins._prompt)

    def test_desktop_mode_keeps_the_panel_icon_and_the_site_question(self):
        _, origins, _, _, tray = self.run_main()
        tray.run.assert_called_once()
        self.assertIs(origins._prompt, prompt.ask)


if __name__ == "__main__":
    unittest.main()
