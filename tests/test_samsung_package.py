import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
READELF = """ELF Header:
  Class:                             ELF64
  Type:                              DYN (Shared object file)
  Machine:                           AArch64
Dynamic section:
  0x0000000000000001 (NEEDED) Shared library: [libc.so]
  0x0000000000000001 (NEEDED) Shared library: [liblog.so]
  0x0000000000000001 (NEEDED) Shared library: [android.hardware.audio.effect-V3-ndk.so]
Symbol table '.dynsym':
   1: 0000000000000010 32 FUNC GLOBAL DEFAULT 10 createEffect
   2: 0000000000000020 32 FUNC GLOBAL DEFAULT 10 queryEffect
   3: 0000000000000030 32 FUNC GLOBAL DEFAULT 10 destroyEffect
"""


class SamsungPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Not a runnable ELF. The readelf mock is confined to package contract tests.
        self.driver = self.root / "fixture.so"
        self.driver.write_bytes(b"\x7fELF-not-a-production-driver")
        self.digest = hashlib.sha256(self.driver.read_bytes()).hexdigest()
        self.output = self.root / "candidate.zip"
        self.notices = self.root / "NOTICE"
        self.notices.write_text("Fixture notice, not a real source build\n")
        self.readelf = self.root / "readelf"
        self.readelf.write_text("#!/bin/sh\ncat <<'REPORT'\n" + READELF + "REPORT\n")
        self.readelf.chmod(0o755)

    def run_builder(self, *extra, revision="a" * 40):
        return subprocess.run([
            "python3", str(ROOT / "tools/package_samsung_direct.py"),
            "--driver", str(self.driver), "--sha256", self.digest,
            "--source-revision", revision, "--readelf", str(self.readelf),
            "--notices", str(self.notices),
            "--output", str(self.output), *extra,
        ], capture_output=True, text=True, timeout=15)

    def test_requires_explicit_driver_and_provenance(self):
        result = subprocess.run(["python3", str(ROOT / "tools/package_samsung_direct.py")],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--driver", result.stderr)

    def test_driver_hash_mismatch_blocks_output(self):
        result = self.run_builder("--sha256", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_non_arm64_input_blocks_output(self):
        self.readelf.write_text(self.readelf.read_text().replace("AArch64", "X86-64"))
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_missing_factory_export_blocks_output(self):
        self.readelf.write_text(self.readelf.read_text().replace("GLOBAL DEFAULT 10 queryEffect", "GLOBAL DEFAULT UND queryEffect"))
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_empty_license_notices_block_output(self):
        self.notices.write_text("")
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_unverified_revision_format_blocks_output(self):
        self.assertNotEqual(self.run_builder(revision="main").returncode, 0)
        self.assertFalse(self.output.exists())

    def test_linux_host_dependencies_are_rejected(self):
        self.readelf.write_text(self.readelf.read_text().replace("[libc.so]", "[libc.so.6]"))
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_exact_native_package_does_not_inherit_previous_experiments(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        first = self.output.read_bytes()
        with ZipFile(self.output) as z:
            names = set(z.namelist())
            self.assertIn("skip_mount", names)
            self.assertIn("skip_mountify", names)
            self.assertIn("driver/libjamesdsp.so", names)
            self.assertEqual(z.read("NOTICE"), self.notices.read_bytes())
            for forbidden in ("audio-reload.sh", "patch.sh", "update.json", "sepolicy.rule", "jdsp_app.sh"):
                self.assertNotIn(forbidden, names)
            self.assertFalse(any(n.endswith(".apk") or "pinwrap" in n or n.startswith(".test18") or n.startswith("system/") for n in names))
            for hook in ("service.sh", "post-fs-data.sh", "late-load.sh"):
                self.assertEqual(z.read(hook), (ROOT / "samsung" / hook).read_bytes())
                self.assertEqual((z.getinfo(hook).external_attr >> 16) & 0o777, 0o755)
            metadata = json.loads(z.read("driver-build.json"))
            self.assertEqual(metadata["source_revision"], "a" * 40)
            self.assertEqual(metadata["sha256"], self.digest)
            self.assertIn("not verified", metadata["provenance_note"])
            self.assertIn("processing=unverified", metadata["validation_boundary"])
            self.assertEqual(z.read("driver/libjamesdsp.so"), self.driver.read_bytes())
            props = z.read("module.prop").decode()
            self.assertIn("id=ainur_jamesdsp\n", props)
            self.assertIn("versionCode=130\n", props)
        self.assertEqual(self.run_builder().returncode, 0)
        self.assertEqual(self.output.read_bytes(), first)
        self.assertEqual(self.output.with_suffix(".zip.sha256").read_text().split()[0], hashlib.sha256(first).hexdigest())

    def test_existing_output_is_not_replaced_on_invalid_input(self):
        self.output.write_text("preserve")
        self.run_builder("--sha256", "0" * 64)
        self.assertEqual(self.output.read_text(), "preserve")

    def test_cannot_overwrite_driver_input(self):
        before = self.driver.read_bytes()
        result = self.run_builder("--output", str(self.driver))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.driver.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
