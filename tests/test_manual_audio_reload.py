import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManualAudioReloadTests(unittest.TestCase):
    @staticmethod
    def executable(path, body):
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def fixture(self, root):
        module = root / "module"
        (module / "logs").mkdir(parents=True)
        (module / ".AIDL").touch()
        (module / "logs/late-load.status").write_text("READY late_load=1 boot_id=boot-1 lib=validated\n")
        (module / "logs/native-control.status").write_text("WAITING policy=typed_rules_refreshed\n")
        (module / "system/vendor/lib64/soundfx").mkdir(parents=True)
        library = module / "system/vendor/lib64/soundfx/lightningdsplib.so"
        library.write_bytes(b"test-library")
        script = module / "manual-audio-reload.sh"
        script.write_bytes((ROOT / "manual-audio-reload.sh").read_bytes())
        proc = root / "proc"
        (proc / "101/root/vendor/lib64/soundfx").mkdir(parents=True)
        (proc / "101/root/vendor/etc").mkdir(parents=True)
        (proc / "101/root/vendor/lib64/soundfx/lightningdsplib.so").write_bytes(library.read_bytes())
        (proc / "101/root/vendor/etc/audio_effects_config.xml").write_text(
            '<effect uuid="f27317f4-c984-4de6-9a90-545759495bf2"/>\n'
        )
        (root / "boot-id").write_text("boot-1\n")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        marker = root / "restart-called"
        self.executable(bin_dir / "id", "echo 0\n")
        self.executable(bin_dir / "flock", "test \"$1\" = -x && test \"$2\" = 0 && test -e /dev/fd/0\n")
        self.executable(bin_dir / "getprop", "echo running\n")
        self.executable(bin_dir / "linker", "exit 0\n")
        self.executable(bin_dir / "service", "echo 'Service default: found'\n")
        self.executable(bin_dir / "sleep", "exit 0\n")
        self.executable(bin_dir / "pidof", f"if [ -e '{marker}' ]; then echo 202; else echo 101; fi\n")
        self.executable(bin_dir / "setprop", f"printf '%s\\n' \"$*\" >>'{marker}'\nmkdir -p '{proc}/202'\n")
        self.executable(bin_dir / "dumpsys", f"if [ -e '{marker}' ]; then echo 'Effects (22):'; echo 'f27317f4-c984-4de6-9a90-545759495bf2'; else echo 'Effects (21):'; fi\n")
        env = {
            **os.environ,
            "LDSP_AUDIO_HAL_INIT_SERVICE": "vendor.audio-hal-aidl",
            "LDSP_AUDIO_HAL_PROCESS": "android.hardware.audio.service-aidl.aoc",
            "LDSP_PROC_ROOT": str(proc),
            "LDSP_BOOT_ID_FILE": str(root / "boot-id"),
        }
        for name in ("id", "flock", "getprop", "linker", "service", "sleep", "pidof", "setprop", "dumpsys"):
            env["LDSP_" + name.upper() + "_BIN"] = str(bin_dir / name)
        return script, marker, env

    def test_not_invoked_by_boot_hooks(self):
        for name in ("post-fs-data.sh", "service.sh", "late-load.sh"):
            self.assertNotIn("manual-audio-reload.sh", (ROOT / name).read_text())

    def test_no_confirmation_cannot_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "restart-called"
            fake_setprop = Path(tmp) / "setprop"
            fake_setprop.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            fake_setprop.chmod(0o755)
            result = subprocess.run(
                ["sh", str(ROOT / "manual-audio-reload.sh")],
                env={**os.environ, "LDSP_SETPROP_BIN": str(fake_setprop)},
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_packaged_recovery_dispatcher_and_auto_schedule(self):
        source = (ROOT / "tools/package_native_control_v4.py").read_text()
        self.assertIn("'aidl-audio-recovery.sh': 0o100755", source)
        self.assertIn("'audio-hal-recovery.sh': 0o100755", source)
        self.assertIn("audio-hal-recovery.sh" , (ROOT / "service.sh").read_text())
        self.assertIn('set_perm "$MODPATH/aidl-audio-recovery.sh" 0 0 0755',
                      (ROOT / "customize.sh").read_text())
        self.assertIn('set_perm "$MODPATH/audio-hal-recovery.sh" 0 0 0755',
                      (ROOT / "customize.sh").read_text())
        script = (ROOT / "manual-audio-reload.sh").read_text()
        self.assertNotIn("killall", script)
        self.assertNotIn("audioserver", script.split("# Persist the per-mode guard", 1)[0])
        self.assertNotIn("setenforce", script)
        self.assertNotIn("default_android_service", script)

    def test_hal_identity_is_required_before_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            script, marker, env = self.fixture(Path(tmp))
            env.pop("LDSP_AUDIO_HAL_INIT_SERVICE")
            result = subprocess.run(["sh", str(script), "--manual-once"], env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("explicit_hal_identity_required", result.stdout)
            self.assertFalse(marker.exists())

    def test_one_manual_restart_then_guarded_for_same_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            script, marker, env = self.fixture(Path(tmp))
            first = subprocess.run(["sh", str(script), "--manual-once"], env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertIn("DISCOVERED", first.stdout)
            self.assertEqual(marker.read_text(), "ctl.restart vendor.audio-hal-aidl\n")
            second = subprocess.run(["sh", str(script), "--manual-once"], env=env, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("retry_reload_already_attempted_this_boot", second.stdout)
            self.assertEqual(marker.read_text(), "ctl.restart vendor.audio-hal-aidl\n")

    def test_recovery_dispatcher_uses_common_aidl_path_without_model_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            script = module / 'audio-hal-recovery.sh'
            script.write_bytes((ROOT / script.name).read_bytes())
            self.executable(module / 'aidl-audio-recovery.sh',
                            'echo "$1" >>"${0%/*}/aidl.calls"\n')
            for mode in ('--auto-once', '--retry', '--check'):
                result = subprocess.run(['sh', str(script), mode], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((module / 'aidl.calls').read_text(), '--auto-once\n--retry\n--check\n')
            invalid = subprocess.run(['sh', str(script), '--unknown'], capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)

    def test_invisible_overlay_blocks_before_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script, marker, env = self.fixture(root)
            (root / "proc/101/root/vendor/etc/audio_effects_config.xml").unlink()
            result = subprocess.run(["sh", str(script), "--manual-once"], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("overlay_not_visible_to_hal", result.stdout)
            self.assertFalse(marker.exists())

    def test_h8q_cannot_use_direct_legacy_hal_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script, marker, env = self.fixture(root)
            self.executable(Path(env['LDSP_GETPROP_BIN']),
                            'case "$1" in ro.product.device) echo h8q ;; *) echo running ;; esac\n')
            result = subprocess.run(['sh', str(script), '--manual-once'], env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('use_samsung_firmware_recovery', result.stdout)
            self.assertFalse(marker.exists())



if __name__ == "__main__":
    unittest.main()
