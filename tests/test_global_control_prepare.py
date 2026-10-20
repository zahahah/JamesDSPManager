import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class GlobalControlPrepareTests(unittest.TestCase):
    def prepare(self, directory, opt_in=False):
        module = directory / 'module'
        (module / 'native-control').mkdir(parents=True)
        (module / '.AIDL').touch()
        source = directory / 'vendor_service_contexts'
        source.write_text('other.service u:object_r:other_service:s0\njdsp.control old_label\n')
        for name in ('global-service.rule', 'default-label-opt-in.rule'):
            (module / 'native-control' / name).write_bytes((ROOT / 'native-control' / name).read_bytes())
        helper = module / 'common/files/control/arm64-v8a/jdspctl'
        helper.parent.mkdir(parents=True)
        helper.write_text('fixture, not executed')
        fakebin = directory / 'bin'
        fakebin.mkdir()
        tool = fakebin / 'ksud'
        tool.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$POLICY_CALLS"\n')
        tool.chmod(0o755)
        if opt_in:
            (module / '.jdsp-control-default-label-opt-in').touch()
        result = subprocess.run(['sh', str(ROOT / 'native-control.sh'), 'prepare', str(module)],
            env={**os.environ, 'JDSP_SERVICE_CONTEXTS': str(source), 'KSU_LATE_LOAD': '1',
                 'PATH': str(fakebin) + ':' + os.environ['PATH'], 'POLICY_CALLS': str(directory / 'calls')},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return module, source

    def test_staging_preserves_stock_contexts_and_does_not_claim_label_cache_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, source = self.prepare(root)
            staged = (module / 'system/vendor/etc/selinux/vendor_service_contexts').read_text()
            self.assertEqual(staged.count('jdsp.control'), 1)
            self.assertIn('other.service u:object_r:other_service:s0', staged)
            self.assertIn('jdsp_control_service', staged)
            self.assertIn('old_label', source.read_text()) # no partition modification
            self.assertNotIn('default-label-opt-in', (root / 'calls').read_text())
            self.assertTrue((module / 'system/vendor/bin/jdspctl').stat().st_mode & 0o111)
            status = (module / 'logs/native-control.status').read_text()
            self.assertIn('label_cache=unverified', status)
            self.assertIn('restart=not_requested', status)

    def test_default_label_permission_requires_explicit_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, _ = self.prepare(root, opt_in=True)
            self.assertIn('default-label-opt-in.rule', (root / 'calls').read_text())
            self.assertIn('explicit_default_label_opt_in', (module / 'logs/native-control.status').read_text())

    def test_no_untrusted_app_global_grant_or_automatic_audio_restart(self):
        rules = (ROOT / 'native-control/global-service.rule').read_text()
        self.assertNotIn('untrusted_app', rules)
        self.assertNotIn('default_android_service', rules)
        self.assertNotIn('killall', (ROOT / 'service.sh').read_text())
        script = (ROOT / 'native-control.sh').read_text()
        self.assertNotIn('setenforce', script)
        self.assertNotIn('stop servicemanager', script)
