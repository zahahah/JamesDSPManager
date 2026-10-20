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
        self.assertIn("jdsp_lock_fd9 || late_block late_load_lock_failed", script)
        self.assertLess(
            script.index("jdsp_lock_fd9 || late_block late_load_lock_failed"),
            script.index('rm -f "$MODPATH/skip_mount"'),
        )
        self.assertIn('mv -f "$xml_tmp" "$xml"', script)
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
            "JDSP_COMPAT_PROFILE": "mustang",
            "JDSP_LINKER_BIN": str(linker),
            "JDSP_FLOCK_BIN": str(module / "flock"),
            "JDSP_SOURCE_VENDOR_CONFIG": str(module / "live_vendor_config.xml"),
            "JDSP_COMPAT_PROFILE": "mustang",
        }

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
            self.assertTrue((module / ".late-load-reload-experimental").exists())
            self.assertFalse((module / ".late-load-no-effect").exists())
            self.assertFalse((module / "skip_mount").exists())
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertIn(JDSP_UUID, patched)
            self.assertIn(XML_UUID, patched)
            self.assertEqual(
                (module / "logs/late-load.status").read_text(),
                "READY late_load=1 vendor_config=patched_from_live_vendor lib=patched restart=service\n",
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
                "READY late_load=1 vendor_config=patched_from_live_vendor lib=patched restart=service\n",
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
                "READY late_load=1 vendor_config=generated_from_system_legacy lib=patched restart=service\n",
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
                "READY late_load=1 vendor_config=patched_from_live_vendor lib=patched restart=service\n",
            )

    def test_late_load_service_restarts_default_factory_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = root / "module"
            logs = module / "logs"
            mocks = root / "mocks"
            proc = root / "proc"
            module.mkdir()
            logs.mkdir()
            mocks.mkdir()
            (proc / "100").mkdir(parents=True)
            (proc / "300").mkdir(parents=True)
            (proc / "500").mkdir(parents=True)
            shutil.copy2(ROOT / "audio-reload.sh", module / "audio-reload.sh")
            (module / ".late-load-reload-experimental").touch()
            xml = root / "audio_effects_config.xml"
            xml.write_text(
                f'<library name="bundle" path="libbundleaidl.so"/>\n'
                f'<effect name="pixel_eq" uuid="{XML_UUID}"/>\n'
                f'<effect name="jamesdsp" uuid="{JDSP_UUID}"/>\n'
            )
            lib = root / "libjamesdsp.so"
            lib.touch()
            boot_id = root / "boot_id"
            boot_id.write_text("boot-1\n")
            hal_pid = root / "hal_pid"
            hal_pid.write_text("100\n")
            audioserver_pid = root / "audioserver_pid"
            audioserver_pid.write_text("300\n")
            factory_loaded = root / "factory_loaded"
            factory_loaded.write_text("0\n")
            controls = root / "controls"

            dumpsys = mock_executable(
                mocks / "dumpsys",
                f'''if [ "$1" = --pid ]; then
  cat "$MOCK_FACTORY_PID"
  exit 0
fi
if [ "$(cat "$MOCK_FACTORY_LOADED")" = 1 ]; then
  echo 'Effects (22):'
else
  echo 'Effects (21):'
fi
cat <<'UUIDS'
{STOCK_UUIDS}
UUIDS
if [ "$(cat "$MOCK_FACTORY_LOADED")" = 1 ]; then
  echo 'UUID: {JDSP_UUID}'
fi
''',
            )
            service = mock_executable(
                mocks / "service",
                '''if [ "$2" = android.hardware.audio.effect.IFactory/default ] ||
   { [ "$2" = android.hardware.audio.effect.IFactory/aml ] &&
     [ "${MOCK_AML_ACTIVE:-0}" = 1 ] &&
     [ ! -f "$MOCK_AML_RESTARTED" ]; }; then
  echo "Service $2: found"
else
  echo "Service $2: not found"
fi
''',
            )
            linker = mock_executable(mocks / "linker64", "exit 0\n")
            getprop = mock_executable(mocks / "getprop", ":\n")
            setprop = mock_executable(
                mocks / "setprop",
                '''echo "$1 $2" >>"$MOCK_CONTROLS"
if [ "$1" = ctl.restart ] && [ "$2" = vendor.audio-hal-aidl ]; then
  [ -n "$MOCK_AML_RESTARTED" ] && echo 1 >"$MOCK_AML_RESTARTED"
  echo 200 >"$MOCK_HAL_PID"
  echo 400 >"$MOCK_AUDIOSERVER_PID"
  echo 1 >"$MOCK_FACTORY_LOADED"
  mkdir -p "$MOCK_PROC_ROOT/200"
  mkdir -p "$MOCK_PROC_ROOT/400"
fi
''',
            )
            pidof = mock_executable(
                mocks / "pidof",
                '''if [ "$1" = audioserver ]; then
  count=$(cat "$MOCK_AUDIO_LOOKUPS" 2>/dev/null || echo 0)
  count=$((count + 1))
  echo "$count" >"$MOCK_AUDIO_LOOKUPS"
  if [ "$count" -eq 2 ]; then exit 0; fi
  cat "$MOCK_AUDIOSERVER_PID"
elif [ "$1" = -s ] && [ "$2" = vendor.aml.effect-service ] &&
     [ "${MOCK_AML_ACTIVE:-0}" = 1 ] &&
     [ ! -f "$MOCK_AML_RESTARTED" ]; then
  echo 500
elif [ "$1" = -s ]; then
  cat "$MOCK_HAL_PID"
fi
''',
            )
            sleep = mock_executable(mocks / "sleep", ":\n")

            env = os.environ.copy()
            env.update(
                {
                    "KSU_LATE_LOAD": "1",
                    "JDSP_COMPAT_PROFILE": "mustang",
                    "JDSP_EFFECT_XML": str(xml),
                    "JDSP_EFFECT_LIB": str(lib),
                    "JDSP_BOOT_ID_FILE": str(boot_id),
                    "JDSP_PROC_ROOT": str(proc),
                    "JDSP_DUMPSYS_BIN": str(dumpsys),
                    "JDSP_SERVICE_BIN": str(service),
                    "JDSP_LINKER_BIN": str(linker),
                    "JDSP_GETPROP_BIN": str(getprop),
                    "JDSP_SETPROP_BIN": str(setprop),
                    "JDSP_PIDOF_BIN": str(pidof),
                    "JDSP_SLEEP_BIN": str(sleep),
                    "MOCK_HAL_PID": str(hal_pid),
                    "MOCK_FACTORY_LOADED": str(factory_loaded),
                    "MOCK_AUDIOSERVER_PID": str(audioserver_pid),
                    "MOCK_AUDIO_LOOKUPS": str(root / "audio-lookups"),
                    "MOCK_CONTROLS": str(controls),
                    "MOCK_PROC_ROOT": str(proc),
                    "JDSP_COMPAT_PROFILE": "mustang",
                }
            )
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("READY reason=target_loaded restart=once", (logs / "audio-reload.status").read_text())
            self.assertIn("pixaml=not_active", (logs / "audio-reload.status").read_text())
            self.assertEqual(controls.read_text().splitlines(), ["ctl.restart vendor.audio-hal-aidl"])
            self.assertEqual(
                (logs / "audio-reload.boot-id").read_text().splitlines(),
                ["boot-1", "200"],
            )

            # Re-entering service for the same HAL process must not restart it
            # again, even if the effect has disappeared from its factory.
            controls.write_text("")
            factory_loaded.write_text("0\n")
            (root / "audio-lookups").write_text("0\n")
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (logs / "audio-reload.status").read_text().strip(),
                "BLOCKED reason=reload_already_attempted_for_hal_instance",
            )
            self.assertEqual(controls.read_text(), "")

            # A userspace/soft reboot can replace the HAL while preserving the
            # kernel boot id. Allow one guarded refresh for that new instance.
            controls.write_text("")
            hal_pid.write_text("500\n")
            audioserver_pid.write_text("600\n")
            (proc / "500").mkdir(exist_ok=True)
            (proc / "600").mkdir(exist_ok=True)
            (root / "audio-lookups").write_text("0\n")
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("READY reason=target_loaded restart=once", (logs / "audio-reload.status").read_text())
            self.assertEqual(controls.read_text().splitlines(), ["ctl.restart vendor.audio-hal-aidl"])
            self.assertEqual(
                (logs / "audio-reload.boot-id").read_text().splitlines(),
                ["boot-1", "200"],
            )

            # Older releases stored only the kernel boot id; allow one
            # migration attempt to the HAL-instance guard format.
            controls.write_text("")
            factory_loaded.write_text("0\n")
            (logs / "audio-reload.boot-id").write_text("boot-1\n")
            hal_pid.write_text("700\n")
            audioserver_pid.write_text("800\n")
            (proc / "700").mkdir(exist_ok=True)
            (proc / "800").mkdir(exist_ok=True)
            (root / "audio-lookups").write_text("0\n")
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("READY reason=target_loaded restart=once", (logs / "audio-reload.status").read_text())
            self.assertEqual(controls.read_text().splitlines(), ["ctl.restart vendor.audio-hal-aidl"])
            self.assertEqual(
                (logs / "audio-reload.boot-id").read_text().splitlines(),
                ["boot-1", "200"],
            )

            (logs / "audio-reload.boot-id").unlink()
            controls.write_text("")
            factory_loaded.write_text("0\n")
            hal_pid.write_text("100\n")
            audioserver_pid.write_text("300\n")
            (root / "audio-lookups").write_text("0\n")
            env["MOCK_AML_ACTIVE"] = "1"
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("READY reason=target_loaded restart=once", (logs / "audio-reload.status").read_text())
            self.assertIn("pixaml=preserved", (logs / "audio-reload.status").read_text())
            self.assertEqual(controls.read_text().splitlines(), ["ctl.restart vendor.audio-hal-aidl"])

            (logs / "audio-reload.boot-id").unlink()
            controls.write_text("")
            factory_loaded.write_text("0\n")
            hal_pid.write_text("100\n")
            audioserver_pid.write_text("300\n")
            (root / "audio-lookups").write_text("0\n")
            aml_restarted = root / "aml-restarted"
            env["MOCK_AML_RESTARTED"] = str(aml_restarted)
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (logs / "audio-reload.status").read_text().strip(),
                "BLOCKED reason=pixaml_factory_lost_after_audio_restart",
            )
            self.assertEqual(controls.read_text().splitlines(), ["ctl.restart vendor.audio-hal-aidl"])

    def test_late_load_service_starts_app_helper_before_audio_reload_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp)
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "service.sh", module / "service.sh")
            (module / ".late-load-reload-experimental").touch()
            (module / "jdsp_app.sh").write_text(
                '#!/system/bin/sh\n[ -z "$MODPATH" ] && MODPATH="${0%/*}"\necho app >>"$MODPATH/logs/app-helper.calls"\n'
            )
            (module / "audio-reload.sh").write_text(
                '#!/system/bin/sh\nMODPATH="${0%/*}"\necho "KSU_LATE_LOAD=$KSU_LATE_LOAD" >"$MODPATH/logs/audio-reload.env"\necho BLOCKED reason=test_audio_block >"$MODPATH/logs/audio-reload.status"\n'
            )
            result = subprocess.run(
                ["sh", str(module / "service.sh")],
                env=os.environ.copy(),
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
            self.assertEqual(calls.read_text(), "app\n")
            self.assertEqual(
                (module / "logs/audio-reload.env").read_text(),
                "KSU_LATE_LOAD=1\n",
            )
            self.assertEqual(
                (module / "logs/service.status").read_text(),
                "BLOCKED reason=test_audio_block\n",
            )


    def test_portable_late_load_patches_canonical_native_config_without_pixel_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = self.make_late_load_module(str(root / "module"))
            linker = mock_executable(module / "linker", "exit 0\n")
            fsroot = root / "roots"
            vendor_etc = fsroot / "vendor/etc"
            vendor_etc.mkdir(parents=True)
            native = vendor_etc / "audio_effects_config.xml"
            native.write_text(
                """
<audio_effects_conf>
    <libraries>
        <library name="vendorfx" path="libsamsungfx.so"/>
    </libraries>
    <effects>
        <effect name="vendor_fx" library="vendorfx" uuid="11111111-2222-3333-4444-555555555555"/>
    </effects>
</audio_effects_conf>
"""
            )
            env = self.env_for_post_fs(module, linker)
            env.update(
                {
                    "JDSP_COMPAT_PROFILE": "portable",
                    "JDSP_SOURCE_VENDOR_CONFIG": str(module / "missing.xml"),
                    "JDSP_CONFIG_ROOTS": str(vendor_etc),
                    "JDSP_FS_ROOT": str(fsroot),
                }
            )
            result = subprocess.run(["sh", str(module / "post-fs-data.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            patched = (module / "system/vendor/etc/audio_effects_config.xml").read_text()
            self.assertIn(JDSP_UUID, patched)
            self.assertIn('name="vendorfx"', patched)
            status = (module / "logs/late-load.status").read_text()
            self.assertIn("READY late_load=1 vendor_config=portable_native_aidl_config:/vendor/etc/audio_effects_config.xml", status)
            context = (module / "logs/late-load-context.txt").read_text()
            self.assertIn("profile=portable", context)
            self.assertIn("native_config_candidate=/vendor/etc/audio_effects_config.xml", context)

    def test_portable_late_load_uses_highest_priority_native_config_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = self.make_late_load_module(str(root / "module"))
            linker = mock_executable(module / "linker", "exit 0\n")
            fsroot = root / "roots"
            odm = fsroot / "odm/etc"
            product = fsroot / "product/etc"
            odm.mkdir(parents=True)
            product.mkdir(parents=True)
            body = """
<audio_effects_conf>
    <libraries>
    </libraries>
    <effects>
    </effects>
</audio_effects_conf>
"""
            (odm / "audio_effects_config.xml").write_text(body)
            (product / "audio_effects_config.xml").write_text(body)
            env = self.env_for_post_fs(module, linker)
            env.update(
                {
                    "JDSP_COMPAT_PROFILE": "portable",
                    "JDSP_SOURCE_VENDOR_CONFIG": str(module / "missing.xml"),
                    "JDSP_CONFIG_ROOTS": f"{odm} {product}",
                    "JDSP_FS_ROOT": str(fsroot),
                }
            )
            result = subprocess.run(["sh", str(module / "post-fs-data.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((module / "skip_mount").exists())
            self.assertIn("READY late_load=1", (module / "logs/late-load.status").read_text())
            self.assertTrue((module / "system/odm/etc/audio_effects_config.xml").exists())
            self.assertFalse((module / "system/product/etc/audio_effects_config.xml").exists())

    def test_portable_audio_reload_does_not_restart_unknown_hal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = root / "module"
            logs = module / "logs"
            mocks = root / "mocks"
            module.mkdir()
            logs.mkdir()
            mocks.mkdir()
            shutil.copy2(ROOT / "audio-reload.sh", module / "audio-reload.sh")
            (module / ".late-load-reload-experimental").touch()
            xml = root / "audio_effects_config.xml"
            xml.write_text(f'<effect name="jamesdsp" uuid="{JDSP_UUID}"/>\n')
            lib = root / "libjamesdsp.so"
            lib.touch()
            controls = root / "controls"
            dumpsys = mock_executable(mocks / "dumpsys", "echo 'Effects (21):'\n")
            service = mock_executable(mocks / "service", "echo 'Service android.hardware.audio.effect.IFactory/default: found'\n")
            linker = mock_executable(mocks / "linker64", "exit 0\n")
            setprop = mock_executable(mocks / "setprop", 'echo "$@" >>"$MOCK_CONTROLS"\n')
            env = {
                **os.environ,
                "KSU_LATE_LOAD": "1",
                "JDSP_COMPAT_PROFILE": "portable",
                "JDSP_EFFECT_XML": str(xml),
                "JDSP_EFFECT_LIB": str(lib),
                "JDSP_DUMPSYS_BIN": str(dumpsys),
                "JDSP_SERVICE_BIN": str(service),
                "JDSP_LINKER_BIN": str(linker),
                "JDSP_SETPROP_BIN": str(setprop),
                "MOCK_CONTROLS": str(controls),
            }
            result = subprocess.run(["sh", str(module / "audio-reload.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("default_factory_needs_device_specific_refresh", (logs / "audio-reload.status").read_text())
            self.assertFalse(controls.exists())

    def run_jdsp_app(self, module: pathlib.Path, mocks: pathlib.Path, pm_body: str, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
        temp_apk = module / "tmp-install.apk"
        mock_executable(mocks / "getprop", "echo 1\n")
        mock_executable(mocks / "chcon", "exit 0\n")
        mock_executable(mocks / "pm", pm_body)
        return subprocess.run(
            ["sh", str(module / "jdsp_app.sh")],
            env={
                **os.environ,
                "PATH": f"{mocks}:{os.environ['PATH']}",
                "JDSP_TEMP_INSTALL_PATH": str(temp_apk),
                "MOCK_PM_LOG": str(module.parent / "pm.log"),
                **(extra_env or {}),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    def make_host_tar_wrapper(self, path: pathlib.Path) -> pathlib.Path:
        host_tar = shutil.which("tar")
        if not host_tar:
            self.skipTest("host tar is unavailable")
        return mock_executable(
            path,
            "python3 -c 'import os,sys; a=[x for x in sys.argv[1:] if x not in (\"--numeric-owner\",\"--selinux\")]; os.execv(\""
            + host_tar
            + "\", [\""
            + host_tar
            + "\"]+a)' \"$@\"\n",
        )

    def test_jdsp_app_installer_exits_when_exact_package_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = root / "module"
            mocks = root / "mocks"
            module.mkdir()
            mocks.mkdir()
            (module / "logs").mkdir()
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            pm_body = '''if [ "$1 $2" = "list packages" ]; then
  echo package:james.dsp
  exit 0
fi
echo "$@" >>"$MOCK_PM_LOG"
'''
            result = self.run_jdsp_app(module, mocks, pm_body)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already installed", (module / "logs/jamesdsp_app_install.log").read_text())
            self.assertFalse((root / "pm.log").exists())

    def test_jdsp_app_installer_updates_existing_app_without_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = root / "module", root / "mocks"
            module.mkdir(); mocks.mkdir(); (module / "logs").mkdir()
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            pm_body = '''if [ "$1 $2" = "list packages" ]; then echo package:james.dsp; exit 0; fi
if [ "$1 $2" = "list users" ]; then echo 'UserInfo{0:Owner:13}'; exit 0; fi
echo "$@" >>"$MOCK_PM_LOG"
echo Success
exit 0
'''
            result = self.run_jdsp_app(module, mocks, pm_body, {"JDSP_FLASH_INSTALL": "1"})
            self.assertEqual(result.returncode, 0, result.stderr)
            log = (root / "pm.log").read_text()
            self.assertIn("install --user 0 -r -g", log)
            self.assertNotIn("uninstall", log)
            self.assertIn("Updated installed app", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_does_not_treat_non_success_output_as_update_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks = root / "module", root / "mocks"
            module.mkdir(); mocks.mkdir(); (module / "logs").mkdir()
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            pm_body = '''if [ "$1 $2" = "list packages" ]; then echo package:james.dsp; exit 0; fi
if [ "$1 $2" = "list users" ]; then echo 'UserInfo{0:Owner:13}'; exit 0; fi
echo "$@" >>"$MOCK_PM_LOG"
echo 'Failure [INSTALL_FAILED_INTERNAL_ERROR]'
exit 0
'''
            result = self.run_jdsp_app(module, mocks, pm_body, {"JDSP_FLASH_INSTALL": "1"})
            self.assertEqual(result.returncode, 0, result.stderr)
            log = (module / "logs/jamesdsp_app_install.log").read_text()
            self.assertIn("did not confirm installation success", log)
            self.assertIn("existing app preserved", log)
            self.assertNotIn("Updated installed app", log)
            self.assertNotIn("uninstall", (root / "pm.log").read_text())

    def test_jdsp_app_different_signature_requires_volume_down_and_defaults_to_keep(self):
        for key_event, should_uninstall in (("KEY_VOLUMEDOWN DOWN", True), ("KEY_VOLUMEUP DOWN", False), ("", False)):
            with self.subTest(key_event=key_event), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                module, mocks = root / "module", root / "mocks"
                module.mkdir(); mocks.mkdir(); (module / "logs").mkdir()
                shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
                (module / "JamesDSPManager.apk").write_text("apk")
                state = root / "install-count"
                pm_body = f'''if [ "$1 $2" = "list packages" ]; then echo package:james.dsp; exit 0; fi
if [ "$1 $2" = "list users" ]; then echo 'UserInfo{{0:Owner:13}}'; exit 0; fi
echo "$@" >>"$MOCK_PM_LOG"
if [ "$1" = install ]; then
  n=0; [ -f "{state}" ] && n=$(cat "{state}"); n=$((n+1)); echo "$n" >"{state}"
  [ "$n" -eq 1 ] && {{ echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]'; exit 0; }}
fi
echo Success
exit 0
'''
                mock_executable(mocks / "timeout", 'shift; exec "$@"\n')
                mock_executable(mocks / "getevent", f'echo "{key_event}"\n')
                result = self.run_jdsp_app(
                    module,
                    mocks,
                    pm_body,
                    {"JDSP_FLASH_INSTALL": "1", "JDSP_GETEVENT_BIN": str(mocks / "getevent")},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                pm_log = (root / "pm.log").read_text()
                if should_uninstall:
                    self.assertIn("uninstall james.dsp", pm_log)
                    self.assertGreaterEqual(pm_log.count("install --user 0 -r -g"), 2)
                else:
                    self.assertNotIn("uninstall", pm_log)
                    self.assertIn("Replacement declined or timed out", (module / "logs/jamesdsp_app_install.log").read_text())

    def test_jdsp_app_backs_up_and_restores_data_only_after_volume_down_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks, data = root / "module", root / "mocks", root / "data"
            module.mkdir(); mocks.mkdir(); (module / "logs").mkdir()
            (data / "user/0/james.dsp/shared_prefs").mkdir(parents=True)
            (data / "user_de/0/james.dsp").mkdir(parents=True)
            (data / "media/0/Android/data/james.dsp/files").mkdir(parents=True)
            (data / "user/0/james.dsp/shared_prefs/settings.xml").write_text("<settings>preserve</settings>")
            (data / "user_de/0/james.dsp/device-protected.txt").write_text("device data")
            (data / "media/0/Android/data/james.dsp/files/export.txt").write_text("external data")
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            backup = module / ".jdsp-appdata-migration"
            state = root / "install-count"
            pm_body = f'''if [ "$1 $2" = "list packages" ]; then
  if [ "$3" = "-U" ]; then echo "package:james.dsp uid:10042"; else echo package:james.dsp; fi
  exit 0
fi
if [ "$1 $2" = "list users" ]; then echo 'UserInfo{{0:Owner:13}}'; exit 0; fi
echo "$@" >>"$MOCK_PM_LOG"
if [ "$1" = install ]; then
  n=0; [ -f "{state}" ] && n=$(cat "{state}"); n=$((n+1)); echo "$n" >"{state}"
  if [ "$n" -eq 1 ]; then echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]'; exit 0; fi
fi
if [ "$1" = uninstall ]; then
  if [ ! -s "{backup / 'data.tar'}" ]; then echo 'ERROR: no pre-uninstall backup'; exit 1; fi
  rm -rf "{data}/user/0/james.dsp" "{data}/user_de/0/james.dsp" "{data}/media/0/Android/data/james.dsp"
fi
echo Success
exit 0
'''
            mock_executable(mocks / "timeout", 'shift; exec "$@"\n')
            mock_executable(mocks / "getevent", 'echo "KEY_VOLUMEDOWN DOWN"\n')
            self.make_host_tar_wrapper(mocks / "tar")
            mock_executable(mocks / "chown", 'echo "$@" >>"$MOCK_CHOWN_LOG"\nexit 0\n')
            mock_executable(mocks / "restorecon", 'echo "$@" >>"$MOCK_RESTORECON_LOG"\nexit 0\n')
            result = self.run_jdsp_app(
                module, mocks, pm_body,
                {
                    "JDSP_FLASH_INSTALL": "1",
                    "JDSP_GETEVENT_BIN": str(mocks / "getevent"),
                    "JDSP_DATA_ROOT": str(data),
                    "JDSP_DATA_BACKUP_DIR": str(backup),
                    "JDSP_TAR_BIN": str(mocks / "tar"),
                    "JDSP_CHOWN_BIN": str(mocks / "chown"),
                    "JDSP_RESTORECON_BIN": str(mocks / "restorecon"),
                    "MOCK_CHOWN_LOG": str(root / "chown.log"),
                    "MOCK_RESTORECON_LOG": str(root / "restorecon.log"),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("uninstall james.dsp", (root / "pm.log").read_text())
            self.assertEqual((data / "user/0/james.dsp/shared_prefs/settings.xml").read_text(), "<settings>preserve</settings>")
            self.assertEqual((data / "user_de/0/james.dsp/device-protected.txt").read_text(), "device data")
            self.assertEqual((data / "media/0/Android/data/james.dsp/files/export.txt").read_text(), "external data")
            self.assertFalse(backup.exists(), "successful restore should remove the temporary archive")
            self.assertIn("10042:10042", (root / "chown.log").read_text())
            self.assertTrue((root / "restorecon.log").exists())
            log = (module / "logs/jamesdsp_app_install.log").read_text()
            self.assertIn("App-data backup created before uninstall", log)
            self.assertIn("App-data restore completed", log)
            self.assertNotIn("preserve</settings>", log)

    def test_jdsp_app_keeps_original_if_confirmed_migration_backup_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks, data = root / "module", root / "mocks", root / "data"
            module.mkdir(); mocks.mkdir(); (module / "logs").mkdir()
            (data / "user/0/james.dsp").mkdir(parents=True)
            (data / "user/0/james.dsp/settings").write_text("keep")
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            pm_body = '''if [ "$1 $2" = "list packages" ]; then echo package:james.dsp; exit 0; fi
if [ "$1 $2" = "list users" ]; then echo 'UserInfo{0:Owner:13}'; exit 0; fi
echo "$@" >>"$MOCK_PM_LOG"
if [ "$1" = install ]; then echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]'; exit 0; fi
echo Success
'''
            mock_executable(mocks / "timeout", 'shift; exec "$@"\n')
            mock_executable(mocks / "getevent", 'echo "KEY_VOLUMEDOWN DOWN"\n')
            mock_executable(mocks / "tar", 'exit 1\n')
            result = self.run_jdsp_app(
                module, mocks, pm_body,
                {
                    "JDSP_FLASH_INSTALL": "1",
                    "JDSP_GETEVENT_BIN": str(mocks / "getevent"),
                    "JDSP_DATA_ROOT": str(data),
                    "JDSP_TAR_BIN": str(mocks / "tar"),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("uninstall", (root / "pm.log").read_text())
            self.assertIn("app-data backup failed", (module / "logs/jamesdsp_app_install.log").read_text())
            self.assertEqual((data / "user/0/james.dsp/settings").read_text(), "keep")

    def test_jdsp_app_retries_pending_restore_from_boot_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module, mocks, data = root / "module", root / "mocks", root / "data"
            module.mkdir(); mocks.mkdir(); (module / "logs").mkdir()
            (data / "user/0/james.dsp").mkdir(parents=True)
            shutil.copy2(ROOT / "jdsp_app.sh", module / "jdsp_app.sh")
            (module / "JamesDSPManager.apk").write_text("apk")
            backup = module / ".jdsp-appdata-migration"
            backup.mkdir()
            (backup / "restore-pending").touch()
            (backup / "users.list").write_text("0\n")
            source = root / "source/user/0/james.dsp"
            source.mkdir(parents=True)
            (source / "settings").write_text("restored on retry")
            self.make_host_tar_wrapper(mocks / "tar")
            subprocess.run([str(mocks / "tar"), "-c", "-f", str(backup / "data.tar"), "-C", str(root / "source"), "user"], check=True)
            pm_body = '''if [ "$1 $2" = "list packages" ]; then
  if [ "$3" = "-U" ]; then echo "package:james.dsp uid:10042"; else echo package:james.dsp; fi
  exit 0
fi
echo "$@" >>"$MOCK_PM_LOG"
exit 0
'''
            mock_executable(mocks / "chown", 'exit 0\n')
            mock_executable(mocks / "restorecon", 'exit 0\n')
            result = self.run_jdsp_app(
                module, mocks, pm_body,
                {
                    "JDSP_DATA_ROOT": str(data),
                    "JDSP_DATA_BACKUP_DIR": str(backup),
                    "JDSP_TAR_BIN": str(mocks / "tar"),
                    "JDSP_CHOWN_BIN": str(mocks / "chown"),
                    "JDSP_RESTORECON_BIN": str(mocks / "restorecon"),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((data / "user/0/james.dsp/settings").read_text(), "restored on retry")
            self.assertFalse(backup.exists())

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
if [ "$1" = install ]; then echo Success; fi
exit 0
'''
            result = self.run_jdsp_app(module, mocks, pm_body)
            self.assertEqual(result.returncode, 0, result.stderr)
            log = pm_log.read_text()
            self.assertIn("install --user 0 -r -g", log)
            self.assertIn("disable --user 0 james.dsp", log)
            self.assertIn("enable --user 0 james.dsp", log)


    def test_patch_script_adapts_unknown_late_load_with_available_soname(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            module = root / "module"
            tools = module / "tools"
            libdir = module / "system/vendor/lib64/soundfx"
            mocks = root / "mocks"
            tools.mkdir(parents=True)
            libdir.mkdir(parents=True)
            mocks.mkdir()
            shutil.copy2(ROOT / "patch.sh", module / "patch.sh")
            (libdir / "libjamesdsp.so").touch()
            (libdir / "libjamesdsp_real.so").touch()
            patchelf_log = root / "patchelf.log"
            mock_executable(
                tools / "patchelf",
                f'''case "$1" in
  --print-needed) echo android.hardware.audio.effect-V1-ndk.so ;;
  --replace-needed) echo "$@" >>"{patchelf_log}" ;;
esac
''',
            )
            mock_executable(mocks / "find", "echo /vendor/lib64/android.hardware.audio.effect-V9-ndk.so\n")
            mock_executable(mocks / "sync", "exit 0\n")
            env = {
                **os.environ,
                "PATH": f"{mocks}:{os.environ['PATH']}",
                "AIDL": "true",
                "MODPATH": str(module),
                "MOD_VENDOR": str(module / "system/vendor"),
            }
            result = subprocess.run(["sh", str(module / "patch.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            patch_log = patchelf_log.read_text()
            self.assertIn("--replace-needed android.hardware.audio.effect-V1-ndk.so android.hardware.audio.effect-V9-ndk.so", patch_log)
            self.assertIn("libjamesdsp_real.so", patch_log)

            patchelf_log.unlink()
            env.update({"KSU_LATE_LOAD": "1", "JDSP_COMPAT_PROFILE": "portable"})
            result = subprocess.run(["sh", str(module / "patch.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "--replace-needed android.hardware.audio.effect-V1-ndk.so android.hardware.audio.effect-V9-ndk.so",
                patchelf_log.read_text(),
            )

    def test_late_load_reload_script_has_no_restart_loop_or_killall(self):
        combined = (ROOT / "audio-reload.sh").read_text()
        self.assertNotIn("killall", combined)
        self.assertNotIn("while true", combined)
        self.assertIn('ctl.restart "$INIT_SERVICE"', combined)
        self.assertIn("reload_already_attempted_for_hal_instance", combined)
        self.assertIn("default_factory_needs_device_specific_refresh", combined)
        self.assertIn('service_found "$AML_FACTORY"', combined)
        self.assertIn("pixaml_state=not_active", combined)
        self.assertIn("pixaml_factory_lost_after_audio_restart", combined)
        self.assertIn("audioserver_pid_missing_after_restart", combined)

    def test_release_contains_only_root_apks_and_reload_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "JamesDSPManager-v6.5.9.zip"
            env = {**os.environ, "JDSP_PACKAGE_OUTPUT": str(zip_path)}
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_659_mustang_late_load.py")],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                self.assertIn("audio-reload.sh", names)
                self.assertIn("post-fs-data.sh", names)
                readme = archive.read("README.md").decode("utf-8")
                self.assertIn("JamesDSP does not depend on PIXAML", readme)
                self.assertIn("through several soft reboots", readme)
                self.assertIn("version=v6.5.9", archive.read("module.prop").decode("utf-8"))
                update = archive.read("update.json").decode("utf-8")
                self.assertIn('"version": "v6.5.9"', update)
                self.assertIn("github.com/zahahah/JamesDSPManager/releases/download/v6.5.9", update)
                self.assertEqual(
                    {name for name in names if name.endswith(".apk")},
                    {"common/files/JamesDSPManagerThePBone.apk"},
                )
                self.assertFalse(any("rootless" in name.lower() for name in names))

    def test_installer_requires_confirmation_before_removing_an_existing_app(self):
        installer = (ROOT / "common/install.sh").read_text()
        self.assertIn("Installing ThePBone 1.6.15 root app", installer)
        self.assertIn("Same-signature apps are updated in place", installer)
        self.assertIn("Different signatures require explicit volume-key confirmation", installer)
        self.assertIn('JDSP_FLASH_INSTALL=1', installer)
        self.assertIn('mv -f "$MODPATH/common/files/JamesDSPManagerThePBone.apk"', installer)
        self.assertNotIn("Which UI you want to install?", installer)
        self.assertNotIn("Original 9.5", installer)
        self.assertNotIn(".apkorig", installer)
        app_installer = (ROOT / "jdsp_app.sh").read_text()
        self.assertIn('Volume DOWN:', app_installer)
        self.assertIn('Volume UP:', app_installer)
        self.assertIn('timeout "$KEY_TIMEOUT"', app_installer)
        self.assertIn('$PM_CMD uninstall "$PKG"', app_installer)


if __name__ == "__main__":
    unittest.main()
