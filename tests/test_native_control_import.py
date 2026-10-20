from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import import_native_control_v4 as importer


class NativeImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'driver.so'
        data = bytearray(64)
        data[:6] = b'\x7fELF\x02\x01'
        data[16:20] = b'\x03\x00\xb7\x00'
        self.path.write_bytes(data)
        self.report = {'sha256': sha256(data).hexdigest(), 'direct_dt_needed': ['libbinder_ndk.so']}
        self.dynamic = '(NEEDED) Shared library: [libbinder_ndk.so]\n(SONAME) Library soname: [libjamesdspaidl.so]\n(FLAGS_1) Flags: NODELETE'
        self.symbols = '\n'.join('1: 0010 32 FUNC GLOBAL DEFAULT 12 ' + name
                                 for name in ('queryEffect', 'createEffect', 'destroyEffect'))

    def inspect(self, report=None):
        return importer.inspect_elf(self.path, 'driver', report or self.report, 'readelf')

    def test_validated_driver_is_not_executed(self):
        with patch.object(importer.subprocess, 'check_output', side_effect=[self.dynamic, self.symbols]) as run:
            self.assertEqual(self.inspect()['sha256'], self.report['sha256'])
            self.assertEqual(run.call_args_list[0].args[0][0], 'readelf')

    def test_wrong_hash_rejected_before_inspection(self):
        with patch.object(importer.subprocess, 'check_output') as run:
            with self.assertRaisesRegex(ValueError, 'Unexpected or retired'):
                self.inspect({'sha256': '0' * 64})
            run.assert_not_called()

    def test_dependency_report_must_match_actual_elf(self):
        with patch.object(importer.subprocess, 'check_output', return_value=self.dynamic):
            with self.assertRaisesRegex(ValueError, 'DT_NEEDED'):
                self.inspect(dict(self.report, direct_dt_needed=['wrong.so']))

    def test_lifetime_gate_is_required(self):
        with patch.object(importer.subprocess, 'check_output', return_value=self.dynamic.replace('NODELETE', '')):
            with self.assertRaisesRegex(ValueError, 'NODELETE'):
                self.inspect()

    def test_undefined_factory_symbol_is_not_an_export(self):
        symbols = self.symbols.replace('DEFAULT 12 queryEffect', 'DEFAULT UND queryEffect')
        with patch.object(importer.subprocess, 'check_output', side_effect=[self.dynamic, symbols]):
            with self.assertRaisesRegex(ValueError, 'factory export'):
                self.inspect()

    def test_failed_staging_preserves_existing_candidate(self):
        commit = 'a' * 40
        module = self.root / 'module'
        (module / 'native-control').mkdir(parents=True)
        app = module / importer.package.EXPECTED_PATHS['app']
        app.parent.mkdir(parents=True)
        app.write_bytes(b'original apk')
        app.with_suffix('.apk.meta').write_text('versionCode=58\n')
        driver = module / importer.package.EXPECTED_PATHS['driver']
        driver.parent.mkdir(parents=True)
        driver.write_bytes(b'original driver')
        manifest = module / importer.package.MANIFEST
        manifest.write_text(json.dumps({'iteration': 4, 'service': 'jdsp.control', 'wireProtocol': 3,
            'nativeSource': {'commit': commit}, 'artifacts': {'app': None}}))
        before = manifest.read_bytes()
        provenance = self.root / 'provenance.json'
        provenance.write_text(json.dumps({'source': {'commit': commit},
            'artifacts': {'driver': self.report, 'helper': self.report}}))
        with patch.object(importer, 'inspect_elf', return_value={}), \
                patch.object(importer.package, 'verify_artifacts', side_effect=ValueError('test verification failed')):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                importer.import_candidate(self.path, self.path, provenance, module, 'readelf')
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(driver.read_bytes(), b'original driver')
        self.assertFalse((module / importer.package.EXPECTED_PATHS['helper']).exists())


if __name__ == '__main__':
    unittest.main()
