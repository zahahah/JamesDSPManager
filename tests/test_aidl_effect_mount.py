import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UUID = 'f27317f4-c984-4de6-9a90-545759495bf2'
XML = '''<?xml version="1.0" encoding="UTF-8"?>
<audio_effects_conf version="2.0">
    <!-- Preserve vendor names and paths, not Pixel translations. -->
    <libraries>
        <library name="samsung" path="libsamsung.so"/>
    </libraries>
    <effects>
        <effect name="samsung" library="samsung" uuid="vendor-uuid"/>
    </effects>
    <postprocess>
        <stream type="music"><apply effect="samsung"/></stream>
    </postprocess>
</audio_effects_conf>
'''


class AidlEffectMountTests(unittest.TestCase):
    def executable(self, path, body):
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)
        return path

    def fixture(self, root):
        module = root / 'module'
        (module / 'logs').mkdir(parents=True)
        (module / '.AIDL').touch()
        (module / 'logs/late-load.status').write_text('READY late_load=1 boot_id=boot-1 lib=validated\n')
        (root / 'boot-id').write_text('boot-1\n')
        lib = module / 'system/vendor/lib64/soundfx/libjamesdsp.so'
        lib.parent.mkdir(parents=True)
        lib.write_bytes(b'expected-driver')
        script = module / 'aidl-effect-mount.sh'
        script.write_bytes((ROOT / script.name).read_bytes())
        init = root / 'init'
        sfx = init / 'vendor/lib64/soundfx'
        sfx.mkdir(parents=True)
        (sfx / 'stock.so').write_bytes(b'stock-library')
        (sfx / 'stock-alias.so').symlink_to('stock.so')
        configs = ['vendor/etc/audio_effects_config.xml', 'system/etc/audio_effects.xml',
                   'vendor/etc/audio/sku_qssi/audio_effects.xml', 'odm/etc/audio_effects.xml']
        for name in configs:
            p = init / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(XML)
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        self.executable(bin_dir / 'id', 'echo "${MOCK_UID:-0}"\n')
        self.executable(bin_dir / 'getprop', 'echo "${MOCK_DEVICE:-h8q}"\n')
        self.executable(bin_dir / 'flock', 'exit "${MOCK_LOCK_FAILURE:-0}"\n')
        self.executable(bin_dir / 'chcon', f'echo "$*" >>"{root}/labels.calls"\nexit "${{MOCK_CHCON_FAILURE:-0}}"\n')
        self.executable(bin_dir / 'ls', '''case "$2" in
*.so) echo u:object_r:vendor_file:s0 "$2" ;;
*) echo u:object_r:vendor_configs_file:s0 "$2" ;;
esac
''')
        self.executable(bin_dir / 'nsenter', '''[ "$1" = -t ] && [ "$2" = 1 ] && [ "$3" = -m ] && [ "$4" = -- ] || exit 2
[ "${MOCK_NS_FAILURE:-0}" = 0 ] || exit 1
shift 4
[ "$1" != /system/bin/true ] || exit 0
exec "$@"
''')
        self.executable(bin_dir / 'mount', f'''echo "$*" >>"{root}/mount.calls"
[ "${{MOCK_MOUNT_FAILURE:-0}}" = 0 ] || exit 1
[ "$1" = --bind ] || exit 2
if [ -d "$2" ]; then cp -a "$2/." "{init}$3/"; else cp -p "$2" "{init}$3"; fi
''')
        env = {**os.environ, 'JDSP_INIT_ROOT': str(init), 'JDSP_BOOT_ID_FILE': str(root / 'boot-id')}
        for name in ('id', 'getprop', 'flock', 'chcon', 'ls', 'nsenter', 'mount'):
            env['JDSP_' + name.upper() + '_BIN'] = str(bin_dir / name)
        return module, script, init, env

    def run_script(self, script, env, mode='--mount'):
        return subprocess.run(['sh', str(script), mode], env=env, capture_output=True, text=True, timeout=20)

    def test_mounts_vendor_library_and_all_live_configs_preserving_stock_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, init, env = self.fixture(root)
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('MOUNTED namespace=init changed=5 configs=4', result.stdout)
            self.assertIn('restart=not_requested', result.stdout)
            sfx = init / 'vendor/lib64/soundfx'
            self.assertEqual((sfx / 'libjamesdsp.so').read_bytes(), b'expected-driver')
            self.assertEqual((sfx / 'stock.so').read_bytes(), b'stock-library')
            self.assertTrue((sfx / 'stock-alias.so').is_symlink())
            for config in init.rglob('audio_effects*.xml'):
                text = config.read_text()
                self.assertEqual(text.count(UUID), 1)
                self.assertIn('path="libsamsung.so"', text)
                self.assertIn('<stream type="music"><apply effect="samsung"/></stream>', text)
            self.assertTrue((module / 'logs/aidl-effect-mount.generation').exists())
            calls = (root / 'mount.calls').read_text()
            second = self.run_script(script, env)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn('changed=0', second.stdout)
            self.assertEqual((root / 'mount.calls').read_text(), calls)

    def test_check_stages_without_mounting_or_creating_pending_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, init, env = self.fixture(root)
            result = self.run_script(script, env, '--check')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PREFLIGHT namespace=init planned=5', result.stdout)
            self.assertFalse((root / 'mount.calls').exists())
            self.assertFalse((module / 'logs/aidl-effect-mount.generation').exists())
            self.assertEqual((init / 'vendor/etc/audio_effects_config.xml').read_text(), XML)

    def test_existing_library_is_file_bound_without_hiding_soundfx_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, init, env = self.fixture(root)
            (init / 'vendor/lib64/soundfx/libjamesdsp.so').write_bytes(b'old-driver')
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('/vendor/lib64/soundfx/libjamesdsp.so\n', (root / 'mount.calls').read_text())
            self.assertNotIn('/vendor/lib64/soundfx\n', (root / 'mount.calls').read_text())

    def test_unsupported_config_aborts_all_staging_before_any_mount(self):
        for invalid in ('<config/>\n', XML.replace('<effects>', '<effects/><effects>'),
                        XML.replace('vendor-uuid', UUID), '<!--\n' + XML):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module, script, init, env = self.fixture(root)
                (init / 'odm/etc/audio_effects.xml').write_text(invalid)
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('config_structure_not_supported', result.stdout)
                self.assertFalse((root / 'mount.calls').exists())
                self.assertFalse((module / 'logs/aidl-effect-mount.generation').exists())

    def test_root_namespace_lock_and_label_failures_never_mount(self):
        cases = [('MOCK_UID', '2000', 'root_required'),
                 ('MOCK_NS_FAILURE', '1', 'init_namespace_unavailable'),
                 ('MOCK_LOCK_FAILURE', '1', 'mount_in_progress'),
                 ('MOCK_CHCON_FAILURE', '1', 'library_label_failed')]
        for key, value, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, script, _, env = self.fixture(root)
                env[key] = value
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout)
                self.assertFalse((root / 'mount.calls').exists())

    def test_missing_factory_config_does_not_overlay_vendor_etc_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, init, env = self.fixture(root)
            (init / 'vendor/etc/audio_effects_config.xml').unlink()
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('factory_config_target_missing', result.stdout)
            self.assertFalse((root / 'mount.calls').exists())

    def test_partial_mount_failure_is_reported_and_leaves_generation_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module, script, _, env = self.fixture(root)
            env['MOCK_MOUNT_FAILURE'] = '1'
            result = self.run_script(script, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('init_bind_mount_failed mounted=0', result.stdout)
            self.assertTrue((module / 'logs/aidl-effect-mount.generation').exists())
            self.assertFalse((module / 'logs/aidl-effect-mount.activated').exists())

    def test_normal_boot_stale_boot_or_disable_markers_block_before_mount(self):
        for case in ('normal', 'stale', 'disable', 'recovery-disable', 'skip-mount'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module, script, _, env = self.fixture(root)
                if case == 'normal':
                    (module / 'logs/late-load.status').write_text('READY mode=builtin\n')
                elif case == 'stale':
                    (root / 'boot-id').write_text('boot-2\n')
                else:
                    marker = {'disable': 'disable', 'recovery-disable': '.samsung-firmware-recovery-disabled',
                              'skip-mount': 'skip_mount'}[case]
                    (module / marker).touch()
                result = self.run_script(script, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / 'mount.calls').exists())

    def test_config_security_labels_are_preserved_instead_of_vendor_label_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, script, _, env = self.fixture(root)
            self.executable(Path(env['JDSP_LS_BIN']), '''case "$2" in
*/system/etc/*) echo u:object_r:system_file:s0 ;;
*.so) echo u:object_r:vendor_file:s0 ;;
*) echo u:object_r:vendor_configs_file:s0 ;;
esac
''')
            result = self.run_script(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('u:object_r:system_file:s0', (root / 'labels.calls').read_text())


if __name__ == '__main__':
    unittest.main()
