import unittest

import subprocess
from unittest import mock

from baas_capture_agent import tray
from baas_capture_agent.tray import control_agent, describe, label, state, task_command
from baas_capture_agent.tray_linux import icons


class TrayTest(unittest.TestCase):
    def test_states_in_words(self):
        self.assertEqual(label({"connected": True, "capturing": False}), "Reader ready")
        self.assertEqual(label({"connected": True, "capturing": True}), "Reading a finger")
        self.assertEqual(label({"connected": False, "capturing": False}), "Reader not connected")
        self.assertEqual(state({"connected": False, "capturing": True}), "missing")

    def test_linux_panel_says_when_the_agent_is_gone(self):
        self.assertEqual(describe(None), ("missing", "Capture agent not running"))
        self.assertEqual(describe({"connected": True, "capturing": False}), ("ready", "Reader ready"))

    def test_linux_panel_icons_are_written_once_per_state(self):
        import tempfile
        from pathlib import Path

        paths = icons(Path(tempfile.mkdtemp()))
        self.assertEqual(sorted(paths), ["busy", "missing", "ready"])
        self.assertIn("rgb(76, 195, 138)", Path(paths["ready"]).read_text())


class WindowsIconControlTest(unittest.TestCase):
    def test_start_and_stop_drive_the_agents_task(self):
        self.assertEqual(task_command("start"), ["schtasks", "/Run", "/TN", "BAAS Capture Agent"])
        self.assertEqual(task_command("stop"), ["schtasks", "/End", "/TN", "BAAS Capture Agent"])

    def test_restart_stops_then_starts_without_a_console_window(self):
        with mock.patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), mock.patch.object(
            tray.subprocess, "run"
        ) as run:
            control_agent("restart")
        self.assertEqual([c.args[0][1] for c in run.call_args_list], ["/End", "/Run"])
        self.assertTrue(all(c.kwargs["creationflags"] == 0x08000000 for c in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
