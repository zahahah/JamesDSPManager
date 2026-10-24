from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import package_native_control_v5 as package
import import_native_control_v5 as importer


def elf(payload=b'code'):
    header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01' + b'\0' * 10,
                         3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 64, 0, 0)
    size = 120 + len(payload)
    return header + struct.pack('<IIQQQQQQ', 1, 5, 0, 0, 0, size, size, 4096) + payload


class EmbeddedV5Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.value = json.loads((ROOT / 'native-control/v5-candidate.json').read_text())
        self.value['state'] = 'ready-for-device-test'
        self.report = {'iteration': 5, 'profile': package.PROFILE['profile'], 'controlProtocol': 3,
                       'state': 'elf-validated-runtime-unverified',
                       'source': {'commit': self.value['nativeSource']['commit'], 'aospManifestSha256': 'b' * 64},
                       'embeddedCodeEvidence': {'definedSymbolsVerified': True,
                                                'unstrippedSha256': 'c' * 64, 'loadSegmentsSha256': 'd' * 64},
                       'artifacts': {}}
        for kind, name in package.EXPECTED_PATHS.items():
            data = b'signed app fixture' if kind == 'app' else elf(kind.encode())
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            artifact = self.value['artifacts'].setdefault(kind, {})
            artifact.update(path=name, sha256=sha256(data).hexdigest(), sizeBytes=len(data))
            if kind != 'app':
                self.report['artifacts'][kind] = {
                    'sha256': artifact['sha256'], 'sizeBytes': len(data),
                    'direct_dt_needed': ['libbinder_ndk.so', 'libc.so'],
                    'soname': ['libjamesdspaidl_v5.so'] if kind == 'driver' else [],
                    'nodelete': kind == 'driver'}
        self.report['embeddedCodeEvidence']['loadSegmentsSha256'] = package.gate.load_fingerprint(
            (self.root / package.EXPECTED_PATHS['driver']).read_bytes())
        meta = self.root / 'common/files/JamesDSPManagerThePBone.apk.meta'
        meta.write_text('versionCode=62\n')
        (self.root / 'native-control').mkdir()
        notices = b'license fixture for synthetic artifacts'
        (self.root / package.NOTICES).write_bytes(notices)
        self.value['notices'] = {'path': package.NOTICES, 'sha256': sha256(notices).hexdigest(),
                                 'sizeBytes': len(notices)}
        (self.root / 'module.prop').write_text('id=ainur_jamesdsp\nversion=old\nversionCode=139\nname=old\ndescription=old\n')
        self.write_reports()

    def write_reports(self):
        (self.root / package.MANIFEST).write_text(json.dumps(self.value))
        (self.root / package.PROVENANCE).write_text(json.dumps(self.report))

    def inspector(self, command, text=True):
        if '--dyn-syms' in command:
            return '\n'.join('1: 0010 32 FUNC GLOBAL DEFAULT 12 ' + name for name in package.gate.FACTORY)
        driver = command[-1].endswith('libjamesdsp.so')
        return '\n'.join(('(NEEDED) Shared library: [libbinder_ndk.so]', '(NEEDED) Shared library: [libc.so]',
                          '(SONAME) Library soname: [libjamesdspaidl_v5.so]' if driver else '',
                          '(FLAGS_1) NODELETE' if driver else ''))

    def verify(self):
        with patch.object(package.subprocess, 'check_output', side_effect=self.inspector), \
                patch.object(package.baseline, 'verify_apk'):
            return package.verify_artifacts(self.root, '/trusted/readelf')

    def test_inspected_candidate_passes_without_executing_artifacts(self):
        self.assertEqual(self.verify()['iteration'], 5)

    def test_awaiting_candidate_cannot_relabel_current_v4(self):
        self.value['state'] = 'awaiting-native-build'
        self.write_reports()
        with self.assertRaisesRegex(ValueError, 'not imported'):
            self.verify()

    def test_hash_source_protocol_and_embedding_proof_are_required(self):
        for section, key, value in ((self.report['source'], 'commit', 'a' * 40),
                                    (self.report, 'controlProtocol', 4),
                                    (self.report['embeddedCodeEvidence'], 'definedSymbolsVerified', False),
                                    (self.value['artifacts']['driver'], 'sha256', '0' * 64)):
            with self.subTest(key=key):
                original = section[key]
                section[key] = value
                self.write_reports()
                with self.assertRaises(ValueError):
                    self.verify()
                section[key] = original

    def test_real_dependency_leak_is_rejected_even_with_forged_report(self):
        original = self.inspector
        def leaked(command, text=True):
            output = original(command, text)
            return output + '\n(NEEDED) Shared library: [android.hardware.audio.effect-V4-ndk.so]' if '--dynamic' in command else output
        with patch.object(package.subprocess, 'check_output', side_effect=leaked), \
                patch.object(package.baseline, 'verify_apk'):
            with self.assertRaisesRegex(ValueError, 'Forbidden runtime'):
                package.verify_artifacts(self.root, 'readelf')

    def test_wrong_branch_cannot_distribute(self):
        with patch.object(package.subprocess, 'check_output', return_value='master'):
            with self.assertRaisesRegex(ValueError, 'samsung-test-new-aidl'):
                package.distribution_version(self.root)

    def test_distribution_accepts_integration_branches_with_exact_version(self):
        props = self.root / 'module.prop'
        for branch in ('pixel-test-new-aidl', 'samsung-test-new-aidl'):
            with self.subTest(branch=branch), patch.object(package.subprocess, 'check_output', return_value=branch):
                props.write_text(f'version={package.VERSION}\nversionCode={package.VERSION_CODE}\n')
                self.assertEqual(package.distribution_version(self.root), package.VERSION)
                props.write_text(f'version={package.VERSION}\nversionCode=141\n')
                with self.assertRaisesRegex(ValueError, 'version metadata'):
                    package.distribution_version(self.root)

    def test_zip_is_deterministic_and_excludes_history_and_classic_app(self):
        for name in package.payloads():
            target = self.root / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'fixture')
        outputs = [self.root / name for name in ('a.zip', 'b.zip')]
        with patch.object(package, 'verify_artifacts', return_value=self.value), \
                patch.object(package, 'distribution_version', return_value=package.VERSION):
            for output in outputs:
                package.build(output, self.root)
        self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
        with ZipFile(outputs[0]) as archive:
            self.assertIn(package.MANIFEST, archive.namelist())
            self.assertIn(package.PROVENANCE, archive.namelist())
            self.assertIn(package.NOTICES, archive.namelist())
            self.assertNotIn('native-control/v4-candidate.json', archive.namelist())
            self.assertNotIn('native-control/provenance.json', archive.namelist())
            self.assertNotIn('common/files/JamesDSPManager.apk', archive.namelist())
            self.assertNotIn('update.json', archive.namelist())
            drivers = [name for name in archive.namelist() if name.endswith('/libjamesdsp.so')]
            self.assertEqual(drivers, [package.EXPECTED_PATHS['driver']])
            self.assertEqual(archive.getinfo(package.EXPECTED_PATHS['helper']).external_attr >> 16, 0o100755)

    def test_failed_stage_preserves_existing_payloads_versions_and_manifest(self):
        names = [package.MANIFEST, package.PROVENANCE, 'module.prop', *package.EXPECTED_PATHS.values()]
        before = {name: (self.root / name).read_bytes() for name in names}
        with patch.object(importer, 'inspect_bundle', return_value=self.report), \
                patch.object(package, 'verify_artifacts', side_effect=ValueError('stage rejected')):
            with self.assertRaisesRegex(ValueError, 'stage rejected'):
                importer.import_candidate(self.root / package.EXPECTED_PATHS['driver'], Path('debug.so'),
                                          self.root / package.EXPECTED_PATHS['helper'], Path('manifest.xml'),
                                          self.value['nativeSource']['commit'], self.root, 'readelf', 'nm')
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in names})

    def test_installer_selects_v5_payload_and_checks_abi_before_library_or_app_changes(self):
        source = (ROOT / 'common/install.sh').read_text()
        check = source.index('if [ -f "$MODPATH/native-control/v5-candidate.json" ] && [ ! -f "$MODPATH/native-control/v6-candidate.json" ]; then')
        first_library_copy = source.index('cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so"')
        app_move = source.index('mv -f "$MODPATH/common/files/JamesDSPManagerThePBone.apk"')
        self.assertLess(check, first_library_copy)
        self.assertLess(check, app_move)
        gate = source[check:source.index('ui_print "- Lib bit detection -"', check)]
        self.assertNotIn('[ "$AIDL" = true ] || abort', gate)
        self.assertIn('AIDL=true', gate)
        self.assertIn('getprop ro.product.cpu.abilist64', gate)
        self.assertNotIn('ro.product.device', gate)

    def test_v5_payload_selection_does_not_require_live_factory_enumeration(self):
        source = (ROOT / 'common/install.sh').read_text()
        start = source.index('if service list')
        block = source[start:source.index('# The AIDL candidate is ELF64.', start)]
        prelude = r'''
abort() { echo "$1"; exit 23; }
getprop() { echo "$MOCK_ABI64"; }
ui_print() { echo "$*"; }
service() { printf '%s\n' "$MOCK_SERVICES"; return "$MOCK_SERVICE_EXIT"; }
cp_ch() { mkdir -p "${2%/*}"; cp "$1" "$2"; }
'''
        # Enumeration can be empty, denied, unavailable, or expose only HIDL.
        for services, code, discovered in (
                ('1 android.hardware.audio.effect.IFactory/default', '0', 'observed'),
                ('', '0', 'not_observed'), ('Permission denied', '1', 'not_observed'),
                ('', '127', 'not_observed'),
                ('android.hardware.audio.effect@7.0::IEffectsFactory/default', '0', 'not_observed')):
            with self.subTest(services=services, code=code):
                (self.root / '.AIDL').unlink(missing_ok=True)
                result = subprocess.run(['sh', '-c', prelude + block + '\nprintf "SELECTED=%s\n" "$QARCH"'],
                                        capture_output=True, text=True,
                                        env={**os.environ, 'MODPATH': str(self.root),
                                             'MOCK_SERVICES': services, 'MOCK_SERVICE_EXIT': code,
                                             'MOCK_ABI64': 'arm64-v8a', 'LIB': '', 'LIB2': ''})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('SELECTED=aidl', result.stdout)
                self.assertTrue((self.root / '.AIDL').exists())
                self.assertEqual((self.root / 'system/lib64/soundfx/libjamesdsp.so').read_bytes(),
                                 (self.root / package.EXPECTED_PATHS['driver']).read_bytes())
                self.assertFalse((self.root / 'system/lib/soundfx/libjamesdsp.so').exists())
                status = (self.root / 'logs/install-transport.status').read_text()
                self.assertIn('factory_discovery=' + discovered, status)
                self.assertIn('compatibility=unverified', status)
                if discovered == 'not_observed':
                    self.assertIn('no legacy/HIDL driver', result.stdout)

    def test_non_v5_payload_is_not_forced_onto_aidl(self):
        source = (ROOT / 'common/install.sh').read_text()
        start = source.index('if service list')
        block = source[start:source.index('ui_print " "', start)]
        (self.root / package.MANIFEST).unlink()
        prelude = 'service() { :; }; ui_print() { :; }; '
        result = subprocess.run(['sh', '-c', prelude + block + '\nprintf "%s" "$AIDL"'],
                                capture_output=True, text=True,
                                env={**os.environ, 'MODPATH': str(self.root)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, 'false')
        self.assertFalse((self.root / 'logs/install-transport.status').exists())

    def test_v5_abi_gate_still_rejects_unsupported_architectures(self):
        source = (ROOT / 'common/install.sh').read_text()
        start = source.index('if [ -f "$MODPATH/native-control/v5-candidate.json" ] && [ ! -f "$MODPATH/native-control/v6-candidate.json" ]; then')
        block = source[start:source.index('ui_print " "', start)]
        prelude = 'abort() { echo "$1"; exit 23; }; getprop() { echo "$MOCK_ABI64"; }; ui_print() { :; }; '
        for aidl, abi, expected in (('true', 'arm64-v8a', 0), ('true', 'x86_64,arm64-v8a', 0),
                                    ('false', 'arm64-v8a', 0), ('true', 'x86_64', 23),
                                    ('false', 'armeabi-v7a', 23), ('true', '', 23)):
            with self.subTest(aidl=aidl, abi=abi):
                result = subprocess.run(['sh', '-c', prelude + block], capture_output=True, text=True,
                                        env={**os.environ, 'MODPATH': str(self.root), 'AIDL': aidl, 'MOCK_ABI64': abi})
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_import_refuses_an_unpinned_source_before_tool_execution(self):
        with patch.object(importer, 'inspect_bundle') as inspect:
            with self.assertRaisesRegex(ValueError, 'pinned v5 source'):
                importer.import_candidate(Path('driver'), Path('debug'), Path('helper'), Path('manifest'),
                                          '0' * 40, self.root, 'readelf', 'nm')
            inspect.assert_not_called()

    def test_import_provenance_does_not_copy_private_compiler_fields(self):
        raw = json.loads(json.dumps(self.report))
        raw['privateLogs'] = '/private/compiler/workspace/logs'
        raw['source']['workspace'] = '/private/source'
        raw['artifacts']['driver']['file'] = '/private/driver.so'
        output = self.root / 'inspection.json'
        def inspect(command, check):
            self.assertTrue(check)
            self.assertEqual(command[0], sys.executable)
            output.write_text(json.dumps(raw))
        with patch.object(importer.subprocess, 'run', side_effect=inspect):
            result = importer.inspect_bundle(Path('driver'), Path('debug'), Path('helper'), Path('manifest'),
                                             self.value['nativeSource']['commit'], 'readelf', 'nm', output)
        self.assertNotIn('/private', json.dumps(result))
        self.assertNotIn('privateLogs', result)
        self.assertEqual(result['artifacts']['driver']['sha256'], raw['artifacts']['driver']['sha256'])

    def test_successful_import_preserves_app_and_updates_version_only_after_verification(self):
        app = self.root / package.EXPECTED_PATHS['app']
        before = app.read_bytes()
        with patch.object(importer, 'inspect_bundle', return_value=self.report), \
                patch.object(package.subprocess, 'check_output', side_effect=self.inspector), \
                patch.object(package.baseline, 'verify_apk'):
            result = importer.import_candidate(self.root / package.EXPECTED_PATHS['driver'], Path('debug.so'),
                                               self.root / package.EXPECTED_PATHS['helper'], Path('manifest.xml'),
                                               self.value['nativeSource']['commit'], self.root, 'readelf', 'nm')
        self.assertEqual(result['state'], 'ready-for-device-test')
        self.assertIn('versionCode=' + str(package.VERSION_CODE), (self.root / 'module.prop').read_text())
        self.assertEqual(before, app.read_bytes())
        self.verify()

    def test_copy_failure_rolls_back_completed_payload_writes(self):
        names = [package.MANIFEST, package.PROVENANCE, 'module.prop', *package.EXPECTED_PATHS.values()]
        before = {name: (self.root / name).read_bytes() for name in names}
        copy = shutil.copy2
        def fail(source, target):
            if Path(target) == self.root / package.PROVENANCE:
                raise OSError('copy failure')
            return copy(source, target)
        with patch.object(importer, 'inspect_bundle', return_value=self.report), \
                patch.object(package, 'verify_artifacts', return_value=self.value), \
                patch.object(importer.shutil, 'copy2', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'copy failure'):
                importer.import_candidate(self.root / package.EXPECTED_PATHS['driver'], Path('debug.so'),
                                          self.root / package.EXPECTED_PATHS['helper'], Path('manifest.xml'),
                                          self.value['nativeSource']['commit'], self.root, 'readelf', 'nm')
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in names})


if __name__ == '__main__':
    unittest.main()
