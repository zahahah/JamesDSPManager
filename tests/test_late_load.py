import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
JDSP_UUID = "f27317f4-c984-4de6-9a90-545759495bf2"
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
        self.assertIn('mv -f "$tmp" "$dst"', script)
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
        (module / "system/vendor/lib64/soundfx/libjamesdsp.so").touch()
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
            "JDSP_LINKER_BIN": str(linker),
            "JDSP_FLOCK_BIN": str(module / "flock"),
            "JDSP_SOURCE_VENDOR_CONFIG": str(module / "live_vendor_config.xml"),
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
            self.assertIn(JDSP_UUID, patched)
            self.assertIn(XML_UUID, patched)
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "READY late_load=1 vendor_config=patched_from_live_vendor lib=validated restart=not_requested processing=unverified\n",
            )

    def test_post_fs_data_prepares_late_load_without_pixaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.make_late_load_module(tmp)
            linker = mock_executable(module / "linker", "exit 0\n")
            result = self.run_post_fs(module, linker)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "READY late_load=1 vendor_config=patched_from_live_vendor lib=validated restart=not_requested processing=unverified\n",
            )

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
                JDSP_UUID,
                (module / "system/vendor/etc/audio_effects_config.xml").read_text(),
            )

    def test_post_fs_data_generates_aidl_config_from_system_legacy_when_vendor_config_absent(self):
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
            env["JDSP_SOURCE_VENDOR_CONFIG"] = str(module / "missing_vendor_config.xml")
            env["JDSP_SOURCE_LEGACY_CONFIG"] = str(legacy)
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
            self.assertIn('path="libbundleaidl.so"', patched)
            self.assertIn('path="libreverbaidl.so"', patched)
            self.assertIn('path="libvisualizeraidl.so"', patched)
            self.assertNotIn('path="libaudiopreprocessing.so"', patched)
            self.assertIn(JDSP_UUID, patched)
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "READY late_load=1 vendor_config=generated_from_system_legacy lib=validated restart=not_requested processing=unverified\n",
            )

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
            env.update({"JDSP_GETPROP_BIN": str(getprop), "LINKER_WAS_CALLED": str(module / "linker-called")})
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
            env["JDSP_GETPROP_BIN"] = str(getprop)
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
            env.update({"JDSP_GETPROP_BIN": str(getprop), "LINKER_WAS_CALLED": str(module / "linker-called")})
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
            env["JDSP_GETPROP_BIN"] = str(getprop)
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
            (module / "system/vendor/lib64/soundfx/libjamesdsp.so").touch()
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
                "JDSP_COMPAT_PROFILE": "mustang",
                "JDSP_SOURCE_VENDOR_CONFIG": str(module / "missing_vendor_config.xml"),
                "JDSP_SOURCE_LEGACY_CONFIG": str(legacy),
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
            self.assertIn(JDSP_UUID, config)
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
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "READY late_load=1 vendor_config=patched_from_live_vendor lib=validated restart=not_requested processing=unverified\n",
            )

    def test_late_load_service_never_restarts_audio_or_runs_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "service.sh", module / "service.sh")
            (module / ".late-load-reload-experimental").touch()
            reload_calls = module / "logs/audio-reload.calls"
            (module / "audio-reload.sh").write_text(
                f'#!/system/bin/sh\necho called >>"{reload_calls}"\n'
            )
            (module / "jdsp_app.sh").write_text("#!/system/bin/sh\nexit 0\n")
            result = subprocess.run(
                ["sh", str(module / "service.sh")],
                env={**os.environ, "KSU_LATE_LOAD": "1"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(reload_calls.exists())
            self.assertEqual(
                (module / "logs/service.status").read_text(),
                "SKIPPED reason=automatic_audio_restart_disabled restart=not_requested processing=unverified\n",
            )

    def test_late_load_service_starts_app_helper_and_reports_restart_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "service.sh", module / "service.sh")
            (module / ".late-load-reload-experimental").touch()
            (module / "jdsp_app.sh").write_text(
                '#!/system/bin/sh\n[ -z "$MODPATH" ] && MODPATH="${0%/*}"\necho app >>"$MODPATH/logs/app-helper.calls"\n'
            )
            result = subprocess.run(
                ["sh", str(module / "service.sh")],
                env={**os.environ, "KSU_LATE_LOAD": "1"},
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
                "SKIPPED reason=automatic_audio_restart_disabled restart=not_requested processing=unverified\n",
            )

    def run_jdsp_app(
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
            ["sh", str(module / "jdsp_app.sh")],
            env={
                **os.environ,
                "PATH": f"{mocks}:{os.environ['PATH']}",
                "JDSP_TEMP_INSTALL_PATH": str(temp_apk),
                "MOCK_PM_LOG": str(module.parent / "pm.log"),
                "MOCK_INSTALLED_APK_PATH": "",
                "MOCK_INSTALLED_VERSION_CODE": "",
                "JDSP_SDCARD_PATH": str(module.parent / "sdcard"),
                "JDSP_CMD_BIN": str(cmd),
                "MOCK_PACKAGE_MANAGER": str(pm),
                "MOCK_NOTIFICATION_LOG": str(module.parent / "notifications.log"),
                **(extra_env or {}),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    def make_jdsp_package_manager(self, root: pathlib.Path, mode: str) -> str:
        state = root / "package-installed"
        state.write_text("installed\n")
        pm_log = root / "pm.log"
        return f'''state="{state}"
echo "$@" >>"{pm_log}"
case "$1 $2" in
  "list packages")
    [ "$(cat "$state")" = installed ] && echo package:james.dsp
    exit 0
    ;;
  "list users") echo 'UserInfo{{0:Owner:13}}'; exit 0 ;;
  "dump james.dsp") [ -n "$MOCK_INSTALLED_VERSION_CODE" ] && echo "versionCode=$MOCK_INSTALLED_VERSION_CODE minSdk=26"; exit 0 ;;
  "path james.dsp")
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
  "uninstall --user") echo removed >"$state"; echo Success; exit 0 ;;
esac
exit 0
'''

    def setup_jdsp_app_test(self, root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
        module = root / "module"
        mocks = root / "mocks"
        module.mkdir()
        mocks.mkdir()
        (module / "logs").mkdir()
        shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
        (module / "JamesDSPManager.apk").write_text("new apk")
        return module, mocks

    def run_install_time_migration(
        self,
        root: pathlib.Path,
        installed_version: int,
        installed_certificate: str,
        candidate_version: int,
        choice: str = "none",
        install_mode: str = "success",
    ) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, pathlib.Path]:
        module, mocks = self.setup_jdsp_app_test(root)
        apk = module / "JamesDSPManager.apk"
        metadata = module / "JamesDSPManager.apk.meta"
        metadata.write_text(f"versionCode={candidate_version}\n")
        state = root / "package-installed"
        state.write_text("installed\n")
        pm_log = root / "pm.log"
        pm = mock_executable(
            mocks / "pm",
            f'''state="{state}"
echo "$@" >>"{pm_log}"
case "$1 $2" in
  "list packages") [ "$(cat "$state")" = installed ] && echo package:james.dsp; exit 0 ;;
  "list users") echo 'UserInfo{{0:Owner:13}}'; exit 0 ;;
  "dump james.dsp") echo 'versionCode={installed_version} minSdk=26'; echo 'signatures:[{installed_certificate}]'; exit 0 ;;
  "path james.dsp") echo "package:$MOCK_INSTALLED_APK_PATH"; exit 0 ;;
  "install --user")
    if [ "{install_mode}" = mismatch ] && [ "$(cat "$state")" = installed ]; then
      echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]'; exit 1
    fi
    echo installed >"$state"; echo Success; exit 0 ;;
  "uninstall --user") echo removed >"$state"; echo Success; exit 0 ;;
esac
exit 0
''',
        )
        cmd = mock_executable(mocks / "cmd", 'shift; exec "$MOCK_PM" "$@"\n')
        installed_apk = root / "installed.apk"
        installed_apk.write_text("installed package apk")
        getevent = mock_executable(
            mocks / "getevent",
            {
                "up": "echo '[ 1.0] KEY_VOLUMEUP DOWN'; exit 0\n",
                "down": "echo '[ 1.0] KEY_VOLUMEDOWN DOWN'; exit 0\n",
            }.get(choice, "exit 1\n"),
        )
        mock_executable(mocks / "timeout", 'shift; exec "$@"\n')
        script = ROOT / "common/app_migration.sh"
        result = subprocess.run(
            [
                "sh",
                "-c",
                '. "$JDSP_MIGRATION_SCRIPT"; jdsp_apk_certificate_sha256() { [ "$1" = "$JDSP_APK" ] && echo "$MOCK_NEW_CERT_SHA256" || echo "$MOCK_OLD_CERT_SHA256"; }; jdsp_install_selected_apk "$JDSP_APK" "$JDSP_META" "$JDSP_MODPATH"',
            ],
            env={
                **os.environ,
                "PATH": f"{mocks}:{os.environ['PATH']}",
                "JDSP_MIGRATION_SCRIPT": str(script),
                "JDSP_APK": str(apk),
                "JDSP_META": str(metadata),
                "JDSP_MODPATH": str(module),
                "JDSP_MIGRATION_CMD": str(cmd),
                "JDSP_MIGRATION_GETEVENT": str(getevent),
                "JDSP_MIGRATION_TEMP": str(root / "install.apk"),
                "JDSP_MIGRATION_SDCARD": str(root / "sdcard"),
                "MOCK_INSTALLED_APK_PATH": str(installed_apk),
                "MOCK_NEW_CERT_SHA256": "a" * 64,
                "MOCK_OLD_CERT_SHA256": "a" * 64 if installed_certificate == "same" else "b" * 64,
                "MOCK_PM": str(pm),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return result, root, module

    def run_signature_mismatch_case(self, choice: str) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, pathlib.Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        module, mocks = self.setup_jdsp_app_test(root)
        pm_body = self.make_jdsp_package_manager(root, "mismatch")
        getevent = mock_executable(mocks / "getevent", f'''case "{choice}" in
  up) echo '[ 1.0] KEY_VOLUMEUP DOWN'; exit 0 ;;
  down) echo '[ 1.0] KEY_VOLUMEDOWN DOWN'; exit 0 ;;
  *) exit 1 ;;
esac
''')
        result = self.run_jdsp_app(
            module,
            mocks,
            pm_body,
            {
                "JDSP_GETEVENT_BIN": str(getevent),
            },
        )
        return result, root, module

    def test_jdsp_app_updates_existing_package_in_place_when_signature_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_jdsp_app_test(root)
            pm_body = self.make_jdsp_package_manager(root, "same")
            result = self.run_jdsp_app(module, mocks, pm_body)
            self.assertEqual(result.returncode, 0, result.stderr)
            log = (module / "logs/jamesdsp_app_install.log").read_text()
            self.assertIn("Install result (User 0): Success", log)
            commands = (root / "pm.log").read_text()
            self.assertIn("install --user 0 -r -g", commands)
            self.assertNotIn("uninstall", commands)

    def test_install_time_updates_matching_signature_only_when_candidate_is_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            result, root, module = self.run_install_time_migration(root, 51, "same", 56)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("versionCode 56 is newer than 51", result.stdout)
            self.assertIn("install --user 0 -r -g", (root / "pm.log").read_text())
            self.assertEqual((module / ".jdsp_apk_target_version_code").read_text().strip(), "56")

    def test_install_time_skips_matching_signature_when_candidate_is_equal_or_older(self):
        for installed, candidate in ((56, 56), (100, 95)):
            with self.subTest(installed=installed, candidate=candidate), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                result, root, _module = self.run_install_time_migration(
                    root, installed, "same", candidate
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("is not newer. Keeping the installed app", result.stdout)
                self.assertNotIn("install --user", (root / "pm.log").read_text())

    def test_install_time_signature_mismatch_prompts_and_defaults_to_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            result, root, _module = self.run_install_time_migration(
                root, 56, "different", 56, choice="none"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Analysing installed and selected JamesDSP signing certificates", result.stdout)
            output_lines = result.stdout.splitlines()
            analysis_index = output_lines.index(
                "Analysing installed and selected JamesDSP signing certificates"
            )
            self.assertEqual(output_lines[analysis_index - 1], " ")
            self.assertEqual(output_lines[analysis_index + 1], " ")
            self.assertLess(
                analysis_index,
                output_lines.index(
                    "Installed and selected JamesDSP APKs have different signing certificates."
                ),
            )
            self.assertIn("Different JamesDSP signing certificates", result.stdout)
            self.assertIn("No volume-key response. Keeping the installed app by default", result.stdout)
            self.assertNotIn("uninstall --user", (root / "pm.log").read_text())
            self.assertTrue((root / "sdcard/Download/JamesDSPManager.apk").is_file())

    def test_install_time_volume_up_confirms_different_signature_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            result, root, _module = self.run_install_time_migration(
                root, 56, "different", 56, choice="up"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = (root / "pm.log").read_text()
            self.assertIn("uninstall --user 0 james.dsp", commands)
            self.assertIn("install --user 0 -r -g", commands)
            self.assertFalse((root / "sdcard/Download/JamesDSPManager.apk").exists())

    def test_jdsp_app_skips_reinstall_when_installed_apk_already_matches_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_jdsp_app_test(root)
            installed_apk = root / "installed.apk"
            shutil.copy2(module / "JamesDSPManager.apk", installed_apk)
            pm_body = self.make_jdsp_package_manager(root, "same")
            result = self.run_jdsp_app(
                module,
                mocks,
                pm_body,
                {"MOCK_INSTALLED_APK_PATH": str(installed_apk)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("install --user", (root / "pm.log").read_text())
            self.assertIn("already matches the module payload", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_skips_equal_or_newer_version_written_by_module_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = self.setup_jdsp_app_test(root)
            (module / ".jdsp_apk_target_version_code").write_text("56\n")
            pm_body = self.make_jdsp_package_manager(root, "same")
            result = self.run_jdsp_app(
                module,
                mocks,
                pm_body,
                {"MOCK_INSTALLED_VERSION_CODE": "56"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("install --user", (root / "pm.log").read_text())
            self.assertIn("equal to or newer", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_keeps_existing_app_and_copies_apk_when_user_declines(self):
        result, root, module = self.run_signature_mismatch_case("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = (root / "pm.log").read_text()
        self.assertNotIn("uninstall", commands)
        self.assertEqual((root / "sdcard/Download/JamesDSPManager.apk").read_text(), "new apk")
        self.assertTrue((module / ".jdsp_apk_signature_declined").exists())
        self.assertIn("Volume Down selected", (module / "logs/jamesdsp_app_install.log").read_text())
        self.assertIn("notification post", (root / "notifications.log").read_text())

    def test_jdsp_app_defaults_to_keep_and_copy_when_no_volume_key_is_pressed(self):
        result, root, module = self.run_signature_mismatch_case("none")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("uninstall", (root / "pm.log").read_text())
        self.assertEqual((root / "sdcard/Download/JamesDSPManager.apk").read_text(), "new apk")
        self.assertIn("No volume-key response", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_replaces_different_signature_only_after_volume_up(self):
        result, root, module = self.run_signature_mismatch_case("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = (root / "pm.log").read_text()
        self.assertIn("uninstall --user 0 james.dsp", commands)
        self.assertGreaterEqual(commands.count("install --user 0 -r -g"), 2)
        self.assertIn("Install after approved removal (User 0): Success", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_does_not_reprompt_for_the_same_declined_apk_on_next_boot(self):
        result, root, module = self.run_signature_mismatch_case("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        notifications_before = (root / "notifications.log").read_text()
        mocks = root / "mocks"
        getevent = mock_executable(mocks / "getevent", 'echo "unexpected prompt" >>"$MOCK_GETEVENT_LOG"; exit 1\n')
        pm_body = self.make_jdsp_package_manager(root, "mismatch")
        result = self.run_jdsp_app(
            module,
            mocks,
            pm_body,
            {
                "JDSP_GETEVENT_BIN": str(getevent),
                "MOCK_GETEVENT_LOG": str(root / "getevent.log"),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((root / "getevent.log").exists())
        self.assertEqual((root / "notifications.log").read_text(), notifications_before)
        self.assertIn("without prompting again", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_installer_installs_when_only_lookalike_package_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = root / "module"
            mocks = root / "mocks"
            module.mkdir()
            mocks.mkdir()
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            pm_log = root / "pm.log"
            pm_body = f'''case "$1 $2" in
  "list packages") echo package:jamesXdsp; exit 0 ;;
  "list users") echo 'UserInfo{{0:Owner:13}}'; exit 0 ;;
esac
echo "$@" >>"{pm_log}"
exit 0
'''
            result = self.run_jdsp_app(module, mocks, pm_body)
            self.assertEqual(result.returncode, 0, result.stderr)
            log = pm_log.read_text()
            self.assertIn("install --user 0 -r -g", log)
            self.assertIn("disable --user 0 james.dsp", log)
            self.assertIn("enable --user 0 james.dsp", log)

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

    def test_previous_pixel_builder_refuses_new_root_app_before_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "old-candidate.zip"
            env = {**os.environ, "JDSP_PACKAGE_OUTPUT": str(zip_path)}
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

    def test_installer_does_not_remove_an_existing_app(self):
        app_helper = (ROOT / "jdsp_app.sh").read_text()
        installer = (ROOT / "common/install.sh").read_text()
        self.assertIn("install --user", app_helper)
        self.assertIn("INSTALL_FAILED_UPDATE_INCOMPATIBLE", app_helper)
        self.assertIn("Volume Up selected", app_helper)
        self.assertIn("No volume-key response; keeping the existing app by default", app_helper)
        self.assertIn("copy_apk_to_sdcard", app_helper)
        self.assertIn("jdsp_install_selected_apk", (ROOT / "common/app_migration.sh").read_text())
        self.assertIn(". \"$MODPATH/common/app_migration.sh\"", installer)
        self.assertIn("jdsp_install_selected_apk", installer)
        self.assertNotIn("pm uninstall", installer)


if __name__ == "__main__":
    unittest.main()
