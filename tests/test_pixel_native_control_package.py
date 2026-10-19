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
                self.assertEqual(
                    archive.read("common/files/JamesDSPManagerThePBone.apk"),
                    (ROOT / "common/files/JamesDSPManagerThePBone.apk").read_bytes(),
                )
                self.assertEqual(
                    archive.read("common/files/JamesDSPManagerThePBone.apk.meta"),
                    b"versionCode=57\n",
                )
                self.assertIn("native-control/provenance.json", names)
                self.assertIn("native-control/LightningDSP-Main-LICENSE.txt", names)
                self.assertIn("NATIVE-CONTROL.md", names)
                self.assertEqual(
                    archive.getinfo("tools/patchelf").external_attr >> 16 & 0o777,
                    0o755,
                )
            self.assertTrue(output.with_suffix(".zip.sha256").is_file())
            self.assertTrue(output.with_suffix(".zip.json").is_file())

    def test_candidate_service_does_not_restart_audio_in_late_load(self):
        service = (ROOT / "service.sh").read_text(encoding="utf-8")
        late_branch = service.split('if [ "${KSU_LATE_LOAD:-0}"', 1)[1].split("fi", 1)[0]
        self.assertNotIn("audio-reload.sh", late_branch)
        self.assertNotIn("killall", late_branch)
        self.assertIn("restart=not_requested", late_branch)

    def test_installer_restores_patchelf_executable_mode_after_permission_reset(self):
        installer = (ROOT / "common/functions.sh").read_text(encoding="utf-8")
        permission_reset = installer.index("set_perm_recursive $MODPATH 0 0 0755 0644")
        permission_finalize = installer.index("set_permissions", permission_reset)
        patchelf_restore = installer.index('chmod 0755 "$MODPATH/tools/patchelf"', permission_finalize)
        self.assertLess(permission_reset, permission_finalize)
        self.assertLess(permission_finalize, patchelf_restore)


if __name__ == "__main__":
    unittest.main()
