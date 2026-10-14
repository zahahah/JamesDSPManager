import os
import pathlib
import subprocess
import tempfile
import unittest
import zipfile
from hashlib import sha256

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ExperimentalPackageTests(unittest.TestCase):
    def test_installer_defers_only_unknown_late_load(self):
        installer = (ROOT / "common/install.sh").read_text()
        start = installer.index("INSTALL_DEVICE=$(getprop")
        end = installer.index('ui_print " "', start)
        probe = (
            'getprop() { printf "%s\\n" "$MOCK_DEVICE"; }\n'
            'ui_print() { printf "%s\\n" "$*"; }\n'
            + installer[start:end] + 'printf "legacy_patch\\n"\nfi\n'
        )
        for device, late, mode, deferred in (
            ("galaxy", "1", "", True),
            ("galaxy", "0", "late-load", True),
            ("mustang", "1", "late-load", False),
            ("galaxy", "0", "built-in", False),
        ):
            with self.subTest(device=device, late=late, mode=mode):
                result = subprocess.run(
                    ["sh", "-c", probe], text=True, capture_output=True,
                    env={**os.environ, "MOCK_DEVICE": device,
                         "KSU_LATE_LOAD": late, "KSU_RUNTIME_MODE": mode},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual("legacy_patch" not in result.stdout, deferred)

    def test_archive_is_distinct_and_preserves_apks(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "experimental.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test_portability.py")],
                env={**os.environ, "JDSP_TEST_PACKAGE_OUTPUT": str(output)},
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                props = archive.read("module.prop").decode()
                self.assertIn("version=v6.5.9-test9-samsung-aidl-pin", props)
                self.assertIn("versionCode=119", props)
                self.assertIn("id=ainur_jamesdsp", props)
                self.assertNotIn("update.json", archive.namelist())
                self.assertIn("EXPERIMENTAL.md", archive.namelist())
                self.assertIn("common/files/aidl/libjamesdsp_pinwrap.so", archive.namelist())
                for name in ("common/files/JamesDSPManager.apk", "common/files/JamesDSPManagerThePBone.apk"):
                    self.assertEqual(archive.read(name), (ROOT / name).read_bytes())
                self.assertFalse(any("rootless" in name.lower() for name in archive.namelist()))
            self.assertEqual(output.with_suffix(".zip.sha256").read_text().split()[0],
                             sha256(output.read_bytes()).hexdigest())

    def test_stable_output_is_rejected(self):
        result = subprocess.run(
            ["python3", str(ROOT / "tools/package_test_portability.py")],
            env={**os.environ, "JDSP_TEST_PACKAGE_OUTPUT": str(ROOT / "dist/JamesDSPManager-v6.5.9.zip")},
            text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot overwrite", result.stderr)
