"""Host-only tests: Android operations are replaced by temporary-file mocks."""

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
XML = """<?xml version="1.0"?>
<audio_effects_conf version="2.0">
    <libraries>
        <library name="stock" path="libstockaidl.so"/>
    </libraries>
    <effects>
        <effect name="stock" library="stock" uuid="stock-uuid"/>
    </effects>
    <postprocess>
        <stream type="music"><apply effect="stock"/></stream>
    </postprocess>
</audio_effects_conf>
"""


class SamsungDirectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = self.root / "module"
        self.module.mkdir()
        for name in ("runtime.sh", "post-fs-data.sh", "service.sh", "late-load.sh"):
            shutil.copy2(ROOT / "samsung" / name, self.module / name)
        self.fs = self.root / "android"
        self.lib = self.fs / "vendor/lib64/soundfx"
        self.lib.mkdir(parents=True)
        (self.lib / "libstock.so").write_text("stock-library")
        (self.lib / ".stock-marker").write_text("hidden-stock-file")
        self.config = self.fs / "vendor/etc/audio_effects_config_sec.xml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(XML)
        driver = self.module / "driver/libjamesdsp.so"
        driver.parent.mkdir()
        driver.write_bytes(b"test-driver-not-executed")
        (self.module / "driver.sha256").write_text(hashlib.sha256(driver.read_bytes()).hexdigest() + "\n")
        self.proc = self.root / "proc"
        self.proc.mkdir()
        (self.proc / "mountinfo").touch()
        (self.proc / "boot-id").write_text("boot-a\n")
        self.calls = self.root / "calls"
        self.calls.touch()
        self.env = {
            **os.environ,
            "JDSP_SAMSUNG_FS_ROOT": str(self.fs),
            "JDSP_SAMSUNG_MOUNTINFO": str(self.proc / "mountinfo"),
            "JDSP_SAMSUNG_BOOT_ID": str(self.proc / "boot-id"),
            "JDSP_SAMSUNG_SH": shutil.which("sh"),
            "TEST_CALLS": str(self.calls),
            "TEST_BOOT_COMPLETE": "1",
            "TEST_MANUFACTURER": "samsung",
            "TEST_INIT_NS": "mnt:[test]",
            "TEST_SELF_NS": "mnt:[test]",
            "KSU_LATE_LOAD": "1",
            "KSU_RUNTIME_MODE": "late-load",
        }
        self.tool("getprop", """case "$1" in
sys.boot_completed) echo "$TEST_BOOT_COMPLETE";;
ro.product.manufacturer) echo "$TEST_MANUFACTURER";;
ro.product.cpu.abilist64) echo arm64-v8a;;
ro.boot.product.vendor.sku) echo canoe;;
esac
""")
        self.tool("readlink", 'case "$1" in */1/ns/mnt) echo "$TEST_INIT_NS";; */777/ns/mnt) echo "${TEST_HAL_NS:-$TEST_INIT_NS}";; *) echo "$TEST_SELF_NS";; esac\n')
        self.tool("pidof", 'echo "${TEST_HAL_PID-777}"\n')
        self.tool("service", 'echo "Service android.hardware.audio.effect.IFactory/default: ${TEST_FACTORY_STATE:-found}"\n')
        self.tool("nsenter", 'echo "namespace $*" >> "$TEST_CALLS"; shift 4; exec "$@"\n')
        self.tool("linker", 'echo "linker $*" >> "$TEST_CALLS"; exit "${TEST_LINKER_RC:-0}"\n')
        self.tool("flock", 'exit 0\n')
        self.tool("chcon", 'echo "label $*" >> "$TEST_CALLS"; exit "${TEST_LABEL_RC:-0}"\n')
        # Mounts only replace temporary fixtures with symlinks. Never calls host mount.
        tool = self.root / "mock-mount.py"
        tool.write_text("""#!/usr/bin/env python3
import os, pathlib, sys
source, target = sys.argv[-2:]
p = pathlib.Path(target)
with open(os.environ['TEST_CALLS'], 'a') as f: f.write('mount '+target+'\\n')
if target.endswith(os.environ.get('TEST_FAIL_TARGET', '__none__')): sys.exit(1)
p.rename(str(p)+'.backup')
p.symlink_to(source, target_is_directory=pathlib.Path(source).is_dir())
info = pathlib.Path(os.environ['JDSP_SAMSUNG_MOUNTINFO'])
rows = info.read_text().splitlines()
with info.open('a') as f: f.write(f'{100+len(rows)} 1 0:1 / {target} rw - tmpfs tmpfs rw\\n')
""")
        tool.chmod(0o755)
        self.env["JDSP_SAMSUNG_MOUNT"] = str(tool)
        tool = self.root / "mock-umount.py"
        tool.write_text("""#!/usr/bin/env python3
import os, pathlib, sys
target=sys.argv[-1]
with open(os.environ['TEST_CALLS'], 'a') as f: f.write('umount '+target+'\\n')
if os.environ.get('TEST_UMOUNT_FAIL'): sys.exit(1)
p=pathlib.Path(target); p.unlink(); pathlib.Path(target+'.backup').rename(p)
info=pathlib.Path(os.environ['JDSP_SAMSUNG_MOUNTINFO'])
info.write_text(''.join(r+'\\n' for r in info.read_text().splitlines() if r.split()[4]!=target))
""")
        tool.chmod(0o755)
        self.env["JDSP_SAMSUNG_UMOUNT"] = str(tool)

    def tool(self, name, body):
        path = self.root / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        self.env["JDSP_SAMSUNG_" + name.upper()] = str(path)

    def run_hook(self, hook="service.sh", **env):
        return subprocess.run(["sh", str(self.module / hook)], env={**self.env, **env},
                              text=True, capture_output=True, timeout=30)

    def status(self):
        return (self.module / "logs/samsung-runtime.status").read_text()

    def test_boot_callbacks_never_activate_even_with_old_markers(self):
        (self.module / ".late-load-reload-experimental").touch()
        (self.module / ".test18-samsung-viper-refresh").touch()
        for hook in ("post-fs-data.sh", "late-load.sh", "service.sh"):
            result = self.run_hook(hook, KSU_LATE_LOAD="1", KSU_RUNTIME_MODE="builtin")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), "")
        self.assertIn("SKIPPED reason=not_explicit_late_load", self.status())

    def test_pre_mount_hooks_never_mount_even_in_a_late_load_session(self):
        for hook in ("post-fs-data.sh", "late-load.sh"):
            self.assertEqual(self.run_hook(hook).returncode, 0)
        self.assertEqual(self.calls.read_text(), "")

    def test_runtime_mode_alone_is_not_an_activation_request(self):
        self.run_hook(KSU_LATE_LOAD="0")
        self.assertEqual(self.calls.read_text(), "")

    def test_explicit_late_load_before_boot_complete_is_deferred(self):
        self.run_hook(TEST_BOOT_COMPLETE="0")
        self.assertIn("DEFERRED reason=android_not_ready", self.status())
        self.assertEqual(self.calls.read_text(), "")

    def test_wrong_vendor_is_blocked(self):
        self.run_hook(TEST_MANUFACTURER="google")
        self.assertIn("unsupported_device", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_namespace_entry_failure_never_falls_back(self):
        self.tool("nsenter", "exit 1\n")
        self.run_hook()
        self.assertIn("init_namespace_unavailable", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_wrong_namespace_is_blocked(self):
        self.run_hook(TEST_SELF_NS="mnt:[wrong]")
        self.assertIn("namespace_mismatch", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_factory_in_another_namespace_is_blocked(self):
        self.run_hook(TEST_HAL_NS="mnt:[other]")
        self.assertIn("factory_namespace_mismatch", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_missing_qti_factory_is_blocked(self):
        self.run_hook(TEST_HAL_PID="")
        self.assertIn("qti_factory_process_missing", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_missing_aidl_service_never_mounts(self):
        self.run_hook(TEST_FACTORY_STATE="not available")
        self.assertIn("default_aidl_factory_missing", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_incompatible_driver_never_mounts(self):
        self.run_hook(TEST_LINKER_RC="1")
        self.assertIn("driver_dependency_resolution_failed", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_driver_tampering_never_mounts(self):
        (self.module / "driver/libjamesdsp.so").write_text("changed")
        self.run_hook()
        self.assertIn("driver_digest_mismatch", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_runtime_cannot_be_activated_by_a_marker_alone(self):
        (self.module / ".late-load-reload-experimental").touch()
        result = subprocess.run(["sh", str(self.module / "runtime.sh"), "activate"],
                                env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn("explicit_late_load_required", self.status())
        self.assertEqual(self.calls.read_text(), "")

    def test_xml_sections_outside_root_are_rejected(self):
        self.config.write_text(XML.replace("</audio_effects_conf>", "").replace(
            '    <libraries>', '</audio_effects_conf>\n    <libraries>'))
        self.run_hook()
        self.assertIn("unsupported_native_config", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_symlink_config_is_not_mounted_via_an_ambiguous_path(self):
        original = self.config.with_name("original.xml")
        self.config.rename(original)
        self.config.symlink_to(original)
        self.run_hook()
        self.assertIn("symlink_mount_target_unsupported", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_no_native_config_never_mounts(self):
        self.config.unlink()
        self.run_hook()
        self.assertIn("native_config_missing", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_existing_soundfx_mount_is_not_replaced(self):
        (self.proc / "mountinfo").write_text(f"77 1 0:1 / {self.lib} rw - tmpfs tmpfs rw\n")
        self.run_hook()
        self.assertIn("existing_soundfx_overlay", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_concurrent_activation_is_blocked_without_mounts(self):
        self.tool("flock", "exit 1\n")
        self.run_hook()
        self.assertIn("activation_locked", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_malformed_xml_never_mounts(self):
        self.config.write_text(XML.replace("</audio_effects_conf>", ""))
        self.run_hook()
        self.assertIn("unsupported_native_config", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_existing_jdsp_overlay_is_not_overwritten(self):
        (self.lib / "libjamesdsp.so").write_text("other-driver")
        self.run_hook()
        self.assertIn("existing_jdsp_payload", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_labels_must_succeed_before_any_mount(self):
        self.run_hook(TEST_LABEL_RC="1")
        self.assertIn("label_failed", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_self_mount_preserves_stock_and_never_claims_processing(self):
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MOUNTED_UNVERIFIED", self.status())
        self.assertIn("restart=not_requested", self.status())
        self.assertEqual((self.lib / ".stock-marker").read_text(), "hidden-stock-file")
        self.assertEqual((self.lib / "libstock.so").read_text(), "stock-library")
        self.assertEqual(stat.S_IMODE(self.lib.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.lib / "libjamesdsp.so").stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE((self.module / "logs").stat().st_mode), 0o700)
        patched = self.config.read_text()
        self.assertIn('name="jamesdsp"', patched)
        self.assertIn('<stream type="music"><apply effect="stock"/></stream>', patched)
        self.assertEqual((self.config.parent / (self.config.name + ".backup")).read_text(), XML)

    def test_repeated_activation_is_idempotent_from_live_mounts(self):
        self.run_hook()
        before = self.calls.read_text().count("mount ")
        self.run_hook()
        self.assertIn("already_mounted", self.status())
        self.assertEqual(self.calls.read_text().count("mount "), before)

    def test_partial_existing_session_is_not_stacked_or_unmounted(self):
        self.run_hook()
        (self.proc / "mountinfo").write_text((self.proc / "mountinfo").read_text().splitlines()[0] + "\n")
        before = self.calls.read_text()
        self.run_hook()
        self.assertIn("partial_or_changed_existing_mounts", self.status())
        self.assertNotIn("mount ", self.calls.read_text()[len(before):])

    def test_changed_factory_pid_during_staging_never_mounts(self):
        self.tool("pidof", 'N="$TEST_CALLS.pid-count"; if [ -f "$N" ]; then echo 778; else touch "$N"; echo 777; fi\n')
        self.run_hook()
        self.assertIn("factory_changed_during_activation", self.status())
        self.assertNotIn("mount ", self.calls.read_text())

    def test_config_mount_failure_rolls_back_owned_library_mount(self):
        self.run_hook(TEST_FAIL_TARGET="audio_effects_config_sec.xml")
        self.assertIn("mount_failed", self.status())
        self.assertNotIn("rollback_failed", self.status())
        self.assertFalse((self.lib / "libjamesdsp.so").exists())
        self.assertEqual(self.config.read_text(), XML)
        self.assertEqual((self.proc / "mountinfo").read_text(), "")

    def test_rollback_failure_is_explicit_and_work_files_are_retained(self):
        self.run_hook(TEST_FAIL_TARGET="audio_effects_config_sec.xml", TEST_UMOUNT_FAIL="1")
        self.assertIn("rollback_failed=1", self.status())
        self.assertTrue((self.lib / "libjamesdsp.so").is_file())

    def test_no_automatic_reboot_restart_policy_or_app_install_in_runtime(self):
        for path in (ROOT / "samsung").glob("*.sh"):
            source = path.read_text()
            for command in ("ctl.restart", "killall ", "setprop ", "resetprop ", "pm install", "sepolicy apply"):
                self.assertNotIn(command, source, str(path))


if __name__ == "__main__":
    unittest.main()
