import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    "android.hardware.audio.effect-V4-ndk.so",
    "android.media.audio.common.types-V5-ndk.so",
    "android.hardware.common-V2-ndk.so",
    "android.hardware.common.fmq-V1-ndk.so",
)


class NativeControlPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.libdir = self.module / "system/vendor/lib64/soundfx"
        self.libdir.mkdir(parents=True)
        (self.libdir / "lightningdsplib.so").write_bytes(b"fixture shared object")
        self.deps = self.root / "system-lib64"
        self.deps.mkdir()
        self.calls = self.root / "patchelf-calls"
        self.patchelf = self.root / "patchelf"

    def run_patch(self, needed=EXPECTED, add_available=True, allow_mismatch=False, library_roots=None):
        if add_available:
            for dependency in EXPECTED:
                (self.deps / dependency).touch()
        body = "#!/bin/sh\n"
        body += f"echo \"$*\" >> '{self.calls}'\n"
        body += "[ \"$1\" = --print-needed ] || exit 91\n"
        body += "cat <<'EOF'\n" + "\n".join(needed) + "\nEOF\n"
        self.patchelf.write_text(body)
        self.patchelf.chmod(0o755)
        env = {
            **os.environ,
            "AIDL": "true",
            "MODPATH": str(self.module),
            "MOD_VENDOR": str(self.module / "system/vendor"),
            "LDSP_PATCHELF_BIN": str(self.patchelf),
            "LDSP_SYSTEM_LIB_DIRS": library_roots or str(self.deps),
            "LDSP_EXPERIMENTAL_ALLOW_ABI_MISMATCH": "1" if allow_mismatch else "0",
        }
        return subprocess.run(
            ["sh", "-c", '. "$1/patch.sh"', "patch-test", str(ROOT)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_exact_dependencies_are_accepted_without_binary_rewrite(self):
        before = (self.libdir / "lightningdsplib.so").read_bytes()
        result = self.run_patch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validated without rewriting DT_NEEDED", result.stdout)
        self.assertEqual((self.libdir / "lightningdsplib.so").read_bytes(), before)
        self.assertEqual(self.calls.read_text().splitlines(), [f"--print-needed {self.libdir}/lightningdsplib.so"])

    def test_unavailable_compiled_interface_version_is_rejected(self):
        needed = list(EXPECTED)
        needed[0] = "android.hardware.audio.effect-V3-ndk.so"
        result = self.run_patch(needed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("device lacks exact AIDL dependency", result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [f"--print-needed {self.libdir}/lightningdsplib.so"])

    def test_missing_platform_dependency_is_rejected(self):
        result = self.run_patch(add_available=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("device lacks exact AIDL dependency", result.stderr)

    def test_real_v3_variant_is_accepted_when_its_own_dependencies_exist(self):
        needed = [name.replace("effect-V4-", "effect-V3-") for name in EXPECTED]
        for name in needed:
            (self.deps / name).touch()
        result = self.run_patch(needed=needed, add_available=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validated without rewriting", result.stdout)

    def test_legacy_bypass_flag_cannot_hide_missing_dependencies(self):
        before = (self.libdir / "lightningdsplib.so").read_bytes()
        needed = [name.replace("-V4-", "-V3-") for name in EXPECTED]
        result = self.run_patch(needed=needed, add_available=False, allow_mismatch=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("device lacks exact AIDL dependency", result.stderr)
        self.assertEqual((self.libdir / "lightningdsplib.so").read_bytes(), before)

    def embedded_profile(self):
        control = self.module / 'native-control'
        control.mkdir()
        (control / 'ldsp-candidate.json').write_text('{"iteration": 6}')

    def test_embedded_driver_needs_no_versioned_audio_dsos(self):
        self.embedded_profile()
        needed = ('libbinder_ndk.so', 'liblog.so', 'libc.so', 'libm.so', 'libdl.so')
        for name in needed:
            (self.deps / name).touch()
        result = self.run_patch(needed, add_available=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('embedded LightningDSP', result.stdout)
        self.assertEqual(len(self.calls.read_text().splitlines()), 1)

    def test_embedded_profile_resolves_bionic_from_an_apex_library_directory(self):
        self.embedded_profile()
        bionic = self.root / 'apex/com.android.runtime/lib64/bionic'
        bionic.mkdir(parents=True)
        (bionic / 'libc.so').touch()
        (self.deps / 'libbinder_ndk.so').touch()
        roots = str(self.deps) + ' ' + str(self.root / 'apex/*/lib64/bionic')
        result = self.run_patch(('libbinder_ndk.so', 'libc.so'), add_available=False, library_roots=roots)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/apex/*/lib64/bionic', (ROOT / 'patch.sh').read_text())

    def test_embedded_profile_rejects_shared_audio_or_empty_dependency_list(self):
        for needed in ((), EXPECTED, ('libbinder_ndk.so', 'libc.so', 'libc++.so'),
                       ('libbinder_ndk.so',), ('libc.so',)):
            with self.subTest(needed=needed):
                marker = self.module / 'native-control/ldsp-candidate.json'
                if not marker.exists():
                    self.embedded_profile()
                result = self.run_patch(needed, add_available=False)
                self.assertNotEqual(result.returncode, 0)

    def test_embedded_profile_still_rejects_missing_system_dependencies(self):
        self.embedded_profile()
        result = self.run_patch(('libbinder_ndk.so', 'libc.so'), add_available=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('device lacks exact embedded-driver dependency', result.stderr)


if __name__ == "__main__":
    unittest.main()

class NativeControlVersionVariants(unittest.TestCase):
    def test_validator_does_not_pin_effect_hal_to_v4(self):
        source = (ROOT / "patch.sh").read_text()
        self.assertNotIn("android.hardware.audio.effect-V4-ndk.so", source)
        self.assertNotIn("--replace-needed", source)
