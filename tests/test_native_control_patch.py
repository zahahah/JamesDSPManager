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
        (self.libdir / "libjamesdsp.so").write_bytes(b"fixture shared object")
        self.deps = self.root / "system-lib64"
        self.deps.mkdir()
        self.calls = self.root / "patchelf-calls"
        self.patchelf = self.root / "patchelf"

    def run_patch(self, needed=EXPECTED, add_available=True, allow_mismatch=False):
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
            "JDSP_PATCHELF_BIN": str(self.patchelf),
            "JDSP_SYSTEM_LIB_DIRS": str(self.deps),
            "JDSP_EXPERIMENTAL_ALLOW_ABI_MISMATCH": "1" if allow_mismatch else "0",
        }
        return subprocess.run(
            ["sh", "-c", '. "$1/patch.sh"', "patch-test", str(ROOT)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_exact_dependencies_are_accepted_without_binary_rewrite(self):
        before = (self.libdir / "libjamesdsp.so").read_bytes()
        result = self.run_patch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validated without rewriting DT_NEEDED", result.stdout)
        self.assertEqual((self.libdir / "libjamesdsp.so").read_bytes(), before)
        self.assertEqual(self.calls.read_text().splitlines(), [f"--print-needed {self.libdir}/libjamesdsp.so"])

    def test_wrong_interface_version_is_rejected(self):
        needed = list(EXPECTED)
        needed[0] = "android.hardware.audio.effect-V3-ndk.so"
        result = self.run_patch(needed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required dependency missing", result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [f"--print-needed {self.libdir}/libjamesdsp.so"])

    def test_missing_platform_dependency_is_rejected(self):
        result = self.run_patch(add_available=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("device lacks exact AIDL dependency", result.stderr)

    def test_experimental_mode_logs_missing_v4_abi_without_rewriting_binary(self):
        before = (self.libdir / "libjamesdsp.so").read_bytes()
        needed = [name.replace("-V4-", "-V3-") for name in EXPECTED]
        result = self.run_patch(needed=needed, add_available=False, allow_mismatch=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EXPERIMENTAL WARNING", result.stdout)
        self.assertIn("EXPERIMENTAL AIDL ABI probe enabled", result.stdout)
        self.assertEqual((self.libdir / "libjamesdsp.so").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
