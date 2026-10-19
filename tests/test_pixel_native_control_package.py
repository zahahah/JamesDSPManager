import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location(
    "pixel_native_control_package",
    ROOT / "tools/package_6511_pixel_native_control_v3.py",
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PixelNativeControlPackageTests(unittest.TestCase):
    def test_builder_produces_pinned_zip_without_restart_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "candidate.zip"
            digest = package.build(output)
            self.assertEqual(len(digest), 64)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, set(package.PAYLOADS))
                self.assertNotIn("audio-reload.sh", names)
                self.assertEqual(
                    archive.read(package.DRIVER),
                    (ROOT / package.DRIVER).read_bytes(),
                )
                self.assertIn("native-control/provenance.json", names)
                self.assertIn("native-control/LightningDSP-Main-LICENSE.txt", names)
                self.assertIn("NATIVE-CONTROL.md", names)
            self.assertTrue(output.with_suffix(".zip.sha256").is_file())
            self.assertTrue(output.with_suffix(".zip.json").is_file())

    def test_candidate_service_does_not_restart_audio_in_late_load(self):
        service = (ROOT / "service.sh").read_text(encoding="utf-8")
        late_branch = service.split('if [ "${KSU_LATE_LOAD:-0}"', 1)[1].split("fi", 1)[0]
        self.assertNotIn("audio-reload.sh", late_branch)
        self.assertNotIn("killall", late_branch)
        self.assertIn("restart=not_requested", late_branch)


if __name__ == "__main__":
    unittest.main()
