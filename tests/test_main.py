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
    def run_main(self, *argv, platform="win32"):
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
            sys, "platform", platform
        ), mock.patch.object(panel_icon, "run", tray.run):
            entry.main(list(argv))
        return server, made["origins"], popen, tray

    def test_service_mode_serves_with_no_icon_or_pop_up(self):
        server, origins, popen, tray = self.run_main("--service")
        self.assertTrue(server.served)
        tray.run.assert_not_called()
        popen.assert_not_called()
        self.assertIsNone(origins._prompt)

    def test_on_windows_the_program_itself_is_the_icon_and_never_a_second_agent(self):
        with mock.patch.object(sys, "platform", "win32"), mock.patch.object(panel_icon, "run") as run, mock.patch.object(
            entry, "make_server"
        ) as make_server, mock.patch.object(entry, "open_reader") as open_reader:
            entry.main([])
        run.assert_called_once_with("http://127.0.0.1:7501")
        make_server.assert_not_called()
        open_reader.assert_not_called()

    def test_on_linux_the_agent_keeps_its_panel_icon_and_the_site_question(self):
        server, origins, popen, _ = self.run_main(platform="linux")
        self.assertTrue(server.served)
        popen.assert_called_once()
        self.assertIs(origins._prompt, prompt.ask)

if __name__ == "__main__":
    unittest.main()
