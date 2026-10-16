import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test19Tests(unittest.TestCase):
    def test_test19_bumps_module_version_and_keeps_the_updated_app_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test19.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test19.py")],
                env={**os.environ, "JDSP_TEST19_PACKAGE_OUTPUT": str(output)},
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                props = archive.read("module.prop").decode()
                self.assertIn("test19-samsung-root-app", props)
                self.assertIn("versionCode=128", props)
                self.assertIn("common/files/JamesDSPManagerZahah.apk", names)
                self.assertIn("TEST19.md", names)
                self.assertNotIn("update.json", names)
                self.assertEqual(
                    archive.read("common/files/JamesDSPManagerZahah.apk"),
                    (ROOT / "common/files/JamesDSPManagerZahah.apk").read_bytes(),
                )

    def test_experimental_marker_allows_both_test18_and_test19_module_versions(self):
        for path in (ROOT / "audio-reload.sh", ROOT / "patch.sh"):
            source = path.read_text()
            self.assertIn('[ "$module_version" = 127 ]', source)
            self.assertIn('[ "$module_version" = 128 ]', source)
            self.assertIn('[ "$module_version" = 129 ]', source)


if __name__ == "__main__":
    unittest.main()
