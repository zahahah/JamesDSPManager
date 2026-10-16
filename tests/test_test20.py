import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test20Tests(unittest.TestCase):
    def test_test20_packages_the_new_app_and_only_bumps_the_test_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test20.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test20.py")],
                env={**os.environ, "JDSP_TEST20_PACKAGE_OUTPUT": str(output)},
                capture_output=True,
                text=True,
                timeout=150,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive:
                props = archive.read("module.prop").decode()
                app = archive.read("common/files/JamesDSPManagerZahah.apk")
                self.assertIn("test20-samsung-discovery-retry", props)
                self.assertIn("versionCode=129", props)
                self.assertIn("TEST20.md", archive.namelist())
                self.assertEqual(
                    app, (ROOT / "common/files/JamesDSPManagerZahah-test62.apk").read_bytes()
                )
                self.assertNotIn("update.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()
