import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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

    def test_identical_sources_package_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            payloads = []
            for branch in ('master', 'pixel-test-new-aidl'):
                output = Path(tmp) / (branch + '.zip')
                with patch.object(package, 'verify_artifacts', return_value={}), \
                     patch.object(package, 'distribution_version', return_value='v6.6-beta-4'):
                    package.build(output)
                payloads.append(output.read_bytes())
            self.assertEqual(payloads[0], payloads[1])

    def test_unrelated_branch_cannot_package_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(package, 'verify_artifacts', return_value={}), \
                 patch.object(package.subprocess, 'check_output', return_value='unrelated'):
                with self.assertRaisesRegex(ValueError, 'requires an approved branch'):
                    package.build(Path(tmp) / 'candidate.zip')

    def test_approved_branches_require_their_own_release_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for branch, (version, code) in package.DISTRIBUTIONS.items():
                (root / 'module.prop').write_text(f'version={version}\nversionCode={code}\n')
                with patch.object(package.subprocess, 'check_output', return_value=branch):
                    self.assertEqual(package.distribution_version(root), version)
            (root / 'module.prop').write_text('version=v6.6-beta-4\nversionCode=137\n')
            with patch.object(package.subprocess, 'check_output', return_value='samsung-test-new-aidl'):
                with self.assertRaisesRegex(ValueError, 'samsung-test2'):
                    package.distribution_version(root)

    def test_common_aidl_scripts_replace_legacy_recovery_without_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'candidate.zip'
            with patch.object(package, 'verify_artifacts', return_value={}), \
                    patch.object(package, 'distribution_version', return_value='v6.6-beta-4-samsung-test2'):
                package.build(output)
            with ZipFile(output) as archive:
                for script in ('aidl-effect-mount.sh', 'aidl-audio-recovery.sh'):
                    self.assertEqual(archive.getinfo(script).external_attr >> 16, 0o100755)
                self.assertNotIn('samsung-audio-recovery.sh', archive.namelist())
                self.assertNotIn('manual-audio-reload.sh', archive.namelist())
                self.assertNotIn('.samsung-firmware-recovery-opt-in', archive.namelist())

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

    def test_native_provenance_keeps_regular_boot_dependency_gate_active(self):
        for iteration in (4, 5):
            with self.subTest(iteration=iteration), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'native-control').mkdir()
                (root / f'native-control/v{iteration}-build-provenance.json').write_text('{}')
                (root / 'patch.sh').write_text('return 1\n')
                shutil.copy2(ROOT / 'post-fs-data.sh', root / 'post-fs-data.sh')
                result = subprocess.run(['sh', str(root / 'post-fs-data.sh')],
                    env={**os.environ, 'KSU_LATE_LOAD': '0'}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / 'skip_mount').exists())
                self.assertIn('native_control_dependency_mismatch', (root / 'logs/late-load.status').read_text())

    def test_candidate_service_only_schedules_guarded_hal_recovery_for_late_load(self):
        service = (ROOT / "service.sh").read_text(encoding="utf-8")
        late_branch = service.split('if [ "${KSU_LATE_LOAD:-0}"', 1)[1].split("fi", 1)[0]
        self.assertNotIn("audio-reload.sh", late_branch)
        self.assertNotIn("killall", late_branch)
        self.assertIn(':-/system/bin/sleep}" 10', late_branch)
        self.assertIn('audio-hal-recovery.sh" --auto-once', late_branch)
        self.assertIn('restart=one_shot', late_branch)
        self.assertNotIn('audioserver', late_branch)

    def test_installer_restores_patchelf_executable_mode_after_permission_reset(self):
        installer = (ROOT / "common/functions.sh").read_text(encoding="utf-8")
        permission_reset = installer.index("set_perm_recursive $MODPATH 0 0 0755 0644")
        permission_finalize = installer.index("set_permissions", permission_reset)
        patchelf_restore = installer.index('chmod 0755 "$MODPATH/tools/patchelf"', permission_finalize)
        self.assertLess(permission_reset, permission_finalize)
        self.assertLess(permission_finalize, patchelf_restore)


if __name__ == "__main__":
    unittest.main()
