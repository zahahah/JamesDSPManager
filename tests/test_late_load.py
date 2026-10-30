import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LDSP_UUID = "f27317f4-c984-4de6-9a90-545759495bf2"
XML_UUID = "ce772f20-847d-11df-bb17-0002a5d5c51b"
PIXEL_UUID = "50deaa30-4a83-4b1f-bfe3-dec6d605ede0"
STOCK_UUIDS = """ce772f20-847d-11df-bb17-0002a5d5c51b
8631f300-72e2-11df-b57e-0002a5d5c51b
1d4033c0-8557-11df-9f2d-0002a5d5c51b
119341a0-8469-11df-81f9-0002a5d5c51b
d069d9e0-8329-11df-9168-0002a5d5c51b
e0e6539b-1781-7261-676f-6d7573696340
4a387fc0-8ab3-11df-8bad-0002a5d5c51b
f29a1400-a3bb-11df-8ddc-0002a5d5c51b
c7a511a0-a3bb-11df-860e-0002a5d5c51b
172cdf00-a3bc-11df-a72f-0002a5d5c51b
93f04452-e4fe-41cc-91f9-e475b6d1d69f
fa415329-2034-4bea-b5dc-5b381c8d1e2c
97c4acd1-8b82-4f2f-832e-c2fe5d7a9931
50deaa30-4a83-4b1f-bfe3-dec6d605ede0
c7e3b29d-e797-4cf9-9912-17c1956510cc
f8f88a03-fdf8-4554-8e60-77fbf8f2d3b0
1bf15eb7-8f49-4fd8-8380-0767fd5680f3
99fb2ecb-3426-4a0e-8082-1a1da5604b7d
7b491460-8d4d-11e0-bd61-0002a5d5c51b
58b4b260-8e06-11e0-aa8e-0002a5d5c51b
6507a0e2-a9bd-44ca-9116-b740a284ee5f"""


def mock_executable(path: pathlib.Path, body: str) -> pathlib.Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


