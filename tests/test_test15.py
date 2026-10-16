import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test15PackageTests(unittest.TestCase):
    def test_package_stages_patched_thepbone_app_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test15.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test15.py")],
                env={**os.environ, "JDSP_TEST15_PACKAGE_OUTPUT": str(output)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive, ZipFile(
                ROOT / "dist/JamesDSPManager-v6.5.9-test14-samsung-aidl-query-trace.zip"
            ) as previous:
                props = archive.read("module.prop").decode()
                self.assertIn("test15-samsung-mountns-detection", props)
                self.assertIn("versionCode=125", props)
                self.assertEqual(
                    archive.read("common/files/JamesDSPManager.apk"),
                    previous.read("common/files/JamesDSPManager.apk"),
                )
                app = archive.read("common/files/JamesDSPManagerThePBone.apk")
                self.assertIn(b"classes3.dex", app)
                self.assertIn("HAL mount view".encode(), archive.read("TEST15.md"))

    def test_source_patch_has_null_guard_and_checks_hal_mount_view(self):
        source = (ROOT / "patches/RootJamesDSP-test15.patch").read_text()
        self.assertIn("AudioEffect.queryEffects().orEmpty()", source)
        self.assertIn("/proc/${'$'}pid/root${'$'}path", source)
        self.assertIn("RootShellImpl.cmd(command)", source)


if __name__ == "__main__":
    unittest.main()
