import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
UUID = "f27317f4-c984-4de6-9a90-545759495bf2"
SERVICES = (
    "vendor.secaudiohal-aidl", "vendor.audio-hal", "vendor.audio-hal-aidl",
    "vendor.audio-effect-hal-aidl", "vendor.audio-hal-4-0-msd",
    "audio_proxy_service", "audio_parameter_parser_service",
)


class SamsungAudioRecoveryTests(unittest.TestCase):
    def executable(self, path, body):
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def fixture(self, root):
        module = root / "module"
        logs = module / "logs"
        logs.mkdir(parents=True)
        (module / ".AIDL").touch()
        (module / ".samsung-firmware-recovery-opt-in").touch()
        (logs / "late-load.status").write_text("READY late_load=1 boot_id=boot-1 lib=validated\n")
        (logs / "native-control.status").write_text("WAITING policy=typed_rules_refreshed\n")
        (root / "boot-id").write_text("boot-1\n")
        lib = module / "system/vendor/lib64/soundfx/libjamesdsp.so"
        lib.parent.mkdir(parents=True)
        lib.write_bytes(b"test-library")
        script = module / "samsung-audio-recovery.sh"
        script.write_bytes((ROOT / script.name).read_bytes())
        proc = root / "proc"
        for pid, name in ((101, "audiohalservice.qti"), (102, "secaudiohalaidl"),
                          (201, "audiohalservice.qti"), (202, "secaudiohalaidl")):
            p = proc / str(pid)
            (p / "root/vendor/lib64/soundfx").mkdir(parents=True)
            (p / "root/vendor/etc").mkdir()
            (p / "exe").symlink_to("/vendor/bin/hw/" + name)
            (p / "root/vendor/lib64/soundfx/libjamesdsp.so").write_bytes(lib.read_bytes())
            (p / "root/vendor/etc/audio_effects_config.xml").write_text(f'<effect uuid="{UUID}"/>\n')
            (p / "maps").write_text("/vendor/lib64/soundfx/libjamesdsp.so\n" if pid == 201 else "")
        firmware = root / "firmware"
        (firmware / "system/etc/init").mkdir(parents=True)
        (firmware / "vendor/etc/init").mkdir(parents=True)
        rc = firmware / "system/etc/init/audioserver.rc"
        rc.write_text("on property:sys.audio.restart.hal=1\n" + "".join(
            f"    {op} {service}\n" for op in ("stop", "start") for service in SERVICES
        ) + "    setprop sys.audio.restart.hal 0\n\non init\n    mkdir /dev/socket/audioserver\n")
        (firmware / "vendor/etc/init/audiohalservice_qti.rc").write_text(
            "service vendor.audio-hal-aidl /vendor/bin/hw/audiohalservice.qti\n    onrestart restart audioserver\n")
        (firmware / "vendor/etc/init/secaudiohalaidl.rc").write_text(
            "service vendor.secaudiohal-aidl /vendor/bin/hw/secaudiohalaidl\n    onrestart restart audioserver\n")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        marker = root / "reload.calls"
        self.executable(bin_dir / "id", "echo 0\n")
        self.executable(bin_dir / "flock", 'test "$1" = -n && test "$2" = 0 && test -e /dev/fd/0\n')
        self.executable(bin_dir / "getprop", f'''case "$1" in
ro.product.device) echo "${{MOCK_DEVICE:-h8q}}" ;;
sys.audio.restart.hal) if [ -e "{marker}" ]; then echo "${{MOCK_PROPERTY_AFTER:-0}}"; else echo "${{MOCK_PROPERTY:-0}}"; fi ;;
init.svc.*) echo running ;;
esac
''')
        self.executable(bin_dir / "pidof", f'''case "$1" in
audiohalservice.qti) if [ -e "{marker}" ]; then echo 201; else echo "${{MOCK_QTI_PIDS:-101}}"; fi ;;
secaudiohalaidl) if [ -e "{marker}" ]; then echo 202; else echo 102; fi ;;
audioserver) echo 103 ;;
esac
''')
        self.executable(bin_dir / "dumpsys", f'''case "$*" in
*--pid*) if [ -n "$MOCK_FACTORY_PID" ]; then echo "$MOCK_FACTORY_PID"; elif [ -e "{marker}" ]; then echo 201; else echo 101; fi ;;
*) exit 0 ;;
esac
''')
        self.executable(bin_dir / "setprop", f'''echo "$*" >>"{marker}"
[ "${{MOCK_SETPROP_FAILURE:-0}}" != 1 ]
''')
        self.executable(bin_dir / "linker", 'exit "${MOCK_LINKER_FAILURE:-0}"\n')
        self.executable(bin_dir / "sleep", "exit 0\n")
        self.executable(bin_dir / "logcat", "echo test-loader-log\n")
        env = {**os.environ, "JDSP_PROC_ROOT": str(proc), "JDSP_INIT_ROOT": str(firmware),
               "JDSP_BOOT_ID_FILE": str(root / "boot-id")}
        for name in ("id", "flock", "getprop", "pidof", "dumpsys", "setprop", "linker", "sleep", "logcat"):
            env["JDSP_" + name.upper() + "_BIN"] = str(bin_dir / name)
        return module, script, marker, rc, env

    def run_script(self, script, env, mode="--retry-once"):
        return subprocess.run(["sh", str(script), mode], env=env,
                              capture_output=True, text=True, timeout=30)

    def test_empty_vendor_dump_does_not_prevent_one_guarded_firmware_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, script, marker, _, env = self.fixture(Path(tmp))
            first = self.run_script(script, env)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("LOADED", first.stdout)
            self.assertIn("registration=unverified", first.stdout)
            self.assertIn("processing=unverified", first.stdout)
            self.assertEqual(marker.read_text(), "sys.audio.restart.hal 1\n")
            (Path(env["JDSP_PROC_ROOT"]) / "201/maps").write_text("")
            second = self.run_script(script, env)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("reload_already_attempted_this_boot", second.stdout)
            self.assertEqual(marker.read_text(), "sys.audio.restart.hal 1\n")
            self.assertEqual((module / "logs/audio-hal-reload-samsung.boot-id").read_text(), "boot-1\n")

    def test_check_mode_and_missing_opt_in_do_not_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, script, marker, _, env = self.fixture(Path(tmp))
            (module / ".samsung-firmware-recovery-opt-in").unlink()
            check = self.run_script(script, env, "--check")
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("PREFLIGHT", check.stdout)
            retry = self.run_script(script, env)
            self.assertNotEqual(retry.returncode, 0)
            self.assertIn("opt_in_required", retry.stdout)
            self.assertFalse(marker.exists())

    def test_automatic_mode_cannot_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, script, marker, _, env = self.fixture(Path(tmp))
            result = self.run_script(script, env, "--auto-once")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_changed_firmware_trigger_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, script, marker, rc, env = self.fixture(Path(tmp))
            rc.write_text(rc.read_text().replace("stop vendor.audio-hal-aidl", "restart vendor.audio-hal-aidl"))
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("firmware_trigger_not_verified", result.stdout)
            self.assertFalse(marker.exists())

    def test_missing_library_after_reload_is_not_reported_as_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, script, marker, _, env = self.fixture(Path(tmp))
            (Path(env["JDSP_PROC_ROOT"]) / "201/maps").write_text("")
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("library_not_mapped_after_reload", result.stdout)
            self.assertEqual(marker.read_text(), "sys.audio.restart.hal 1\n")

    def test_preflight_mismatches_fail_before_setting_property(self):
        cases = (("MOCK_DEVICE", "mustang", "unsupported_device"),
                 ("MOCK_FACTORY_PID", "102", "factory_owner_mismatch"),
                 ("MOCK_QTI_PIDS", "101 201", "hal_process_not_unique"),
                 ("MOCK_LINKER_FAILURE", "1", "linker_dependency_resolution_failed"),
                 ("MOCK_PROPERTY", "1", "firmware_reload_already_in_progress"))
        for key, value, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                _, script, marker, _, env = self.fixture(Path(tmp))
                env[key] = value
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout)
                self.assertFalse(marker.exists())

    def test_failed_property_request_still_consumes_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, script, marker, _, env = self.fixture(Path(tmp))
            env["MOCK_SETPROP_FAILURE"] = "1"
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("firmware_reload_request_failed", result.stdout)
            self.assertTrue((module / "logs/audio-hal-reload-samsung.boot-id").exists())
            self.assertEqual(marker.read_text(), "sys.audio.restart.hal 1\n")

    def test_changed_overlay_or_stale_boot_blocks_before_request(self):
        for case in ("library", "uuid", "boot", "disabled", "policy", "guard"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module, script, marker, _, env = self.fixture(root)
                if case == "library":
                    (root / "proc/101/root/vendor/lib64/soundfx/libjamesdsp.so").write_bytes(b"old-library")
                elif case == "uuid":
                    (root / "proc/102/root/vendor/etc/audio_effects_config.xml").write_text("<config/>\n")
                elif case == "boot":
                    (root / "boot-id").write_text("other-boot\n")
                elif case == "disabled":
                    (module / ".samsung-firmware-recovery-disabled").touch()
                elif case == "policy":
                    (module / "logs/native-control.status").write_text("STAGED policy=typed_rules_applied\n")
                elif case == "guard":
                    (module / "logs/audio-hal-reload-retry.boot-id").write_text("boot-1\n")
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(marker.exists())

    def test_deleted_or_unrelated_mappings_do_not_count_as_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, marker, _, env = self.fixture(root)
            (root / "proc/201/maps").write_text(
                "/vendor/lib64/soundfx/not-libjamesdsp.so\n"
                "/data/adb/modules/other/libjamesdsp.so\n"
                "/vendor/lib64/soundfx/libjamesdsp.so (deleted)\n")
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("library_not_mapped_after_reload", result.stdout)
            self.assertEqual(marker.read_text(), "sys.audio.restart.hal 1\n")

    def test_already_loaded_library_does_not_request_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, marker, _, env = self.fixture(root)
            (module / ".samsung-firmware-recovery-opt-in").unlink()
            (root / "proc/101/maps").write_text("/vendor/lib64/soundfx/libjamesdsp.so\n")
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("LOADED reason=library_already_mapped", result.stdout)
            self.assertIn("registration=unverified", result.stdout)
            self.assertFalse(marker.exists())

    def test_busy_lock_does_not_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, marker, _, env = self.fixture(root)
            self.executable(Path(env["JDSP_FLOCK_BIN"]), "exit 1\n")
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("recovery_in_progress", result.stdout)
            self.assertFalse(marker.exists())

    def test_firmware_property_must_reset_after_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, script, marker, _, env = self.fixture(Path(tmp))
            env['MOCK_PROPERTY_AFTER'] = '1'
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('firmware_reload_not_observed', result.stdout)
            self.assertEqual(marker.read_text(), 'sys.audio.restart.hal 1\n')

    def test_new_hal_must_remain_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, marker, _, env = self.fixture(root)
            unstable = root / 'unstable'
            self.executable(Path(env['JDSP_SLEEP_BIN']), f'touch "{unstable}"\n')
            self.executable(Path(env['JDSP_PIDOF_BIN']), f'''case "$1" in
audiohalservice.qti) if [ -e "{unstable}" ]; then echo 301; elif [ -e "{marker}" ]; then echo 201; else echo 101; fi ;;
secaudiohalaidl) if [ -e "{marker}" ]; then echo 202; else echo 102; fi ;;
audioserver) echo 103 ;;
esac
''')
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('audio_services_unstable_after_reload', result.stdout)
            self.assertEqual(marker.read_text(), 'sys.audio.restart.hal 1\n')

    def test_factory_change_during_preflight_does_not_request_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, marker, _, env = self.fixture(root)
            changed = root / 'factory-changed'
            self.executable(Path(env['JDSP_LINKER_BIN']), f'touch "{changed}"\n')
            self.executable(Path(env['JDSP_DUMPSYS_BIN']),
                            f'if [ -e "{changed}" ]; then echo 201; else echo 101; fi\n')
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('audio_state_changed_during_preflight', result.stdout)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
