import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_aidl_audio_recovery as recovery_tests

ROOT = Path(__file__).resolve().parents[1]


class DualEntryHostTests(unittest.TestCase):
    def fixture(self, root):
        module = root / 'module'
        (module / 'native-control').mkdir(parents=True)
        (module / 'native-control/ldsp-candidate.json').write_text('{}')
        script = module / 'effect-host.sh'
        script.write_bytes((ROOT / script.name).read_bytes())
        init = root / 'init'
        manifest = init / 'vendor/etc/vintf/manifest.xml'
        manifest.parent.mkdir(parents=True)
        manifest.write_text('<manifest>\n<hal format="hidl">\n'
                            '<name>android.hardware.audio.effect</name>\n'
                            '<interface><name>IEffectsFactory</name></interface>\n'
                            '</hal>\n</manifest>\n')
        proc = root / 'proc'
        self.process(proc, 101)
        od = root / 'od'
        od.write_text('#!/bin/sh\necho "7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00 03 00 b7 00"\n')
        od.chmod(0o755)
        return script, proc, manifest, od, {**os.environ, 'LDSP_PROC_ROOT': str(proc),
            'LDSP_INIT_ROOT': str(init), 'LDSP_OD_BIN': str(od)}

    def process(self, proc, pid):
        path = proc / str(pid)
        (path / 'attr').mkdir(parents=True)
        (path / 'attr/current').write_bytes(b'u:r:hal_audio_default:s0\x00')
        (path / 'exe').symlink_to('/vendor/bin/hw/android.hardware.audio.service_64')
        (path / 'maps').write_text('0010 /vendor/lib64/libeffects.so\n')
        (path / 'fd').mkdir()
        (path / 'fd/5').symlink_to('/dev/binderfs/hwbinder')

    def run_script(self, script, env):
        return subprocess.run(['sh', str(script), '--hidl-pid'], env=env,
                              text=True, capture_output=True, timeout=10)

    def test_unique_arm64_declared_legacy_host_is_selected_without_lshal(self):
        with tempfile.TemporaryDirectory() as tmp:
            script, _, _, _, env = self.fixture(Path(tmp))
            result = self.run_script(script, env)
            self.assertEqual((result.returncode, result.stdout), (0, '101\n'), result.stderr)

    def test_unknown_ambiguous_wrong_abi_or_domain_hosts_do_not_authorize_recovery(self):
        for case in ('no_manifest', 'matrix_only', 'ambiguous', '32bit', 'domain', 'maps', 'binder', 'v5'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                script, proc, manifest, od, env = self.fixture(root)
                if case == 'no_manifest': manifest.unlink()
                elif case == 'matrix_only':
                    new = root / 'init/system/etc/vintf/compatibility_matrix.xml'
                    new.parent.mkdir(parents=True); manifest.rename(new)
                elif case == 'ambiguous': self.process(proc, 102)
                elif case == '32bit': od.write_text(od.read_text().replace('46 02', '46 01'))
                elif case == 'domain': (proc / '101/attr/current').write_text('u:r:audioserver:s0')
                elif case == 'maps': (proc / '101/maps').write_text('/vendor/lib64/libeffectsconfig.so\n')
                elif case == 'binder': (proc / '101/fd/5').unlink()
                else: (root / 'module/native-control/ldsp-candidate.json').unlink()
                self.assertNotEqual(self.run_script(script, env).returncode, 0)

    def test_installer_stages_one_dual_entry_payload_without_transport_block(self):
        source = (ROOT / 'common/install.sh').read_text()
        start = source.index('if [ -f "$MODPATH/native-control/ldsp-candidate.json" ]; then')
        block = source[start:source.index('ui_print "- Lib bit detection -"', start)]
        for abi, expected in (('arm64-v8a', 0), ('arm64-v8a,armeabi-v7a', 0), ('armeabi-v7a', 23), ('', 23)):
            with self.subTest(abi=abi), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'native-control').mkdir()
                (root / 'native-control/ldsp-candidate.json').write_text('{}')
                # A leftover old manifest must not overwrite v6 selection.
                (root / 'native-control/v5-candidate.json').write_text('{}')
                prelude = 'abort() { echo "$1"; exit 23; }; getprop() { echo "$ABI"; }; ui_print() { :; }; '
                result = subprocess.run(['sh','-c',prelude + block], env={**os.environ,
                    'MODPATH':str(root), 'AIDL':'false', 'ABI':abi}, capture_output=True,text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                if not expected:
                    self.assertTrue((root / '.DUAL_ENTRY').exists())
                    self.assertIn('payload=dual-entry-arm64 factory_discovery=not_observed',
                                  (root / 'logs/install-transport.status').read_text())
                else: self.assertFalse((root / '.DUAL_ENTRY').exists())
        self.assertIn('CONFIG_LIBDIR=lib64', source)
        self.assertIn('$LIBPATCH\\/$CONFIG_LIBDIR\\/soundfx', source)

    def test_hidl_fallback_composes_with_recovery_without_claiming_registration(self):
        harness = recovery_tests.AidlAudioRecoveryTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, calls, _, env = harness.fixture(root)
            Path(env['LDSP_DUMPSYS_BIN']).write_text('#!/bin/sh\nexit 1\n')
            harness.executable(module / 'effect-host.sh',
                f'if [ -e "{calls}" ]; then echo 201; else echo 101; fi\n')
            result = harness.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('registration=unverified', result.stdout)
            self.assertEqual(calls.read_text(), 'sys.audio.restart.hal 1\n')

    def test_single_override_is_resolved_only_against_the_running_executable(self):
        harness = recovery_tests.AidlAudioRecoveryTests()
        for case in ('valid', 'multiple_override', 'wrong_exe'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module, script, calls, _, env = harness.fixture(root)
                rc = root / 'init/vendor/etc/init/audio.rc'
                original = rc.read_text()
                # Override for the same init service, preserving the actual mock
                # running executable. The duplicate base is not a second host.
                override = original.replace('    user audioserver', '    override\n    user audioserver')
                base = original.split('service vendor.secaudiohal-aidl', 1)[0]
                base = base.replace('/vendor/bin/hw/audiohalservice.qti', '/vendor/bin/hw/android.hardware.audio.service')
                if case == 'wrong_exe':
                    override = override.replace('audiohalservice.qti', 'unrelatedaudio')
                rc.write_text(base + '\n' + override)
                if case == 'multiple_override':
                    (rc.parent / 'extra.rc').write_text(base.replace('    user audioserver', '    override\n    user audioserver'))
                result = harness.run_script(script, env, '--check')
                if case == 'valid': self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                else: self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(calls.exists())


if __name__ == '__main__':
    unittest.main()
