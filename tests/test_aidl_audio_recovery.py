import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UUID = 'f27317f4-c984-4de6-9a90-545759495bf2'


class AidlAudioRecoveryTests(unittest.TestCase):
    def executable(self, path, body):
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)
        return path

    def fixture(self, root, pixel=False):
        module = root / 'module'
        logs = module / 'logs'
        logs.mkdir(parents=True)
        (module / '.AIDL').touch()
        (logs / 'late-load.status').write_text('READY late_load=1 boot_id=boot-1 lib=validated\n')
        (logs / 'native-control.status').write_text('WAITING policy=typed_rules_refreshed\n')
        (root / 'boot-id').write_text('boot-1\n')
        lib = module / 'system/vendor/lib64/soundfx/libjamesdsp.so'
        lib.parent.mkdir(parents=True)
        lib.write_bytes(b'expected-library')
        script = module / 'aidl-audio-recovery.sh'
        script.write_bytes((ROOT / script.name).read_bytes())
        self.executable(module / 'aidl-effect-mount.sh', 'exit "${MOCK_MOUNT_FAILURE:-0}"\n')
        owner_exe = '/vendor/bin/hw/' + ('android.hardware.audio.service-aidl.aoc' if pixel else 'audiohalservice.qti')
        secondary_exe = '/vendor/bin/hw/secaudiohalaidl'
        proc = root / 'proc'
        for pid, exe in ((101, owner_exe), (102, secondary_exe), (201, owner_exe), (202, secondary_exe)):
            p = proc / str(pid)
            (p / 'root/vendor/lib64/soundfx').mkdir(parents=True)
            (p / 'root/vendor/etc').mkdir()
            (p / 'exe').symlink_to(exe)
            (p / 'root/vendor/lib64/soundfx/libjamesdsp.so').write_bytes(lib.read_bytes())
            (p / 'root/vendor/etc/audio_effects_config.xml').write_text(f'<effect uuid="{UUID}"/>\n')
            (p / 'maps').write_text('/vendor/lib64/soundfx/libjamesdsp.so\n' if pid == 201 else '')
        self.framework_processes(proc)
        init = root / 'init'
        (init / 'vendor/etc/init').mkdir(parents=True)
        (init / 'system/etc/init').mkdir(parents=True)
        (init / 'vendor/lib64/soundfx').mkdir(parents=True)
        (init / 'vendor/lib64/soundfx/libjamesdsp.so').write_bytes(lib.read_bytes())
        (init / 'vendor/etc/audio_effects_config.xml').write_text(f'<effect uuid="{UUID}"/>\n')
        (init / 'vendor/etc/init/audio.rc').write_text(
            f'service vendor.audio-hal-aidl {owner_exe}\n    user audioserver\n    onrestart restart audioserver\n'
            f'service vendor.secaudiohal-aidl {secondary_exe}\n    user audioserver\n    onrestart restart audioserver\n')
        rc = init / 'system/etc/init/audioserver.rc'
        services = ('vendor.secaudiohal-aidl', 'vendor.audio-hal-aidl', 'vendor.audio-hal')
        rc.write_text('on property:sys.audio.restart.hal=1\n' + ''.join(
            f'    {op} {name}\n' for op in ('stop', 'start') for name in services
        ) + '    setprop sys.audio.restart.hal 0\n\non init\n    mkdir /dev/socket/audioserver\n')
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        calls = root / 'reload.calls'
        self.executable(bin_dir / 'id', 'echo "${MOCK_UID:-0}"\n')
        self.executable(bin_dir / 'flock', 'exit "${MOCK_LOCK_FAILURE:-0}"\n')
        self.executable(bin_dir / 'getprop', f'''case "$1" in
ro.audio.ignore_effects) echo "${{MOCK_IGNORE_EFFECTS:-false}}" ;;
sys.audio.restart.hal) if [ -e "{calls}" ]; then echo "${{MOCK_PROPERTY_AFTER:-0}}"; else echo "${{MOCK_PROPERTY:-0}}"; fi ;;
init.svc.vendor.audio-hal-aidl|init.svc.vendor.secaudiohal-aidl|init.svc.audioserver) echo running ;;
esac
''')
        self.executable(bin_dir / 'pidof', f'''case "$1" in
{owner_exe.rsplit('/', 1)[1]}) if [ -e "{calls}" ]; then echo 201; else echo "${{MOCK_FACTORY_PIDS:-101}}"; fi ;;
zygote64) echo 301 ;;
system_server) echo 302 ;;
secaudiohalaidl) if [ -e "{calls}" ]; then echo 202; else echo 102; fi ;;
esac
''')
        self.executable(bin_dir / 'dumpsys', f'''case "$*" in
*--pid*) if [ -n "$MOCK_FACTORY_PID" ]; then echo "$MOCK_FACTORY_PID"; elif [ -e "{calls}" ]; then echo 201; else echo 101; fi ;;
esac
''')
        self.executable(bin_dir / 'setprop', f'echo "$*" >>"{calls}"\nexit "${{MOCK_SETPROP_FAILURE:-0}}"\n')
        self.executable(bin_dir / 'linker', 'exit "${MOCK_LINKER_FAILURE:-0}"\n')
        self.executable(bin_dir / 'sleep', 'exit 0\n')
        self.executable(bin_dir / 'logcat', 'echo bounded-loader-evidence\n')
        env = {**os.environ, 'JDSP_PROC_ROOT': str(proc), 'JDSP_INIT_ROOT': str(init),
               'JDSP_BOOT_ID_FILE': str(root / 'boot-id')}
        for name in ('id', 'flock', 'getprop', 'pidof', 'dumpsys', 'setprop', 'linker', 'sleep', 'logcat'):
            env['JDSP_' + name.upper() + '_BIN'] = str(bin_dir / name)
        return module, script, calls, rc, env

    def framework_processes(self, proc, zstart=100, sstart=110):
        for pid, parent, start in ((301, 1, zstart), (302, 301, sstart)):
            p = proc / str(pid)
            p.mkdir(exist_ok=True)
            # stat fields 3..22; names may contain spaces and parentheses.
            (p / 'stat').write_text(f'{pid} (framework (test)) S {parent} ' +
                                     '0 ' * 17 + f'{start}\n')
            exe = p / 'exe'
            if not exe.exists() and not exe.is_symlink():
                exe.symlink_to('/system/bin/app_process64')

    def test_ten_soft_reboots_each_allow_one_request_but_hal_only_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, calls, _, env = self.fixture(root, pixel=True)
            for session in range(11):
                with self.subTest(session=session):
                    self.framework_processes(root / 'proc', 100 + session * 100, 110 + session * 100)
                    if calls.exists():
                        calls.unlink()  # Mock a fresh HAL before the next request.
                    result = self.run_script(script, env, '--auto-once')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')
                    # HAL PID changes from 101 to 201, framework stays the same.
                    again = self.run_script(script, env)
                    self.assertIn('reload_already_attempted_this_boot', again.stdout)
                    self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')
            self.assertEqual((module / 'logs/audio-hal-reload-aidl.lifecycle').read_text(),
                             'boot-1 301 1100 302 1110\n')

    def test_framework_identity_must_be_valid_and_both_processes_recreated(self):
        for case in ('server_only', 'zygote_only', 'backwards', 'missing', 'parent', 'exe', 'corrupt_ledger'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module, script, calls, _, env = self.fixture(root)
                self.assertEqual(self.run_script(script, env).returncode, 0)
                if case == 'server_only':
                    self.framework_processes(root / 'proc', 100, 210)
                elif case == 'zygote_only':
                    self.framework_processes(root / 'proc', 200, 110)
                elif case == 'backwards':
                    self.framework_processes(root / 'proc', 90, 95)
                elif case == 'missing':
                    (root / 'proc/301/stat').unlink()
                elif case == 'parent':
                    p = root / 'proc/302/stat'
                    p.write_text(p.read_text().replace(' S 301 ', ' S 999 '))
                elif case == 'exe':
                    p = root / 'proc/301/exe'
                    p.unlink()
                    p.symlink_to('/data/unknown')
                else:
                    (module / 'logs/audio-hal-reload-aidl.lifecycle').write_text('broken\n')
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')

    def test_framework_change_during_preflight_never_requests_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, calls, _, env = self.fixture(root)
            prop = Path(env['JDSP_GETPROP_BIN'])
            prop.write_text(prop.read_text().replace(
                'sys.audio.restart.hal)',
                f'''sys.audio.restart.hal) n=$(cat "{root}/property.reads" 2>/dev/null || echo 0); n=$((n+1)); echo $n >"{root}/property.reads"; [ $n -lt 2 ] || rm -f "{root}/proc/301/stat";''' ))
            result = self.run_script(script, env)
            self.assertIn('framework_changed_during_preflight', result.stdout)
            self.assertFalse(calls.exists())

    def test_failed_request_is_not_retried_in_the_same_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, calls, _, env = self.fixture(root)
            env['MOCK_SETPROP_FAILURE'] = '1'
            self.assertIn('firmware_reload_request_failed', self.run_script(script, env).stdout)
            self.assertIn('reload_already_attempted_this_boot', self.run_script(script, env).stdout)
            self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')

    def test_ready_native_context_can_seed_upgrade_without_restarting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, calls, _, env = self.fixture(root)
            (module / 'logs/audio-hal-reload-aidl.boot-id').write_text('boot-1\n')
            (root / 'proc/101/maps').write_text('/vendor/lib64/soundfx/libjamesdsp.so\n')
            helper = module / 'common/files/control/arm64-v8a/jdspctl'
            helper.parent.mkdir(parents=True)
            self.executable(helper, 'echo JDSPCTL:OK:ready=1:protocol=3:contexts=1:writable=1:publication=3\n')
            timeout = self.executable(root / 'bin/timeout', 'shift; exec "$@"\n')
            env.update(JDSP_CONTROL_HELPER=str(helper), JDSP_TIMEOUT_BIN=str(timeout))
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(calls.exists())
            self.assertEqual((module / 'logs/audio-hal-reload-aidl.lifecycle').read_text(),
                             'boot-1 301 100 302 110\n')
            self.framework_processes(root / 'proc', 200, 210)
            (root / 'proc/101/maps').write_text('')
            recovered = self.run_script(script, env, '--auto-once')
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')

    def test_old_guard_without_lifecycle_record_stays_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, script, calls, _, env = self.fixture(Path(tmp))
            (module / 'logs/audio-hal-reload-aidl.boot-id').write_text('boot-1\n')
            result = self.run_script(script, env)
            self.assertIn('reload_already_attempted_this_boot', result.stdout)
            self.assertFalse(calls.exists())

    def run_script(self, script, env, mode='--retry'):
        return subprocess.run(['sh', str(script), mode], env=env, capture_output=True, text=True, timeout=30)

    def test_same_path_handles_pixel_and_samsung_without_model_opt_in(self):
        for pixel in (False, True):
            for mode in ('--auto-once', '--retry'):
                with self.subTest(pixel=pixel, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    module, script, calls, _, env = self.fixture(Path(tmp), pixel=pixel)
                    result = self.run_script(script, env, mode)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('LOADED factory_service=vendor.audio-hal-aidl', result.stdout)
                    self.assertIn('registration=unverified processing=unverified', result.stdout)
                    self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')
                    again = self.run_script(script, env, '--retry')
                    self.assertNotEqual(again.returncode, 0)
                    self.assertIn('reload_already_attempted_this_boot', again.stdout)
                    self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')
                    self.assertEqual((module / 'logs/audio-hal-reload-aidl.boot-id').read_text(), 'boot-1\n')

    def test_check_never_mounts_or_requests_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, calls, _, env = self.fixture(root)
            mount_calls = root / 'bridge.calls'
            self.executable(module / 'aidl-effect-mount.sh', f'echo "$1" >"{mount_calls}"\n')
            result = self.run_script(script, env, '--check')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PREFLIGHT', result.stdout)
            self.assertEqual(mount_calls.read_text(), '--check\n')
            self.assertFalse(calls.exists())
            self.assertFalse((module / 'logs/audio-hal-reload-aidl.boot-id').exists())

    def test_private_old_hal_namespace_does_not_block_init_visible_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, calls, _, env = self.fixture(root)
            (root / 'proc/101/root/vendor/lib64/soundfx/libjamesdsp.so').unlink()
            (root / 'proc/101/root/vendor/etc/audio_effects_config.xml').write_text('<old/>\n')
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(calls.exists())

    def test_unverified_firmware_actions_never_execute(self):
        substitutions = [('stop vendor.audio-hal-aidl', 'restart vendor.audio-hal-aidl'),
                         ('stop vendor.audio-hal-aidl', 'stop zygote'),
                         ('start vendor.audio-hal-aidl', 'start zygote'),
                         ('setprop sys.audio.restart.hal 0', 'exec /data/unknown'),
                         ('property:sys.audio.restart.hal=1', 'property:sys.audio.restart.hal=1 && property:test=1')]
        for before, after in substitutions:
            with self.subTest(after=after), tempfile.TemporaryDirectory() as tmp:
                _, script, calls, rc, env = self.fixture(Path(tmp))
                rc.write_text(rc.read_text().replace(before, after))
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('firmware_handler_not_verified', result.stdout)
                self.assertFalse(calls.exists())

    def test_duplicate_or_missing_handler_is_blocked(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as tmp:
                _, script, calls, rc, env = self.fixture(Path(tmp))
                rc.write_text(rc.read_text() * 2 if duplicate else 'on init\n    mkdir /foo\n')
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('firmware_handler_not_unique', result.stdout)
                self.assertFalse(calls.exists())

    def test_preflight_failures_never_request_property(self):
        cases = [('MOCK_UID', '2000', 'root_required'),
                 ('MOCK_MOUNT_FAILURE', '1', 'effect_mount_failed'),
                 ('MOCK_LOCK_FAILURE', '1', 'recovery_in_progress'),
                 ('MOCK_LINKER_FAILURE', '1', 'linker_dependency_resolution_failed'),
                 ('MOCK_FACTORY_PIDS', '101 201', 'factory_process_not_unique'),
                 ('MOCK_PROPERTY', '1', 'firmware_reload_already_in_progress'),
                 ('MOCK_IGNORE_EFFECTS', 'true', 'effects_disabled_by_firmware')]
        for key, value, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                _, script, calls, _, env = self.fixture(Path(tmp))
                env[key] = value
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout)
                self.assertFalse(calls.exists())

    def test_native_ready_only_skips_reload_for_applied_mount_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, calls, _, env = self.fixture(root)
            (root / 'proc/101/maps').write_text('/vendor/lib64/soundfx/libjamesdsp.so\n')
            helper = module / 'common/files/control/arm64-v8a/jdspctl'
            helper.parent.mkdir(parents=True)
            self.executable(helper, 'echo JDSPCTL:OK:ready=1:protocol=3:contexts=1:writable=1:publication=3\n')
            timeout = self.executable(root / 'bin/timeout', 'shift; exec "$@"\n')
            env.update(JDSP_CONTROL_HELPER=str(helper), JDSP_TIMEOUT_BIN=str(timeout))
            skip = self.run_script(script, env)
            self.assertEqual(skip.returncode, 0, skip.stdout + skip.stderr)
            self.assertIn('native_context_already_ready', skip.stdout)
            self.assertFalse(calls.exists())
            (module / 'logs/aidl-effect-mount.generation').write_text('new-xml\n')
            reload = self.run_script(script, env)
            self.assertEqual(reload.returncode, 0, reload.stdout + reload.stderr)
            self.assertTrue(calls.exists())
            self.assertEqual((module / 'logs/aidl-effect-mount.activated').read_text(), 'new-xml\n')

    def test_failed_request_consumes_boot_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, script, calls, _, env = self.fixture(Path(tmp))
            env['MOCK_SETPROP_FAILURE'] = '1'
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('firmware_reload_request_failed', result.stdout)
            self.assertTrue(calls.exists())
            self.assertTrue((module / 'logs/audio-hal-reload-aidl.boot-id').exists())

    def test_missing_deleted_or_unrelated_map_cannot_be_reported_as_loaded(self):
        for mapping in ('', '/vendor/lib64/soundfx/libjamesdsp.so (deleted)\n', '/other/module/libjamesdsp.so\n'):
            with self.subTest(mapping=mapping), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, script, calls, _, env = self.fixture(root)
                (root / 'proc/201/maps').write_text(mapping)
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('reload_or_library_mapping_not_observed', result.stdout)
                self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')

    def test_disable_stale_boot_legacy_guard_policy_and_overlay_blocks(self):
        for case in ('disable', 'stale', 'legacy', 'policy', 'overlay', 'exe'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module, script, calls, _, env = self.fixture(root)
                if case == 'disable':
                    (module / '.aidl-recovery-disabled').touch()
                elif case == 'stale':
                    (root / 'boot-id').write_text('boot-2\n')
                elif case == 'legacy':
                    (module / 'logs/audio-hal-reload-samsung.boot-id').write_text('boot-1\n')
                elif case == 'policy':
                    (module / 'logs/native-control.status').write_text('BLOCKED policy=missing\n')
                elif case == 'overlay':
                    (root / 'init/vendor/lib64/soundfx/libjamesdsp.so').write_bytes(b'other')
                elif case == 'exe':
                    (root / 'proc/101/exe').unlink()
                    (root / 'proc/101/exe').symlink_to('/data/unknown/audio')
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(calls.exists())

    def test_property_must_reset_and_target_pids_must_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, script, calls, _, env = self.fixture(Path(tmp))
            env['MOCK_PROPERTY_AFTER'] = '1'
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('reload_or_library_mapping_not_observed', result.stdout)
            self.assertTrue(calls.exists())

    def test_library_unload_after_five_samples_is_not_hidden_as_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, calls, _, env = self.fixture(root)
            self.executable(Path(env['JDSP_SLEEP_BIN']), f'''n=$(cat "{root}/samples" 2>/dev/null || echo 0)
n=$((n + 1)); echo "$n" >"{root}/samples"
[ "$n" -lt 5 ] || : >"{root}/proc/201/maps"
''')
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('audio_services_unstable_after_reload', result.stdout)
            self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')

    def test_real_mount_bridge_composes_before_the_single_firmware_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, calls, _, env = self.fixture(root)
            (module / 'aidl-effect-mount.sh').write_bytes((ROOT / 'aidl-effect-mount.sh').read_bytes())
            config = root / 'init/vendor/etc/audio_effects_config.xml'
            config.write_text('<audio_effects_conf version="2.0">\n<libraries>\n</libraries>\n<effects>\n</effects>\n</audio_effects_conf>\n')
            self.executable(root / 'bin/ls', 'case "$2" in *.so) echo u:object_r:vendor_file:s0 ;; *) echo u:object_r:vendor_configs_file:s0 ;; esac\n')
            self.executable(root / 'bin/chcon', 'exit 0\n')
            self.executable(root / 'bin/nsenter', 'shift 4; [ "$1" != /system/bin/true ] || exit 0; exec "$@"\n')
            self.executable(root / 'bin/mount', f'echo "$*" >>"{root}/mount.calls"\ncp "$2" "{root}/init$3"\n')
            self.executable(Path(env['JDSP_SETPROP_BIN']),
                f'grep -q "{UUID}" "{config}" && test -f "{root}/mount.calls" || exit 1\necho "$*" >>"{calls}"\n')
            for name in ('ls', 'chcon', 'nsenter', 'mount'):
                env['JDSP_' + name.upper() + '_BIN'] = str(root / 'bin' / name)
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')
            self.assertEqual((module / 'logs/aidl-effect-mount.generation').read_text(),
                             (module / 'logs/aidl-effect-mount.activated').read_text())


if __name__ == '__main__':
    unittest.main()
