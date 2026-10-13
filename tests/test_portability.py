import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JDSP_UUID = "f27317f4-c984-4de6-9a90-545759495bf2"
STOCK_UUID = "11111111-2222-3333-4444-555555555555"


def mock_executable(path: pathlib.Path, body: str) -> pathlib.Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


class PortabilityTests(unittest.TestCase):
    def make_module(self, tmp: str) -> pathlib.Path:
        module = pathlib.Path(tmp)
        (module / "system/vendor/lib64/soundfx").mkdir(parents=True)
        (module / "system/etc").mkdir(parents=True)
        (module / "logs").mkdir()
        shutil.copy2(ROOT / "post-fs-data.sh", module / "post-fs-data.sh")
        (module / ".AIDL").touch()
        (module / "system/vendor/lib64/soundfx/libjamesdsp.so").touch()
        mock_executable(module / "flock", "exit 0\n")
        return module

    def run_post_fs(
        self,
        module: pathlib.Path,
        *,
        vendor_config: pathlib.Path | None = None,
        legacy_config: pathlib.Path | None = None,
        config_roots: list[pathlib.Path] | None = None,
        fs_root: pathlib.Path | None = None,
        profile: str = "portable",
        linker_body: str = "exit 0\n",
        flock: pathlib.Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        linker = mock_executable(module / "linker", linker_body)
        env = {
            **os.environ,
            "KSU_LATE_LOAD": "1",
            "JDSP_COMPAT_PROFILE": profile,
            "JDSP_LINKER_BIN": str(linker),
            "JDSP_FLOCK_BIN": str(flock or module / "flock"),
        }
        if vendor_config is not None:
            env["JDSP_SOURCE_VENDOR_CONFIG"] = str(vendor_config)
        if legacy_config is not None:
            env["JDSP_SOURCE_LEGACY_CONFIG"] = str(legacy_config)
        if config_roots is not None:
            env["JDSP_CONFIG_ROOTS"] = " ".join(str(root) for root in config_roots)
        if fs_root is not None:
            env["JDSP_FS_ROOT"] = str(fs_root)
        return subprocess.run(
            ["sh", str(module / "post-fs-data.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_native_config(self, path: pathlib.Path, extra_line: str = "") -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""
<audio_effects_conf>
    <libraries>
        <library name="stock_fx" path="libsamsungstockaidl.so"/>
    </libraries>
    <effects>
        <effect name="samsung_stock" library="stock_fx" uuid="{STOCK_UUID}"/>
        {extra_line}
    </effects>
</audio_effects_conf>
"""
        )
        return path

    def write_rooted_vendor_config(self, fs_root: pathlib.Path) -> pathlib.Path:
        return self.write_native_config(fs_root / "vendor/etc/audio_effects_config.xml")

    def test_portable_native_config_without_pixel_anchors_is_ready_and_preserves_stock_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            vendor = self.write_rooted_vendor_config(fs_root)

            result = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertIn(JDSP_UUID, patched)
            self.assertIn("libsamsungstockaidl.so", patched)
            self.assertIn(STOCK_UUID, patched)
            self.assertIn("READY late_load=1", (module / "logs/late-load.status").read_text())

    def test_portable_inline_native_config_fails_closed_without_staging_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            vendor = fs_root / "vendor/etc/audio_effects_config.xml"
            vendor.parent.mkdir(parents=True)
            vendor.write_text(
                f'<audio_effects_conf><libraries><library name="stock_fx" path="libsamsungstockaidl.so"/></libraries>'
                f'<effects><effect name="samsung_stock" library="stock_fx" uuid="{STOCK_UUID}"/></effects></audio_effects_conf>\n'
            )

            result = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertFalse((module / "system/vendor/etc/audio_effects_config.xml").exists())
            self.assertIn("BLOCKED reason=native_vendor_config_unsupported", (module / "logs/late-load.status").read_text())

    def test_portable_malformed_native_config_fails_closed_without_staging_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            vendor = fs_root / "vendor/etc/audio_effects_config.xml"
            vendor.parent.mkdir(parents=True)
            vendor.write_text(
                """
<audio_effects_conf>
    <libraries>
        <library name="stock_fx" path="libsamsungstockaidl.so"/>
    </libraries>
    <effects>
        <effect name="stock" library="stock_fx" uuid="11111111-2222-3333-4444-555555555555"/>
    </effects>
"""
            )

            result = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertFalse((module / "system/vendor/etc/audio_effects_config.xml").exists())
            self.assertIn("BLOCKED reason=native_vendor_config_unsupported", (module / "logs/late-load.status").read_text())

    def test_portable_commented_libraries_tag_fails_closed_without_staging_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            vendor = fs_root / "vendor/etc/audio_effects_config.xml"
            vendor.parent.mkdir(parents=True)
            vendor.write_text(
                """
<audio_effects_conf>
    <!-- <libraries> -->
    <!-- </libraries> -->
    <effects>
        <effect name="stock" library="stock_fx" uuid="11111111-2222-3333-4444-555555555555"/>
    </effects>
</audio_effects_conf>
"""
            )

            result = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertFalse((module / "system/vendor/etc/audio_effects_config.xml").exists())
            self.assertIn("BLOCKED reason=native_vendor_config_unsupported", (module / "logs/late-load.status").read_text())

    def test_portable_missing_native_config_does_not_translate_legacy_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            legacy = module / "system_audio_effects.xml"
            legacy.write_text(
                f"""
<audio_effects_conf>
    <libraries>
        <library name="bundle" path="libbundlewrapper.so"/>
    </libraries>
    <effects>
        <effect name="equalizer" library="bundle" uuid="{STOCK_UUID}"/>
    </effects>
</audio_effects_conf>
"""
            )

            result = self.run_post_fs(
                module,
                vendor_config=module / "missing_vendor_config.xml",
                legacy_config=legacy,
                config_roots=[fs_root / "vendor/etc"],
                fs_root=fs_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertIn("BLOCKED reason=native_vendor_config_missing", (module / "logs/late-load.status").read_text())

    def test_config_roots_selects_single_native_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            self.write_native_config(fs_root / "vendor/etc/audio_effects_config.xml")

            result = self.run_post_fs(module, config_roots=[fs_root / "vendor/etc"], fs_root=fs_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertIn(JDSP_UUID, patched)
            self.assertIn("libsamsungstockaidl.so", patched)

    def test_config_roots_prefers_canonical_vendor_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            self.write_native_config(fs_root / "vendor/etc/audio_effects_config.xml")
            self.write_native_config(fs_root / "odm/etc/audio_effects_config.xml")

            result = self.run_post_fs(
                module,
                config_roots=[fs_root / "vendor/etc", fs_root / "odm/etc"],
                fs_root=fs_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertTrue((module / "system/vendor/etc/audio_effects_config.xml").exists())
            self.assertFalse((module / "system/odm/etc/audio_effects_config.xml").exists())

    def test_config_roots_selects_highest_priority_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            self.write_native_config(fs_root / "odm/etc/audio_effects_config.xml")
            self.write_native_config(fs_root / "product/etc/audio_effects_config.xml")

            result = self.run_post_fs(
                module,
                config_roots=[fs_root / "odm/etc", fs_root / "product/etc"],
                fs_root=fs_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertTrue((module / "system/odm/etc/audio_effects_config.xml").exists())
            self.assertFalse((module / "system/product/etc/audio_effects_config.xml").exists())

    def test_all_valid_vendor_sku_configs_are_patched_for_active_sku_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            alor = self.write_native_config(
                fs_root / "vendor/etc/audio/sku_alor/audio_effects_config.xml"
            )
            canoe = self.write_native_config(
                fs_root / "vendor/etc/audio/sku_canoe/audio_effects_config.xml"
            )

            result = self.run_post_fs(
                module,
                config_roots=[fs_root / "vendor/etc"],
                fs_root=fs_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            for source in (alor, canoe):
                logical_relative = source.relative_to(fs_root / "vendor")
                staged = module / "system/vendor" / logical_relative
                patched = staged.read_text()
                self.assertIn(JDSP_UUID, patched)
                self.assertIn(STOCK_UUID, patched)
                self.assertEqual(patched.count('name="jdsp"'), 1)
            context = (module / "logs/late-load-context.txt").read_text()
            self.assertIn("portable_candidate_count=2", context)
            self.assertIn("prepared_config=/vendor/etc/audio/sku_alor/audio_effects_config.xml", context)
            self.assertIn("prepared_config=/vendor/etc/audio/sku_canoe/audio_effects_config.xml", context)

    def test_missing_flock_fails_closed_before_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            vendor = self.write_rooted_vendor_config(fs_root)
            missing_flock = module / "missing-flock"

            result = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root, flock=missing_flock)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "BLOCKED reason=late_load_lock_unavailable\n",
            )

    def test_portable_preparation_is_idempotent_when_reentered(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_module(tmp)
            fs_root = module / "device-root"
            vendor = self.write_rooted_vendor_config(fs_root)

            first = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root)
            second = self.run_post_fs(module, vendor_config=vendor, fs_root=fs_root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertEqual(patched.count('name="jdsp"'), 1)
            self.assertEqual(patched.count('name="jamesdsp"'), 1)
            self.assertEqual(patched.count(JDSP_UUID), 1)
            self.assertIn(STOCK_UUID, patched)

    def make_patch_module(self, tmp: str, patchelf_body: str) -> pathlib.Path:
        module = pathlib.Path(tmp)
        (module / "system/vendor/lib64/soundfx").mkdir(parents=True)
        (module / "system/vendor/lib64/soundfx/libjamesdsp.so").touch()
        (module / "tools").mkdir()
        shutil.copy2(ROOT / "patch.sh", module / "patch.sh")
        mock_executable(module / "tools/patchelf", patchelf_body)
        return module

    def run_patch(
        self,
        module: pathlib.Path,
        *,
        late_load: str = "0",
        profile: str | None = None,
        path_prefix: pathlib.Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "MODPATH": str(module), "MOD_VENDOR": str(module / "system/vendor")}
        if path_prefix is not None:
            env["PATH"] = f"{path_prefix}:{env['PATH']}"
        if late_load is not None:
            env["KSU_LATE_LOAD"] = late_load
        if profile is not None:
            env["JDSP_COMPAT_PROFILE"] = profile
        command = f'AIDL=true; . "{module / "patch.sh"}"; echo after-source'
        return subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True, check=False)

    def test_patch_keeps_early_boot_soname_adaptation_enabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "patchelf.log"
            module = self.make_patch_module(
                tmp,
                f'''echo "$@" >>"{log}"
if [ "$1" = --print-needed ]; then echo android.hardware.audio.effect-V1-ndk.so; fi
exit 0
''',
            )

            result = self.run_patch(module, late_load="0")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--print-needed", log.read_text())
            self.assertIn("after-source", result.stdout)

    def test_patch_skips_portable_late_load_soname_guessing_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "patchelf.log"
            module = self.make_patch_module(tmp, f'echo "$@" >>"{log}"\nexit 0\n')

            result = self.run_patch(module, late_load="1", profile="portable")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("--print-needed", log.read_text() if log.exists() else "")
            self.assertIn("SONAME patch skipped", result.stdout)
            self.assertIn("after-source", result.stdout)

    def test_patch_keeps_mustang_late_load_soname_adaptation_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "patchelf.log"
            module = self.make_patch_module(
                tmp,
                f'''echo "$@" >>"{log}"
if [ "$1" = --print-needed ]; then echo android.hardware.audio.effect-V1-ndk.so; fi
exit 0
''',
            )

            result = self.run_patch(module, late_load="1", profile="mustang")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--print-needed", log.read_text())
            self.assertIn("after-source", result.stdout)

    def test_patch_replace_failure_returns_to_sourcing_caller(self):
        with tempfile.TemporaryDirectory() as tmp:
            mocks = pathlib.Path(tmp) / "mocks"
            mocks.mkdir()
            mock_executable(
                mocks / "find",
                'echo /vendor/lib64/android.hardware.audio.effect-V9-ndk.so\n',
            )
            module = self.make_patch_module(
                tmp,
                '''if [ "$1" = --print-needed ]; then echo android.hardware.audio.effect-V1-ndk.so; exit 0; fi
exit 7
''',
            )

            result = self.run_patch(module, late_load="1", profile="mustang", path_prefix=mocks)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AIDL NDK SONAME patch failed", result.stdout)
            self.assertIn("after-source", result.stdout)

    def make_audio_reload_module(self, root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
        module = root / "module"
        module.mkdir()
        (module / "logs").mkdir()
        shutil.copy2(ROOT / "audio-reload.sh", module / "audio-reload.sh")
        (module / ".late-load-reload-experimental").touch()
        xml = root / "audio_effects_config.xml"
        xml.write_text(f'<effect name="jamesdsp" uuid="{JDSP_UUID}"/>\n')
        lib = root / "libjamesdsp.so"
        lib.touch()
        setprop_log = root / "setprop.log"
        return module, xml, lib, setprop_log

    def run_portable_audio_reload(
        self,
        module: pathlib.Path,
        xml: pathlib.Path,
        lib: pathlib.Path,
        setprop_log: pathlib.Path,
        dumpsys_body: str,
    ) -> subprocess.CompletedProcess[str]:
        mocks = module.parent / "mocks"
        mocks.mkdir()
        linker = mock_executable(mocks / "linker64", "exit 0\n")
        service = mock_executable(
            mocks / "service",
            'if [ "$1" = check ] && [ "$2" = android.hardware.audio.effect.IFactory/default ]; then echo "Service $2: found"; else echo "Service $2: not found"; fi\n',
        )
        dumpsys = mock_executable(mocks / "dumpsys", dumpsys_body)
        setprop = mock_executable(mocks / "setprop", f'echo "$@" >>"{setprop_log}"\n')
        env = {
            **os.environ,
            "KSU_LATE_LOAD": "1",
            "JDSP_COMPAT_PROFILE": "portable",
            "JDSP_EFFECT_XML": str(xml),
            "JDSP_EFFECT_LIB": str(lib),
            "JDSP_LINKER_BIN": str(linker),
            "JDSP_SERVICE_BIN": str(service),
            "JDSP_DUMPSYS_BIN": str(dumpsys),
            "JDSP_SETPROP_BIN": str(setprop),
        }
        return subprocess.run(
            ["sh", str(module / "audio-reload.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_portable_audio_reload_blocks_missing_files_without_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, xml, lib, setprop_log = self.make_audio_reload_module(root)
            xml.unlink()

            result = self.run_portable_audio_reload(module, xml, lib, setprop_log, "echo 'Effects (0):'\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(setprop_log.exists())
            self.assertIn(
                "BLOCKED reason=mounted_audio_effects_xml_missing",
                (module / "logs/audio-reload.status").read_text(),
            )

    def test_portable_audio_reload_reports_device_specific_refresh_without_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, xml, lib, setprop_log = self.make_audio_reload_module(root)

            result = self.run_portable_audio_reload(module, xml, lib, setprop_log, "echo 'Effects (21):'\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(setprop_log.exists())
            status = (module / "logs/audio-reload.status").read_text()
            self.assertIn("BLOCKED reason=default_factory_needs_device_specific_refresh", status)
            self.assertIn("restart=not_attempted", status)

    def test_portable_audio_reload_descriptor_present_is_not_app_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, xml, lib, setprop_log = self.make_audio_reload_module(root)

            result = self.run_portable_audio_reload(
                module,
                xml,
                lib,
                setprop_log,
                f"echo 'Effects (22):'\necho 'UUID: {JDSP_UUID}'\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(setprop_log.exists())
            status = (module / "logs/audio-reload.status").read_text()
            self.assertIn("READY reason=target_already_loaded", status)
            self.assertIn("restart=not_needed", status)


if __name__ == "__main__":
    unittest.main()
