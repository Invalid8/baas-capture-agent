import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baas_capture_agent import doctor
from baas_capture_agent.doctor import device_node, parse_pnputil, plugged_readers, usb_readers, windows_checks

PNPUTIL = """Microsoft PnP Utility

Instance ID:                USB\\VID_046D&PID_C52B\\5&2B1F
Device Description:         USB Receiver
Class Name:                 USB
Status:                     Started

Instance ID:                USB\\VID_05BA&PID_000A\\{0}
Device Description:         U.are.U® 4500 Fingerprint Reader
Class Name:                 {1}
Class GUID:                 {{53d29ef7-377c-4d14-864b-eb3a85769359}}
Manufacturer Name:          Crossmatch
Status:                     {2}
Driver Name:                oem42.inf
"""


def windows(class_name="Biometric", status="Started"):
    return parse_pnputil(PNPUTIL.format("6&1A2B", class_name, status))


class WindowsDoctorTest(unittest.TestCase):
    def test_finds_only_the_fingerprint_reader(self):
        [device] = windows()
        self.assertEqual(device["Device Description"], "U.are.U® 4500 Fingerprint Reader")

    def test_healthy_wbf_reader(self):
        checks = windows_checks(windows(), reader_connected=True)
        self.assertTrue(all(c.ok for c in checks))
        self.assertEqual([c.name for c in checks], ["USB", "Driver", "Windows Biometric Framework"])

    def test_the_old_driver_is_fine_when_the_sdk_reads_it(self):
        checks = windows_checks(windows(class_name="DigitalPersona"), reader_connected=True, route="dpfpdd")
        self.assertTrue(all(c.ok for c in checks))
        self.assertIn("keeps working", checks[-1].say)

    def test_the_old_driver_without_the_sdk_offers_the_wbf_driver(self):
        checks = windows_checks(windows(class_name="DigitalPersona"), reader_connected=False)
        self.assertFalse(checks[-1].ok)
        self.assertEqual(checks[-1].link_label, "Get the WBF driver")

    def test_a_reader_without_any_driver_points_to_the_wbf_driver(self):
        text = PNPUTIL.format("6&1A2B", "", "Problem").replace("Driver Name:                oem42.inf\n", "")
        checks = windows_checks(parse_pnputil(text), reader_connected=False)
        self.assertFalse(checks[-1].ok)
        self.assertEqual(checks[-1].link, "https://www.hidglobal.com/media/4171")

    def test_driver_not_started(self):
        checks = windows_checks(windows(status="Problem"), reader_connected=False)
        self.assertIn("isn't running (Problem)", checks[-1].say)

    def test_no_reader(self):
        [check] = windows_checks([], reader_connected=False)
        self.assertFalse(check.ok)


class WindowsDriverQueryTest(unittest.TestCase):
    def test_asking_windows_about_drivers_opens_no_console_window(self):
        with mock.patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), mock.patch.object(
            doctor.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout="")
        ) as run:
            doctor._windows(False, None)
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)


class LinuxDoctorTest(unittest.TestCase):
    def test_finds_the_reader_and_its_device_node(self):
        root = Path(tempfile.mkdtemp())
        for name, vendor in (("1-1", "046d"), ("1-4", "05ba")):
            (root / name).mkdir()
            (root / name / "idVendor").write_text(vendor + "\n")
        (root / "1-4" / "busnum").write_text("1\n")
        (root / "1-4" / "devnum").write_text("48\n")
        [reader] = usb_readers(root)
        self.assertEqual(reader.name, "1-4")
        self.assertEqual(device_node(reader), Path("/dev/bus/usb/001/048"))
        self.assertEqual(plugged_readers(root), ("/dev/bus/usb/001/048",))

    def test_a_replug_gives_a_new_address_and_unplugging_leaves_nothing(self):
        root = Path(tempfile.mkdtemp())
        (root / "1-4").mkdir()
        (root / "1-4" / "idVendor").write_text("05ba\n")
        (root / "1-4" / "busnum").write_text("1\n")
        (root / "1-4" / "devnum").write_text("48\n")
        before = plugged_readers(root)
        (root / "1-4" / "devnum").write_text("49\n")
        self.assertNotEqual(plugged_readers(root), before)
        for f in (root / "1-4").iterdir():
            f.unlink()
        (root / "1-4").rmdir()
        self.assertEqual(plugged_readers(root), ())


if __name__ == "__main__":
    unittest.main()
