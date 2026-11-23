import tempfile
import threading
import time
import unittest
from pathlib import Path

from baas_capture_agent.__main__ import parse_origins
from baas_capture_agent.origins import BUILT_IN, OriginStore


def store(prompt=None, extra=()):
    return OriginStore(Path(tempfile.mkdtemp()) / "sites.json", extra, prompt)


class OriginStoreTest(unittest.TestCase):
    def test_built_in_and_local_sites_never_ask(self):
        asked = []
        s = store(lambda o: asked.append(o))
        for origin in (*BUILT_IN, "http://localhost:8080", "http://127.0.0.1:54321", "http://localhost", BUILT_IN[0] + "/"):
            self.assertTrue(s.allow(origin), origin)
        self.assertEqual(asked, [])

    def test_lookalikes_and_junk_are_refused_without_asking(self):
        asked = []
        s = store(lambda o: asked.append(o) or True)
        for origin in (None, "", "ftp://files.example", "https://a.example/path", "null"):
            self.assertFalse(s.allow(origin), origin)
        self.assertEqual(asked, [])

    def test_https_localhost_is_a_site_like_any_other(self):
        self.assertFalse(store().known("https://localhost:8080"))

    def test_extra_sites_from_the_command_line_are_allowed(self):
        self.assertTrue(store(extra=parse_origins(" https://a.example/, https://b.example ,")).allow("https://b.example"))

    def test_approval_survives_a_restart(self):
        path = Path(tempfile.mkdtemp()) / "sites.json"
        OriginStore(path, (), lambda o: True).allow("https://clinic.example")
        self.assertTrue(OriginStore(path, (), None).known("https://clinic.example"))

    def test_forgetting_a_site_asks_again_next_time(self):
        asked = []
        s = store(lambda o: asked.append(o) or True)
        s.allow("https://clinic.example")
        s.forget("https://clinic.example")
        s.allow("https://clinic.example")
        self.assertEqual(len(asked), 2)

    def test_many_requests_at_once_share_one_question(self):
        asked = []

        def slow_yes(origin):
            asked.append(origin)
            time.sleep(0.3)
            return True

        s = store(slow_yes)
        results = []
        workers = [threading.Thread(target=lambda: results.append(s.allow("https://clinic.example"))) for _ in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(5)
        self.assertEqual((asked, results), (["https://clinic.example"], [True] * 4))

    def test_a_broken_sites_file_starts_empty(self):
        path = Path(tempfile.mkdtemp()) / "sites.json"
        path.write_text("{not json")
        self.assertEqual(OriginStore(path, (), None).snapshot()["approved"], [])


if __name__ == "__main__":
    unittest.main()
