import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location(
    "global_control_v4_package",
    ROOT / "tools/package_native_control_v4.py",
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PixelNativeControlPackageTests(unittest.TestCase):
    def test_builder_blocks_until_new_native_artifacts_are_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'native-control').mkdir()
            (root / package.MANIFEST).write_text(json.dumps({
                'iteration': 4, 'service': 'jdsp.control', 'wireProtocol': 3,
                'state': 'awaiting-native-build',
            }))
            with self.assertRaisesRegex(ValueError, "V4 native build not imported"):
                package.build(root / "candidate.zip", root=root)

    def test_retired_native_payloads_cannot_be_relabelled_as_v4(self):
        self.assertIn("cf6e202262dd7925c1245670f3e3e7aa5aacf321fdf8f71ad0378e6e81b33e4a", package.RETIRED_DRIVERS)
        self.assertIn("266909b6aaf9a81648538369a2671d3f79d47d1f0ea02b56b21cf6cfc1df54ce", package.RETIRED_DRIVERS)

    def test_v4_zip_excludes_retired_signature_checker_and_classic_apk(self):
        source = (ROOT / "tools/package_native_control_v4.py").read_text()
        for payload in (
            "common/app_migration.sh",
            "common/apk_certificate.sh",
            "common/files/JamesDSPManager.apk",
            "common/files/JamesDSPManager.apk.meta",
        ):
            self.assertIn(repr(payload), source)

    def test_v4_provenance_keeps_regular_boot_dependency_gate_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'native-control').mkdir()
            (root / 'native-control/v4-build-provenance.json').write_text('{}')
            (root / 'patch.sh').write_text('return 1\n')
            shutil.copy2(ROOT / 'post-fs-data.sh', root / 'post-fs-data.sh')
            result = subprocess.run(['sh', str(root / 'post-fs-data.sh')],
                env={**os.environ, 'KSU_LATE_LOAD': '0'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'skip_mount').exists())
            self.assertIn('native_control_dependency_mismatch', (root / 'logs/late-load.status').read_text())

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