class LateLoadTests(unittest.TestCase):
    def test_late_load_xml_replacements_are_atomic(self):
        script = (ROOT / "post-fs-data.sh").read_text()
        self.assertIn('"$FLOCK_BIN" -x 9', script)
        self.assertLess(
            script.index('"$FLOCK_BIN" -x 9'),
            script.index('rm -f "$MODPATH/skip_mount"'),
        )
        self.assertIn('mv -f "$tmp" "$xml"', script)
        self.assertIn('mv -f "$tmp" "$MOD_VENDOR/etc/audio_effects_config.xml"', script)
        self.assertNotIn('cat "$tmp" >"$xml"', script)
        self.assertNotIn('cat "$tmp" >"$dst"', script)

    def make_late_load_module(self, tmp: str) -> pathlib.Path:
        module = pathlib.Path(tmp)
        (module / "system/vendor/lib64/soundfx").mkdir(parents=True)
        (module / "system/etc").mkdir(parents=True)
        (module / "logs").mkdir()
        shutil.copy2(ROOT / "post-fs-data.sh", module / "post-fs-data.sh")
        mock_executable(module / "flock", "exit 0\n")
        (module / ".AIDL").touch()
        (module / "system/vendor/lib64/soundfx/lightningdsplib.so").touch()
        (module / "live_vendor_config.xml").write_text(
            f"""
<audio_effects_conf>
    <libraries>
        <library name="bundle" path="libbundleaidl.so"/>
    </libraries>
    <effects>
        <effect name="pixel_eq" library="bundle" uuid="{XML_UUID}"/>
    </effects>
</audio_effects_conf>
"""
        )
        return module

    def env_for_post_fs(self, module: pathlib.Path, linker: pathlib.Path) -> dict[str, str]:
        return {
            **os.environ,
            "KSU_LATE_LOAD": "1",
            "LDSP_LINKER_BIN": str(linker),
            "LDSP_FLOCK_BIN": str(module / "flock"),
            "LDSP_SOURCE_VENDOR_CONFIG": str(module / "live_vendor_config.xml"),
        }

    def mock_getprop(self, module: pathlib.Path, manufacturer: str, device: str, sdk: str) -> pathlib.Path:
        return mock_executable(
            module / "getprop",
            "case \"$1\" in\n"
            f"  ro.product.manufacturer) echo '{manufacturer}' ;;\n"
            f"  ro.product.device) echo '{device}' ;;\n"
            f"  ro.build.version.sdk) echo '{sdk}' ;;\n"
            "esac\n",
        )

    def run_post_fs(self, module: pathlib.Path, linker: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(module / "post-fs-data.sh")],
            env=self.env_for_post_fs(module, linker),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_post_fs_data_prepares_late_load_before_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            linker = mock_executable(module / "linker", "exit 0\n")
            result = self.run_post_fs(module, linker)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / ".late-load-reload-experimental").exists())
            self.assertFalse((module / ".late-load-no-effect").exists())
            self.assertFalse((module / "skip_mount").exists())
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertIn(LDSP_UUID, patched)
            self.assertIn(XML_UUID, patched)
            status = (module / "logs/late-load.status").read_text()
            self.assertTrue(status.startswith("READY late_load=1 boot_id="))
            self.assertIn(" vendor_config=patched_from_live_vendor lib=validated ", status)

    def test_vendor_config_with_no_pixel_anchors_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            config = module / 'live_vendor_config.xml'
            config.write_text(config.read_text().replace('libbundleaidl.so', 'libsamsung.so').replace(XML_UUID, 'vendor-uuid'))
            result = self.run_post_fs(module, mock_executable(module / 'linker', 'exit 0\n'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / 'skip_mount').exists())
            patched = (module / 'system/vendor/etc/audio_effects_config.xml').read_text()
            self.assertIn('libsamsung.so', patched)
            self.assertIn('vendor-uuid', patched)
            self.assertIn(LDSP_UUID, patched)

    def test_post_fs_data_prepares_late_load_without_pixaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            linker = mock_executable(module / "linker", "exit 0\n")
            result = self.run_post_fs(module, linker)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            status = (module / "logs/late-load.status").read_text()
            self.assertTrue(status.startswith("READY late_load=1 boot_id="))
            self.assertIn(" vendor_config=patched_from_live_vendor lib=validated ", status)

    def test_parallel_late_load_preparation_is_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            active = module / "linker-active"
            overlap = module / "linker-overlap"
            linker = module / "linker"
            linker.write_text(
                "#!/bin/sh\n"
                f"[ ! -e '{active}' ] || touch '{overlap}'\n"
                f": >'{active}'\n"
                "sleep 0.5\n"
                f"rm -f '{active}'\n"
                "exit 0\n"
            )
            linker.chmod(0o755)
            flock = module / "flock"
            flock.write_text(
                "#!/usr/bin/env python3\n"
                "import fcntl, sys\n"
                "fcntl.flock(int(sys.argv[-1]), fcntl.LOCK_EX)\n"
            )
            flock.chmod(0o755)
            env = self.env_for_post_fs(module, linker)
            scripts = [
                subprocess.Popen(
                    ["sh", str(module / "post-fs-data.sh")],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]
            results = [process.communicate(timeout=10) for process in scripts]
            for process, (stdout, stderr) in zip(scripts, results):
                self.assertEqual(process.returncode, 0, stderr or stdout)
            self.assertFalse(overlap.exists())
            self.assertFalse((module / "skip_mount").exists())
            self.assertIn(
                LDSP_UUID,
                (module / "system/vendor/etc/audio_effects_config.xml").read_text(),
            )

    def test_post_fs_data_uses_dedicated_aidl_config_without_pixel_library_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            linker = mock_executable(module / "linker", "exit 0\n")
            legacy = module / "system_audio_effects.xml"
            legacy.write_text(
                f"""
<audio_effects_conf>
    <libraries>
        <library name=\"bundle\" path=\"libbundlewrapper.so\"/>
        <library name=\"reverb\" path=\"libreverbwrapper.so\"/>
        <library name=\"visualizer\" path=\"libvisualizer.so\"/>
    </libraries>
    <effects>
        <effect name=\"equalizer\" library=\"bundle\" uuid=\"{XML_UUID}\"/>
    </effects>
</audio_effects_conf>
"""
            )
            env = self.env_for_post_fs(module, linker)
            env["LDSP_SOURCE_VENDOR_CONFIG"] = str(module / "missing_vendor_config.xml")
            env["LDSP_SOURCE_LEGACY_CONFIG"] = str(legacy)
            result = subprocess.run(
                ["sh", str(module / "post-fs-data.sh")],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertNotIn('libbundle', patched)
            self.assertNotIn('libreverb', patched)
            self.assertNotIn('libvisualizer', patched)
            self.assertIn('libbundlewrapper.so', legacy.read_text())
            self.assertNotIn('path="libaudiopreprocessing.so"', patched)
            self.assertIn(LDSP_UUID, patched)
            status = (module / "logs/late-load.status").read_text()
            self.assertTrue(status.startswith("READY late_load=1 boot_id="))
            self.assertIn(" vendor_config=dedicated_aidl_template lib=validated ", status)

    def test_post_fs_data_fails_closed_when_late_load_lib_cannot_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            linker = mock_executable(module / "linker", "exit 1\n")
            result = self.run_post_fs(module, linker)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "BLOCKED reason=linker_dependency_resolution_failed\n",
            )

    def test_native_control_candidate_checks_other_models_but_blocks_a_linker_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            (module / "native-control").mkdir()
            shutil.copy2(ROOT / "native-control/provenance.json", module / "native-control/provenance.json")
            getprop = self.mock_getprop(module, "samsung", "SM-F971U", "36")
            linker = mock_executable(module / "linker", "touch \"$LINKER_WAS_CALLED\"; exit 1\n")
            env = self.env_for_post_fs(module, linker)
            env.update({"LDSP_GETPROP_BIN": str(getprop), "LINKER_WAS_CALLED": str(module / "linker-called")})
            result = subprocess.run(["sh", str(module / "post-fs-data.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((module / "skip_mount").exists())
            self.assertTrue((module / "linker-called").exists())
            self.assertIn("linker_dependency_resolution_failed", (module / "logs/late-load.status").read_text())
            self.assertNotIn("EXPERIMENTAL WARNING", (module / "logs/late-load-linker.txt").read_text())

    def test_native_control_candidate_does_not_gate_on_malformed_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            (module / "native-control").mkdir()
            shutil.copy2(ROOT / "native-control/provenance.json", module / "native-control/provenance.json")
            getprop = self.mock_getprop(module, "samsung", "SM-F971U", "36-beta")
            linker = mock_executable(module / "linker", "exit 0\n")
            env = self.env_for_post_fs(module, linker)
            env["LDSP_GETPROP_BIN"] = str(getprop)
            result = subprocess.run(["sh", str(module / "post-fs-data.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertTrue((module / "logs/late-load.status").read_text().startswith("READY late_load=1"))

    def test_native_control_candidate_does_not_gate_on_api_below_36(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            (module / "native-control").mkdir()
            shutil.copy2(ROOT / "native-control/provenance.json", module / "native-control/provenance.json")
            getprop = self.mock_getprop(module, "samsung", "SM-F971U", "35")
            linker = mock_executable(module / "linker", "touch \"$LINKER_WAS_CALLED\"\n")
            env = self.env_for_post_fs(module, linker)
            env.update({"LDSP_GETPROP_BIN": str(getprop), "LINKER_WAS_CALLED": str(module / "linker-called")})
            result = subprocess.run(["sh", str(module / "post-fs-data.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertTrue((module / "linker-called").exists())
            self.assertIn("lib=validated", (module / "logs/late-load.status").read_text())

    def test_native_control_candidate_accepts_supported_api36(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            (module / "native-control").mkdir()
            shutil.copy2(ROOT / "native-control/provenance.json", module / "native-control/provenance.json")
            getprop = self.mock_getprop(module, "Google", "pixel", "36")
            linker = mock_executable(module / "linker", "exit 0\n")
            env = self.env_for_post_fs(module, linker)
            env["LDSP_GETPROP_BIN"] = str(getprop)
            result = subprocess.run(["sh", str(module / "post-fs-data.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertTrue((module / "logs/late-load.status").read_text().startswith("READY late_load=1"))


    def test_builtin_clears_late_load_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            shutil.copy2(ROOT / "post-fs-data.sh", module / "post-fs-data.sh")
            (module / "aml.sh").write_text("")
            (module / "patch.sh").write_text("")
            (module / "logs").mkdir()
            (module / ".late-load-no-effect").touch()
            (module / ".late-load-rootless").touch()
            (module / ".late-load-reload-experimental").touch()
            (module / "skip_mount").touch()
            result = subprocess.run(
                ["sh", str(module / "post-fs-data.sh")],
                env={**os.environ, "KSU_LATE_LOAD": "0"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / ".late-load-no-effect").exists())
            self.assertFalse((module / ".late-load-rootless").exists())
            self.assertFalse((module / ".late-load-reload-experimental").exists())
            self.assertFalse((module / "skip_mount").exists())

    def test_builtin_aidl_prepares_factory_config_without_late_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            (module / "system/vendor/lib64/soundfx").mkdir(parents=True)
            (module / "system/etc").mkdir(parents=True)
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "post-fs-data.sh", module / "post-fs-data.sh")
            (module / ".AIDL").touch()
            (module / "system/vendor/lib64/soundfx/lightningdsplib.so").touch()
            (module / "aml.sh").write_text("")
            (module / "patch.sh").write_text("")
            legacy = module / "system_audio_effects.xml"
            legacy.write_text(
                f'''<audio_effects_conf>
    <libraries>
        <library name="bundle" path="libbundlewrapper.so"/>
        <library name="pre_processing" path="libaudiopreprocessing.so"/>
    </libraries>
    <effects>
        <effect name="equalizer" library="bundle" uuid="{XML_UUID}"/>
        <effect name="aec" library="pre_processing" uuid="{PIXEL_UUID}"/>
    </effects>
</audio_effects_conf>
'''
            )
            env = {
                **os.environ,
                "LDSP_COMPAT_PROFILE": "mustang",
                "LDSP_SOURCE_VENDOR_CONFIG": str(module / "missing_vendor_config.xml"),
                "LDSP_SOURCE_LEGACY_CONFIG": str(legacy),
            }
            result = subprocess.run(
                ["sh", str(module / "post-fs-data.sh")],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertIn('path="libbundleaidl.so"', config)
            self.assertIn(LDSP_UUID, config)
            self.assertNotIn("libaudiopreprocessing.so", config)
            self.assertEqual(
                (module / "logs/builtin-aidl-config.status").read_text(),
                "READY mode=builtin source=system_legacy "
                f"config={module}/system/vendor/etc/audio_effects_config.xml "
                "systemless=1 reload=not_requested\n",
            )
            self.assertFalse((module / ".late-load-reload-experimental").exists())
            self.assertFalse((module / "skip_mount").exists())

    def test_legacy_late_load_entry_point_delegates_to_pre_mount_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            shutil.copy2(ROOT / "late-load.sh", module / "late-load.sh")
            linker = mock_executable(module / "linker", "exit 0\n")
            result = subprocess.run(
                ["sh", str(module / "late-load.sh")],
                env=self.env_for_post_fs(module, linker),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            status = (module / "logs/late-load.status").read_text()
            self.assertTrue(status.startswith("READY late_load=1 boot_id="))
            self.assertIn(" vendor_config=patched_from_live_vendor lib=validated ", status)

    def test_late_load_service_schedules_one_delayed_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "service.sh", module / "service.sh")
            mocks = module / "bin"
            mocks.mkdir()
            mock_executable(mocks / "sleep", "echo \"$*\" >>\"$SLEEP_LOG\"\nexit 0\n")
            recovery_calls = module / "logs/recovery.calls"
            (module / "audio-hal-recovery.sh").write_text(
                f'#!/system/bin/sh\necho "$*" >>"{recovery_calls}"\n'
            )
            (module / "audio-hal-recovery.sh").chmod(0o755)
            (module / "lightningdsp_app.sh").write_text("#!/system/bin/sh\nexit 0\n")
            result = subprocess.run(
                ["sh", str(module / "service.sh")],
                env={**os.environ, "KSU_LATE_LOAD": "1", "LDSP_SLEEP_BIN": str(mocks / "sleep"), "SLEEP_LOG": str(module / "logs/sleep.calls")},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            # The scheduler is intentionally detached. Wait for its completed
            # write, not merely file creation, with a bounded monotonic deadline.
            # A one-second fork-based poll flakes on a loaded macOS host.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if recovery_calls.read_text() == "--auto-once\n":
                        break
                except FileNotFoundError:
                    pass
                time.sleep(0.02)
            self.assertEqual(recovery_calls.read_text(), "--auto-once\n")
            self.assertEqual((module / "logs/sleep.calls").read_text(), "10\n")
            self.assertEqual(
                (module / "logs/service.status").read_text(),
                "SCHEDULED reason=late_load_recovery delay_seconds=10 restart=one_shot processing=unverified\n",
            )

    def test_experimental_marker_without_late_load_does_not_restart_hal(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "service.sh", module / "service.sh")
            (module / ".late-load-reload-experimental").touch()
            (module / "lightningdsp_app.sh").write_text(
                '#!/system/bin/sh\n[ -z "$MODPATH" ] && MODPATH="${0%/*}"\necho app >>"$MODPATH/logs/app-helper.calls"\n'
            )
            result = subprocess.run(
                ["sh", str(module / "service.sh")],
                env={**os.environ, "KSU_LATE_LOAD": "0"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = module / "logs/app-helper.calls"
            for _ in range(20):
                if calls.exists():
                    break
                subprocess.run(["sleep", "0.05"], check=False)
            self.assertTrue(calls.exists())
            self.assertEqual(calls.read_text(), "app\n")
            self.assertEqual(
                (module / "logs/service.status").read_text(),
                "SKIPPED reason=not_kernel_su_late_load restart=not_requested processing=unverified\n",
            )

    def run_lightningdsp_app(
        self,
        module: pathlib.Path,
        mocks: pathlib.Path,
        pm_body: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        temp_apk = module / "tmp-install.apk"
        mock_executable(mocks / "getprop", "echo 1\n")
        mock_executable(mocks / "chcon", "exit 0\n")
        pm = mock_executable(mocks / "pm", pm_body)
        cmd = mock_executable(
            mocks / "cmd",
            '''case "$1" in
  package) shift; exec "$MOCK_PACKAGE_MANAGER" "$@" ;;
  notification) echo "$@" >>"$MOCK_NOTIFICATION_LOG"; exit 0 ;;
esac
exit 1
''',
        )
        mock_executable(mocks / "timeout", 'shift; exec "$@"\n')
        return subprocess.run(
            ["sh", str(module / "lightningdsp_app.sh")],
            env={
                **os.environ,
                "PATH": f"{mocks}:{os.environ['PATH']}",
                "LDSP_TEMP_INSTALL_PATH": str(temp_apk),
                "LDSP_FLASH_INSTALL": "1",
                "LDSP_DATA_ROOT": str(module.parent / "data"),
                "LDSP_DATA_BACKUP_DIR": str(module / ".ldsp-appdata-migration"),
                "MOCK_PM_LOG": str(module.parent / "pm.log"),
                "MOCK_INSTALLED_APK_PATH": "",
                "MOCK_INSTALLED_VERSION_CODE": "",
                "LDSP_SDCARD_PATH": str(module.parent / "sdcard"),
                "LDSP_CMD_BIN": str(cmd),
                "MOCK_PACKAGE_MANAGER": str(pm),
                "MOCK_NOTIFICATION_LOG": str(module.parent / "notifications.log"),
                "LDSP_RESTORECON_BIN": str(mock_executable(mocks / "restorecon", 'echo "$@" >>"$MOCK_RESTORECON_LOG"; exit 0\n')),
                "LDSP_CHOWN_BIN": str(mock_executable(mocks / "chown", 'echo "$@" >>"$MOCK_CHOWN_LOG"; exit 0\n')),
                "MOCK_RESTORECON_LOG": str(module.parent / "restorecon.log"),
                "MOCK_CHOWN_LOG": str(module.parent / "chown.log"),
                **(extra_env or {}),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    def make_lightningdsp_package_manager(self, root: pathlib.Path, mode: str) -> str:
        state = root / "package-installed"
        state.write_text("installed\n")
        pm_log = root / "pm.log"
        return f'''state="{state}"
echo "$@" >>"{pm_log}"
case "$1 $2 $3" in
  "list packages -U") [ "$(cat "$state")" = installed ] && echo 'package:com.lightning.dsp uid:10042'; exit 0 ;;
esac
case "$1 $2" in
  "list packages")
    [ "$(cat "$state")" = installed ] && echo package:com.lightning.dsp
    exit 0
    ;;
  "list users") echo 'UserInfo{{0:Owner:13}}'; exit 0 ;;
  "dump com.lightning.dsp") [ -n "$MOCK_INSTALLED_VERSION_CODE" ] && echo "versionCode=$MOCK_INSTALLED_VERSION_CODE minSdk=26"; exit 0 ;;
  "path com.lightning.dsp")
    [ "$(cat "$state")" = installed ] && [ -n "$MOCK_INSTALLED_APK_PATH" ] && echo "package:$MOCK_INSTALLED_APK_PATH"
    exit 0
    ;;
  "install --user")
    if [ "{mode}" = mismatch ] && [ "$(cat "$state")" = installed ]; then
      echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]'
      exit 1
    fi
    echo installed >"$state"
    echo Success
    exit 0
    ;;
  "uninstall com.lightning.dsp") echo removed >"$state"; echo Success; exit 0 ;;
esac
exit 0
'''

    def setup_lightningdsp_app_test(self, root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
        module = root / "module"
        mocks = root / "mocks"
        module.mkdir()
        mocks.mkdir()
        (module / "logs").mkdir()
        shutil.copy2(ROOT / "lightningdsp_app.sh", module / "lightningdsp_app.sh")
        (module / "LightningDSP.apk").write_text("new apk")
        return module, mocks

    def run_signature_mismatch_case(self, choice: str) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, pathlib.Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        module, mocks = self.setup_lightningdsp_app_test(root)
        pm_body = self.make_lightningdsp_package_manager(root, "mismatch")
        getevent = mock_executable(mocks / "getevent", f'''case "{choice}" in
  up) echo '[ 1.0] KEY_VOLUMEUP DOWN'; exit 0 ;;
  down) echo '[ 1.0] KEY_VOLUMEDOWN DOWN'; exit 0 ;;
  *) exit 1 ;;
esac
''')
        result = self.run_lightningdsp_app(
            module,
            mocks,
            pm_body,
            {
                "LDSP_GETEVENT_BIN": str(getevent),
            },
        )
        return result, root, module

    def test_lightningdsp_app_updates_existing_package_in_place_when_signature_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_lightningdsp_app_test(root)
            pm_body = self.make_lightningdsp_package_manager(root, "same")
            result = self.run_lightningdsp_app(module, mocks, pm_body)
            self.assertEqual(result.returncode, 0, result.stderr)
            log = (module / "logs/lightningdsp_app_install.log").read_text()
            self.assertIn("Install result (User 0): Success", log)
            commands = (root / "pm.log").read_text()
            self.assertIn("install --user 0 -r -g", commands)
            self.assertNotIn("uninstall", commands)

    def test_lightningdsp_app_volume_down_confirms_signer_migration_and_restores_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_lightningdsp_app_test(root)
            data = root / "data/user/0/com.lightning.dsp"
            data.mkdir(parents=True)
            (data / "settings.xml").write_text("eq=custom")
            getevent = mock_executable(mocks / "getevent", "echo '[ 1.0] KEY_VOLUMEDOWN DOWN'; exit 0\n")
            result = self.run_lightningdsp_app(
                module, mocks, self.make_lightningdsp_package_manager(root, "mismatch"),
                {"LDSP_GETEVENT_BIN": str(getevent), "LDSP_KEY_TIMEOUT_SECONDS": "1"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = (root / "pm.log").read_text()
            self.assertIn("uninstall com.lightning.dsp", commands)
            self.assertIn("install --user 0 -r -g", commands)
            self.assertEqual((data / "settings.xml").read_text(), "eq=custom")
            self.assertIn("App data restored", result.stdout)
            self.assertFalse((module / ".ldsp-appdata-migration").exists())
            self.assertIn("10042:10042", (root / "chown.log").read_text())
            self.assertIn("-RF", (root / "restorecon.log").read_text())

    def test_lightningdsp_app_volume_up_or_timeout_keeps_different_signature_app(self):
        for choice in ("up", "none"):
            with self.subTest(choice=choice), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                module, mocks = self.setup_lightningdsp_app_test(root)
                event = "KEY_VOLUMEUP DOWN" if choice == "up" else ""
                getevent = mock_executable(mocks / "getevent", f"echo '[ 1.0] {event}'; exit 0\n")
                result = self.run_lightningdsp_app(
                    module, mocks, self.make_lightningdsp_package_manager(root, "mismatch"),
                    {"LDSP_GETEVENT_BIN": str(getevent), "LDSP_KEY_TIMEOUT_SECONDS": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("uninstall", (root / "pm.log").read_text())
                self.assertIn("Replacement declined or timed out", (module / "logs/lightningdsp_app_install.log").read_text())

    def test_lightningdsp_app_continues_after_failed_backup_only_after_volume_down_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_lightningdsp_app_test(root)
            backup = module / ".ldsp-appdata-migration"
            backup.mkdir()
            (backup / "restore-pending").touch()
            getevent = mock_executable(mocks / "getevent", "echo '[ 1.0] KEY_VOLUMEDOWN DOWN'; exit 0\n")
            result = self.run_lightningdsp_app(
                module, mocks, self.make_lightningdsp_package_manager(root, "mismatch"),
                {"LDSP_GETEVENT_BIN": str(getevent), "LDSP_KEY_TIMEOUT_SECONDS": "1"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("uninstall com.lightning.dsp", (root / "pm.log").read_text())
            self.assertIn("backup failed; continuing as confirmed", result.stdout)

    def test_lightningdsp_app_skips_reinstall_when_installed_apk_already_matches_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_lightningdsp_app_test(root)
            installed_apk = root / "installed.apk"
            shutil.copy2(module / "LightningDSP.apk", installed_apk)
            pm_body = self.make_lightningdsp_package_manager(root, "same")
            result = self.run_lightningdsp_app(
                module,
                mocks,
                pm_body,
                {"MOCK_INSTALLED_APK_PATH": str(installed_apk), "LDSP_FLASH_INSTALL": "0"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("install --user", (root / "pm.log").read_text())
            self.assertIn("App already installed; boot service will not prompt", (module / "logs/lightningdsp_app_install.log").read_text())

    def test_lightningdsp_app_skips_equal_or_newer_version_written_by_module_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_lightningdsp_app_test(root)
            (module / ".lightningdsp_apk_target_version_code").write_text("56\n")
            pm_body = self.make_lightningdsp_package_manager(root, "same")
            result = self.run_lightningdsp_app(
                module,
                mocks,
                pm_body,
                {"MOCK_INSTALLED_VERSION_CODE": "56", "LDSP_FLASH_INSTALL": "0"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("install --user", (root / "pm.log").read_text())
            self.assertIn("App already installed; boot service will not prompt", (module / "logs/lightningdsp_app_install.log").read_text())

    def test_lightningdsp_app_installer_installs_when_only_lookalike_package_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = root / "module"
            mocks = root / "mocks"
            module.mkdir()
            mocks.mkdir()
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "lightningdsp_app.sh", module / "lightningdsp_app.sh")
            (module / "LightningDSP.apk").write_text("apk")
            pm_log = root / "pm.log"
            pm_body = f'''case "$1 $2" in
  "list packages") echo package:jamesXdsp; exit 0 ;;
  "list users") echo 'UserInfo{{0:Owner:13}}'; exit 0 ;;
esac
echo "$@" >>"{pm_log}"
exit 0
'''
            result = self.run_lightningdsp_app(module, mocks, pm_body, {"LDSP_FLASH_INSTALL": "0"})
            self.assertEqual(result.returncode, 0, result.stderr)
            log = pm_log.read_text()
            self.assertIn("install --user 0 -r -g", log)

    def test_lightningdsp_flash_migrates_legacy_package_before_installing_new_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_lightningdsp_app_test(root)
            legacy_state = root / "legacy-installed"
            legacy_state.touch()
            pm_log = root / "pm.log"
            pm_body = f'''echo "$@" >>"{pm_log}"
case "$1 $2" in
  "list packages") [ -e "{legacy_state}" ] && echo package:james.dsp; exit 0 ;;
  "list users") echo 'UserInfo{{0:Owner:13}}'; exit 0 ;;
  "uninstall --user") [ "$3" = 0 ] && [ "$4" = james.dsp ] && rm -f "{legacy_state}"; echo Success; exit 0 ;;
  "install --user") [ "$3" = 0 ] && [ "$4" = -r ] && echo Success; exit 0 ;;
esac
exit 1
'''
            result = self.run_lightningdsp_app(module, mocks, pm_body)
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = pm_log.read_text().splitlines()
            uninstall_index = next(i for i, line in enumerate(commands) if "uninstall --user 0 james.dsp" in line)
            install_index = next(i for i, line in enumerate(commands) if "install --user 0 -r -g" in line)
            self.assertLess(uninstall_index, install_index)
            self.assertFalse(legacy_state.exists())
            self.assertIn("private app data will be removed", result.stdout)

    def test_rebrand_disables_and_removes_verified_old_module(self):
        installer = (ROOT / "common/install.sh").read_text()
        self.assertIn('id=ainur_lightningdsp', (ROOT / "module.prop").read_text())
        self.assertIn('Inspired by JamesDSP', installer)
        self.assertIn('modules/ainur_jamesdsp', installer)
        self.assertIn('modules_update/ainur_jamesdsp', installer)
        self.assertIn('touch "$LEGACY_MODULE/disable"', installer)
        self.assertIn('grep -Fqx \'id=ainur_jamesdsp\' "$LEGACY_MODULE/module.prop"', installer)
        self.assertIn('rm -rf "$LEGACY_MODULE"', installer)
        self.assertIn('Removed previous ainur_jamesdsp module.', installer)
        self.assertNotIn('not deleted', installer)

        readme = (ROOT / "README.md").read_text()
        self.assertIn('disabled, and removed', readme)
        self.assertIn('then removes its directory', readme)

    def test_late_load_reload_script_has_no_restart_loop_or_killall(self):
        combined = (ROOT / "audio-reload.sh").read_text()
        self.assertNotIn("killall", combined)
        self.assertNotIn("while true", combined)
        self.assertIn('ctl.restart "$INIT_SERVICE"', combined)
        self.assertIn("reload_already_attempted_for_hal_instance", combined)
        self.assertIn('service_found "$AML_FACTORY"', combined)
        self.assertIn("pixaml_state=not_active", combined)
        self.assertIn("pixaml_factory_lost_after_audio_restart", combined)
        self.assertIn("audioserver_pid_missing_after_restart", combined)

    @unittest.skip("Historical pixel AIDL package builder is not used by the LightningDSP rebrand packager.")
    def test_previous_pixel_builder_refuses_new_root_app_before_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "old-candidate.zip"
            env = {**os.environ, "LDSP_PACKAGE_OUTPUT": str(zip_path)}
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_6510_pixel_aidl.py")],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unexpected APK payload", result.stderr)
            self.assertFalse(zip_path.exists())

    def test_installer_uses_only_thepbone_and_package_manager_signature_decision(self):
        app_helper = (ROOT / "lightningdsp_app.sh").read_text()
        installer = (ROOT / "common/install.sh").read_text()
        self.assertIn("install --user", app_helper)
        self.assertIn("INSTALL_FAILED_UPDATE_INCOMPATIBLE", app_helper)
        self.assertIn("Volume DOWN: uninstall", app_helper)
        self.assertIn("no response in 10 seconds also keeps it", app_helper)
        self.assertIn("backup_app_data", app_helper)
        self.assertIn('mv -f "$MODPATH/common/files/LightningDSP.apk"', installer)
        self.assertNotIn("Which UI you want to install?", installer)
        self.assertNotIn("common/app_migration.sh", installer)
        self.assertIn('LDSP_FLASH_INSTALL=1 LDSP_PM_CMD="$APP_PM"', installer)
        self.assertNotIn("pm uninstall", installer)


if __name__ == "__main__":
    unittest.main()
