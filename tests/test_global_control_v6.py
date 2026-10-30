from hashlib import sha256
import json
from fnmatch import fnmatch
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
import package_native_control_v6 as package
import import_native_control_v6 as importer


def elf(payload=b'code'):
    header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01' + b'\0' * 10,
                         3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 64, 0, 0)
    size = 120 + len(payload)
    return header + struct.pack('<IIQQQQQQ', 1, 5, 0, 0, 0, size, size, 4096) + payload


@unittest.skip("Historical JDSP v6 candidate importer; rebrand distribution is covered by package_lightningdsp.py.")
class EmbeddedV6Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.value = json.loads((ROOT / 'native-control/v6-candidate.json').read_text())
        self.value['state'] = 'ready-for-device-test'
        self.report = {'iteration': 6, 'profile': package.PROFILE['profile'], 'controlProtocol': 3,
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
                    'soname': ['liblightningdsp_v6.so'] if kind == 'driver' else [],
                    'nodelete': kind == 'driver'}
        self.report['embeddedCodeEvidence']['loadSegmentsSha256'] = package.gate.load_fingerprint(
            (self.root / package.EXPECTED_PATHS['driver']).read_bytes())
        meta = self.root / 'common/files/LightningDSP.apk.meta'
        meta.write_text('versionCode=62\n')
        (self.root / 'native-control').mkdir()
        notices = b'license fixture for synthetic artifacts'
        (self.root / package.NOTICES).write_bytes(notices)
        self.value['notices'] = {'path': package.NOTICES, 'sha256': sha256(notices).hexdigest(),
                                 'sizeBytes': len(notices)}
        (self.root / 'module.prop').write_text('id=ainur_lightningdsp\nversion=old\nversionCode=139\nname=old\ndescription=old\n')
        self.write_reports()

    def write_reports(self):
        (self.root / package.MANIFEST).write_text(json.dumps(self.value))
        (self.root / package.PROVENANCE).write_text(json.dumps(self.report))

    def inspector(self, command, text=True):
        if '--dyn-syms' in command:
            return '\n'.join('1: 0010 32 ' + ('OBJECT' if name == 'AELI' else 'FUNC') + ' GLOBAL DEFAULT 12 ' + name for name in package.gate.FACTORY)
        driver = command[-1].endswith('lightningdsplib.so')
        return '\n'.join(('(NEEDED) Shared library: [libbinder_ndk.so]', '(NEEDED) Shared library: [libc.so]',
                          '(SONAME) Library soname: [liblightningdsp_v6.so]' if driver else '',
                          '(FLAGS_1) NODELETE' if driver else ''))

    def verify(self):
        with patch.object(package.subprocess, 'check_output', side_effect=self.inspector), \
                patch.object(package.baseline, 'verify_apk'):
            return package.verify_artifacts(self.root, '/trusted/readelf')

    def test_inspected_candidate_passes_without_executing_artifacts(self):
        self.assertEqual(self.verify()['iteration'], 6)

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
        with patch.object(package.subprocess, 'check_output', return_value='ldsp-rebrand'):
            with self.assertRaisesRegex(ValueError, 'approved branch'):
                package.distribution_version(self.root)

    def test_distribution_accepts_integration_branches_with_exact_version(self):
        props = self.root / 'module.prop'
        for branch in ('master', 'pixel-test-new-aidl', 'samsung-test-new-aidl', 'reverb-ring-index-optimization'):
            with self.subTest(branch=branch), patch.object(package.subprocess, 'check_output', return_value=branch):
                props.write_text(f'version={package.VERSION}\nversionCode={package.VERSION_CODE}\n')
                self.assertEqual(package.distribution_version(self.root), package.VERSION)
                props.write_text(f'version={package.VERSION}\nversionCode=141\n')
                with self.assertRaisesRegex(ValueError, 'version metadata'):
                    package.distribution_version(self.root)

    def test_release_metadata_and_ci_glob_match_distribution(self):
        props = (ROOT / 'module.prop').read_text()
        self.assertIn(f'version={package.VERSION}\n', props)
        self.assertIn(f'versionCode={package.VERSION_CODE}\n', props)
        update = json.loads((ROOT / 'update.json').read_text())
        self.assertEqual(update['version'], package.VERSION)
        self.assertEqual(update['versionCode'], package.VERSION_CODE)
        self.assertTrue(update['zipUrl'].endswith(f'/{package.VERSION}/JamesDSPManager-{package.VERSION}.zip'))
        workflow = (ROOT / '.github/workflows/pixel-native-control-v4.yml').read_text()
        pattern = next(line.strip().removeprefix('path: ') for line in workflow.splitlines()
                       if line.strip().startswith('path: dist/'))
        self.assertTrue(fnmatch(f'dist/JamesDSPManager-{package.VERSION}.zip', pattern))

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
            self.assertNotIn('common/files/LightningDSP.apk', archive.namelist())
            self.assertNotIn('update.json', archive.namelist())
            self.assertIn('dsp-thread-profile.sh', archive.namelist())
            self.assertEqual(archive.getinfo('dsp-thread-profile.sh').external_attr >> 16, 0o100755)
            drivers = [name for name in archive.namelist() if name.endswith('/lightningdsplib.so')]
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

    def test_import_refuses_an_unpinned_source_before_tool_execution(self):
        with patch.object(importer, 'inspect_bundle') as inspect:
            with self.assertRaisesRegex(ValueError, 'pinned v6 source'):
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
        (self.root / package.EXPECTED_PATHS['driver']).chmod(0o755)
        with patch.object(importer, 'inspect_bundle', return_value=self.report), \
                patch.object(package.subprocess, 'check_output', side_effect=self.inspector), \
                patch.object(package.baseline, 'verify_apk'):
            result = importer.import_candidate(self.root / package.EXPECTED_PATHS['driver'], Path('debug.so'),
                                               self.root / package.EXPECTED_PATHS['helper'], Path('manifest.xml'),
                                               self.value['nativeSource']['commit'], self.root, 'readelf', 'nm')
        self.assertEqual(result['state'], 'ready-for-device-test')
        self.assertIn('versionCode=' + str(package.VERSION_CODE), (self.root / 'module.prop').read_text())
        self.assertEqual(before, app.read_bytes())
        self.assertEqual((self.root / package.EXPECTED_PATHS['driver']).stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.root / package.EXPECTED_PATHS['helper']).stat().st_mode & 0o777, 0o755)
        self.assertTrue(any('Effect V4/common V5' in note and 'AELI' in note for note in result['notes']))
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
