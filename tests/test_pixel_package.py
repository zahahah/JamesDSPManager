import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from hashlib import sha256

spec = importlib.util.spec_from_file_location("pixel_package", Path(__file__).resolve().parents[1] / "tools/package_pixel_test.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PixelPackageTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {"driver": b"old", "apk": b"old", "service.sh": b"unchanged"}
        self.current = dict(self.baseline, driver=b"new driver", apk=b"new apk")
        self.expected = {n: sha256(self.current[n]).hexdigest() for n in ("driver", "apk")}
    def validate(self):
        with patch.object(p, "EXPECTED", self.expected):
            return p.validate_payloads(self.current, self.baseline)
    def test_only_requested_replacements(self):
        self.assertEqual(self.validate(), ["apk", "driver"])
    def test_reject_script_change(self):
        self.current["service.sh"] = b"changed"
        with self.assertRaises(ValueError): self.validate()
    def test_reject_wrong_binary(self):
        self.current["driver"] = b"unknown"
        with self.assertRaises(ValueError): self.validate()
    def test_reject_extra_file(self):
        self.current["extra.apk"] = b"unexpected"
        with self.assertRaises(ValueError): self.validate()
    def test_reject_missing_apk_replacement(self):
        self.current["apk"] = self.baseline["apk"]
        with self.assertRaises(ValueError): self.validate()

if __name__ == "__main__": unittest.main()
