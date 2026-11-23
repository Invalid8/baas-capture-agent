import unittest

from baas_capture_agent.tray import label, state
from baas_capture_agent.tray_linux import describe, icons


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


if __name__ == "__main__":
    unittest.main()
