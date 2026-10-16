"""Installer contract only; all Android installer helpers are host mocks."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SamsungInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = self.root / "module"
        self.module.mkdir()
        self.calls = self.root / "calls"
        self.calls.touch()
        for name, body in {
            "getprop": 'case "$1" in ro.product.manufacturer) echo "${TEST_VENDOR:-samsung}";; ro.product.cpu.abilist64) echo "${TEST_ABI:-arm64-v8a}";; esac\n',
            "service": 'echo "Service default: ${TEST_FACTORY:-found}"\n',
            "unzip": 'echo "extract $*" >> "$TEST_CALLS"; exit "${TEST_EXTRACT_RC:-0}"\n',
        }.items():
            path = self.root / name
            path.write_text("#!/bin/sh\n" + body)
            path.chmod(0o755)
        self.env = {
            **os.environ, "PATH": str(self.root) + ":" + os.environ["PATH"],
            "BOOTMODE": "true", "KSU": "1", "MODPATH": str(self.module),
            "ZIPFILE": str(self.root / "candidate.zip"),
            "TEST_CALLS": str(self.calls), "SCRIPT": str(ROOT / "samsung/customize.sh"),
        }

    def install(self, **env):
        harness = """
abort() { echo "$*" >&2; exit 7; }
ui_print() { echo "$*"; }
set_perm() { echo "permission $*" >> "$TEST_CALLS"; }
set_perm_recursive() { echo "permissions $*" >> "$TEST_CALLS"; }
. "$SCRIPT"
"""
        return subprocess.run(["sh", "-c", harness], env={**self.env, **env},
                              capture_output=True, text=True, timeout=10)

    def test_normal_install_sets_self_mount_markers_without_activating(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.module / "skip_mount").exists())
        self.assertTrue((self.module / "skip_mountify").exists())
        self.assertIn("extract ", self.calls.read_text())
        self.assertNotIn("runtime.sh activate", self.calls.read_text())

    def test_direct_execution_without_installer_helpers_fails_before_operations(self):
        result = subprocess.run(["sh", str(ROOT / "samsung/customize.sh")],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing Android module installer context", result.stderr)
        self.assertEqual(self.calls.read_text(), "")

    def test_wrong_vendor_is_rejected_before_extraction(self):
        self.assertNotEqual(self.install(TEST_VENDOR="google").returncode, 0)
        self.assertEqual(self.calls.read_text(), "")

    def test_non_ksu_is_rejected_before_extraction(self):
        self.assertNotEqual(self.install(KSU="").returncode, 0)
        self.assertEqual(self.calls.read_text(), "")

    def test_recovery_install_is_rejected(self):
        self.assertNotEqual(self.install(BOOTMODE="false").returncode, 0)
        self.assertEqual(self.calls.read_text(), "")

    def test_wrong_architecture_is_rejected(self):
        self.assertNotEqual(self.install(TEST_ABI="x86_64").returncode, 0)
        self.assertEqual(self.calls.read_text(), "")

    def test_missing_factory_is_rejected(self):
        self.assertNotEqual(self.install(TEST_FACTORY="missing").returncode, 0)
        self.assertEqual(self.calls.read_text(), "")

    def test_legacy_directory_is_not_deleted_or_overwritten(self):
        legacy = self.module / "audio-reload.sh"
        legacy.write_text("preserve legacy data")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Mixed legacy", result.stderr)
        self.assertEqual(legacy.read_text(), "preserve legacy data")
        self.assertEqual(self.calls.read_text(), "")

    def test_extraction_failure_does_not_report_success(self):
        result = self.install(TEST_EXTRACT_RC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Extraction failed", result.stderr)
        self.assertFalse((self.module / "skip_mount").exists())


if __name__ == "__main__":
    unittest.main()
