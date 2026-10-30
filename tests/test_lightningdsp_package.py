from pathlib import Path
from fnmatch import fnmatch
from hashlib import sha256
import json
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT / 'tools'))
import package_lightningdsp as package


class LightningDSPPackageTests(unittest.TestCase):
    def test_rebrand_zip_is_deterministic_and_contains_only_the_current_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = [Path(tmp) / 'one.zip', Path(tmp) / 'two.zip']
            with patch.object(package, 'verify_candidate', return_value={}), \
                    patch.object(package.subprocess, 'check_output', return_value='ldsp-rebrand'):
                hashes = [package.build(output, ROOT) for output in outputs]

            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            self.assertEqual(hashes[0], hashes[1])
            with ZipFile(outputs[0]) as archive:
                names = set(archive.namelist())
                self.assertIn(package.DRIVER, names)
                self.assertIn(package.HELPER, names)
                self.assertIn(package.APP, names)
                self.assertIn('common/files/LightningDSP.apk.meta', names)
                self.assertNotIn('common/files/JamesDSPManagerThePBone.apk', names)
                self.assertNotIn('common/files/JamesDSPManager.apk', names)
                self.assertNotIn('common/files/dual-entry-arm64/libjamesdsp.so', names)
                self.assertNotIn('common/files/JamesDSP/', '\n'.join(names))
                self.assertNotIn('LightningDSP_banner.png', names)
                self.assertNotIn('JDSP_banner.png', names)
                self.assertEqual(archive.getinfo(package.DRIVER).external_attr >> 16, 0o100644)
                self.assertEqual(archive.getinfo(package.HELPER).external_attr >> 16, 0o100755)

    def test_distribution_metadata_and_ci_match_the_rebrand_release(self):
        props = (ROOT / 'module.prop').read_text()
        self.assertIn('id=ainur_lightningdsp\n', props)
        self.assertIn(f'version={package.VERSION}\n', props)
        self.assertIn(f'versionCode={package.VERSION_CODE}\n', props)
        update = json.loads((ROOT / 'update.json').read_text())
        self.assertEqual(update['version'], package.VERSION)
        self.assertEqual(update['versionCode'], package.VERSION_CODE)
        self.assertTrue(update['zipUrl'].endswith(
            f'/{package.VERSION}/LightningDSP-{package.VERSION}.zip'))
        workflow = (ROOT / '.github/workflows/pixel-native-control-v4.yml').read_text()
        self.assertIn('ldsp-rebrand]', workflow)
        self.assertLess(workflow.index('native-control/ldsp-candidate.json'),
                        workflow.index('native-control/v6-candidate.json'))
        self.assertIn('python3 tools/package_lightningdsp.py', workflow)
        pattern = next(line.strip() for line in workflow.splitlines()
                       if line.strip().startswith('dist/LightningDSP-'))
        self.assertTrue(fnmatch(f'dist/LightningDSP-{package.VERSION}.zip', pattern))

    def test_integrated_app_metadata_matches_the_signed_release_build(self):
        manifest = json.loads((ROOT / package.CANDIDATE).read_text())
        app = manifest['artifacts']['app']
        apk = ROOT / package.APP
        self.assertEqual(app['versionName'], package.APP_VERSION)
        self.assertEqual(app['versionCode'], package.APP_CODE)
        self.assertEqual(app['sha256'], sha256(apk.read_bytes()).hexdigest())
        self.assertEqual(app['sizeBytes'], apk.stat().st_size)
        self.assertEqual(app['signerSha256'], package.TRUSTED_APK_SIGNER)
        self.assertEqual(manifest['appSource']['commit'], package.APP_SOURCE_COMMIT)
        self.assertFalse(manifest['appSource']['builtFromWorkingTree'])
        self.assertEqual(app['sourceCommit'], package.APP_SOURCE_COMMIT)
        self.assertEqual((ROOT / 'common/files/LightningDSP.apk.meta').read_text(),
                         f'versionCode={package.APP_CODE}\n')
        self.assertIn(f'Installing LightningDSP {package.APP_VERSION} root app',
                      (ROOT / 'common/install.sh').read_text())
        # App integration must not silently substitute the matched native pair.
        self.assertEqual(manifest['artifacts']['driver']['sha256'],
                         '5689d5bbb027f176c266095852826f1712c22d17c5955780a393089ac0cb84d9')
        self.assertEqual(manifest['artifacts']['helper']['sha256'],
                         '0e96f2e69e6e94395f77190b8a753eb056a778b4f73e09dc3617e7e80cee2880')

    def test_packager_rejects_inconsistent_app_source_provenance(self):
        original = json.loads((ROOT / package.CANDIDATE).read_text())
        for field in ('appSource', 'artifact'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'native-control').mkdir()
                manifest = json.loads(json.dumps(original))
                if field == 'appSource':
                    manifest['appSource']['commit'] = '0' * 40
                else:
                    manifest['artifacts']['app']['sourceCommit'] = '0' * 40
                (root / package.CANDIDATE).write_text(json.dumps(manifest))
                (root / package.PROVENANCE).write_bytes((ROOT / package.PROVENANCE).read_bytes())
                with self.assertRaisesRegex(ValueError, 'app source/provenance pin mismatch'):
                    package.verify_candidate(root)

    def test_previous_signed_app_cannot_package_new_background_start_script(self):
        signer = f'Signer #1 certificate SHA-256 digest: {package.TRUSTED_APK_SIGNER}'
        badging = f"package: name='{package.APP_PACKAGE}' versionCode='{package.APP_CODE}' versionName='{package.APP_VERSION}'"
        # An otherwise signed/versioned APK must still implement the startup action.
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / 'previous.apk'
            with ZipFile(apk, 'w') as archive:
                archive.writestr('classes.dex', b'previous app without the startup handler')
            with patch.object(package.subprocess, 'check_output', side_effect=[signer, badging]):
                with self.assertRaisesRegex(ValueError, 'lacks background startup support'):
                    package.verify_apk(apk)

    def test_background_start_action_must_be_in_executable_dex_not_an_asset(self):
        signer = f'Signer #1 certificate SHA-256 digest: {package.TRUSTED_APK_SIGNER}'
        badging = f"package: name='{package.APP_PACKAGE}' versionCode='{package.APP_CODE}' versionName='{package.APP_VERSION}'"
        for entry, supported in [('assets/startup.txt', False), ('classes2.dex', True)]:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                apk = Path(tmp) / 'fixture.apk'
                with ZipFile(apk, 'w') as archive:
                    archive.writestr(entry, b'com.lightning.dsp.root.service.START_BACKGROUND')
                with patch.object(package.subprocess, 'check_output', side_effect=[signer, badging]):
                    if supported:
                        package.verify_apk(apk)
                    else:
                        with self.assertRaisesRegex(ValueError, 'lacks background startup support'):
                            package.verify_apk(apk)

    def test_master_cannot_package_the_separate_rebrand(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(package, 'verify_candidate', return_value={}), \
                patch.object(package.subprocess, 'check_output', return_value='master'):
            output = Path(tmp) / 'candidate.zip'
            with self.assertRaisesRegex(ValueError, 'limited to ldsp-rebrand'):
                package.build(output, ROOT)
            self.assertFalse(output.exists())

    def test_module_manager_does_not_advertise_obsolete_banner(self):
        self.assertNotRegex((ROOT / 'module.prop').read_text(), r'(?m)^banner=')
        self.assertNotIn('JDSP_banner.png', package.payloads())
        self.assertNotIn('LightningDSP_banner.png', package.payloads())


if __name__ == '__main__':
    unittest.main()
