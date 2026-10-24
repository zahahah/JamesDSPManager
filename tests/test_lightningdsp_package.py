from pathlib import Path
from fnmatch import fnmatch
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
        self.assertTrue(update['zipUrl'].endswith(f'/{package.VERSION}/LightningDSP-{package.VERSION}.zip'))
        workflow = (ROOT / '.github/workflows/pixel-native-control-v4.yml').read_text()
        self.assertIn('ldsp-rebrand]', workflow)
        self.assertLess(workflow.index('native-control/ldsp-candidate.json'),
                        workflow.index('native-control/v6-candidate.json'))
        self.assertIn('python3 tools/package_lightningdsp.py', workflow)
        pattern = next(line.strip() for line in workflow.splitlines()
                       if line.strip().startswith('dist/LightningDSP-'))
        self.assertTrue(fnmatch(f'dist/LightningDSP-{package.VERSION}.zip', pattern))

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
