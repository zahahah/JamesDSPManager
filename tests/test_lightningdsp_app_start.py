import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BackgroundAppStartTests(unittest.TestCase):
    def fixture(self, root, boot='1', package=True, failure=False):
        module = root / 'module'
        module.mkdir()
        calls = root / 'calls'
        calls.write_text('')
        tools = root / 'bin'
        tools.mkdir()

        def tool(name, body):
            path = tools / name
            path.write_text('#!/bin/sh\n' + body.replace('\\n', '\n'))
            path.chmod(0o755)
            return str(path)

        env = dict(os.environ)
        env['LDSP_SLEEP_BIN'] = tool('sleep', f'echo "sleep:$*" >>"{calls}"\n')
        env['LDSP_TIMEOUT_BIN'] = tool('timeout', 'shift\nexec "$@"\n')
        env['LDSP_GETPROP_BIN'] = tool('getprop', f'echo {boot}\n')
        env['LDSP_PM_BIN'] = tool('pm', 'echo package:/data/app/lightning/base.apk\n' if package else 'exit 1\n')
        env['LDSP_AM_BIN'] = tool('am', f'''case "$1" in
get-current-user) echo 10 ;;
start-foreground-service)
    echo "am:$*" >>"{calls}"
    {"echo 'Error: denied'; exit 1" if failure else "echo 'Starting service'"} ;;
*) exit 1 ;;
esac
''')
        return module, calls, env

    def run_start(self, module, env):
        return subprocess.run(['sh', str(ROOT / 'lightningdsp-app-start.sh'), str(module)],
                              env=env, text=True, capture_output=True, timeout=15)

    def test_ten_second_delay_targets_current_user_service_without_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, calls, env = self.fixture(Path(tmp))
            result = self.run_start(module, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            log = calls.read_text()
            self.assertEqual(log.splitlines()[0], 'sleep:10')
            self.assertIn('start-foreground-service --user 10', log)
            self.assertIn('com.lightning.dsp.root.service.START_BACKGROUND', log)
            self.assertNotIn('MainActivity', log)
            self.assertNotIn('force-stop', log)
            self.assertIn('DISPATCHED', (module / 'logs/app-start.status').read_text())
            self.assertIn('processing=unverified', (module / 'logs/app-start.status').read_text())

    def test_disabled_module_never_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, calls, env = self.fixture(Path(tmp))
            (module / 'disable').touch()
            self.assertEqual(self.run_start(module, env).returncode, 0)
            self.assertEqual(calls.read_text(), '')

    def test_boot_or_missing_package_wait_is_bounded(self):
        for boot, package in [('0', True), ('1', False)]:
            with self.subTest(boot=boot, package=package), tempfile.TemporaryDirectory() as tmp:
                module, calls, env = self.fixture(Path(tmp), boot=boot, package=package)
                self.assertNotEqual(self.run_start(module, env).returncode, 0)
                self.assertNotIn('am:start-foreground-service', calls.read_text())
                self.assertEqual(calls.read_text().count('sleep:2\n'), 29)
                self.assertIn('DEFERRED', (module / 'logs/app-start.status').read_text())

    def test_failed_dispatch_never_claims_ready_or_restarts_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, calls, env = self.fixture(Path(tmp), failure=True)
            self.assertNotEqual(self.run_start(module, env).returncode, 0)
            self.assertEqual(calls.read_text().count('am:start-foreground-service'), 1)
            self.assertIn('FAILED', (module / 'logs/app-start.status').read_text())

    def test_verified_late_load_dispatch_waits_for_recovery_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / 'module'
            module.mkdir()
            (module / 'service.sh').write_bytes((ROOT / 'service.sh').read_bytes())
            events = root / 'events'
            for name, body in [
                ('audio-hal-recovery.sh', f'echo recovery >>"{events}"\n'),
                ('lightningdsp-app-start.sh', f'echo "startup:$2" >>"{events}"\n'),
            ]:
                path = module / name
                path.write_text('#!/bin/sh\n' + body)
                path.chmod(0o755)
            sleep = root / 'sleep'
            sleep.write_text(f'#!/bin/sh\necho "delay:$1" >>"{events}"\n')
            sleep.chmod(0o755)
            env = dict(os.environ, KSU_LATE_LOAD='1', LDSP_SLEEP_BIN=str(sleep))
            result = subprocess.run(['sh', str(module / 'service.sh')], env=env,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            for _ in range(100):
                if events.exists() and 'startup:0' in events.read_text():
                    break
                time.sleep(0.02)
            self.assertEqual(events.read_text().splitlines(), ['delay:10', 'recovery', 'startup:0'])

    def test_scheduler_and_payload_keep_recovery_separate(self):
        service = (ROOT / 'service.sh').read_text()
        self.assertEqual(service.count('sh "$MODPATH/audio-hal-recovery.sh" --auto-once'), 1)
        self.assertIn('schedule_lightningdsp_background_start', service)
        self.assertIn('lightningdsp-app-start.sh', (ROOT / 'tools/package_lightningdsp.py').read_text())
        script = (ROOT / 'lightningdsp-app-start.sh').read_text()
        self.assertNotIn('setEnabled', script)
        self.assertNotIn('uninstall', script)
        self.assertNotIn('ctl.restart', script)


if __name__ == '__main__':
    unittest.main()
