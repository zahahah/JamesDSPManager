import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test13Tests(unittest.TestCase):
    def test_unavailable_text_replaces_false_absence_claim(self):
        spec = importlib.util.spec_from_file_location(
            "patch_app", ROOT / "tools/patch_thepbone_unavailable_text.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            resources = Path(tmp) / "res"
            values = resources / "values"
            values.mkdir(parents=True)
            source = "<resources>\n" + "\n".join(
                f'<string name="{name}">Old text</string>'
                for name in module.ENGLISH
            ) + "\n</resources>\n"
            (values / "strings.xml").write_text(source)
            self.assertEqual(module.patch_strings(resources), 1)
            result = (values / "strings.xml").read_text()
            self.assertIn("JamesDSP effect not detected", result)
            self.assertIn("does not turn", module.__doc__)
            self.assertNotIn("Old text", result)

    def test_samsung_refresh_is_scoped_to_test18_marker_and_version(self):
        reload_script = (ROOT / "audio-reload.sh").read_text()
        branch = reload_script.split('if [ "$JDSP_PROFILE" = samsung_h8q ]; then')[-1]
        self.assertIn('sh "$MODPATH/aidl-factory-diagnostics.sh"', branch)
        self.assertIn("samsung_factory_descriptor_missing", branch)
        self.assertIn('[ "$module_version" = 127 ]', branch)
        self.assertIn('[ "$module_version" = 128 ]', branch)
        self.assertIn('.test18-samsung-viper-refresh', branch)
        self.assertIn('samsung_h8q_refresh', branch)
        self.assertIn('set_perm "$MODPATH/aidl-factory-diagnostics.sh" 0 0 0755',
                      (ROOT / "customize.sh").read_text())
        diagnostic = (ROOT / "aidl-factory-diagnostics.sh").read_text()
        for unsafe in ("ctl.restart", "mount -", "setprop", "killall"):
            self.assertNotIn(unsafe, diagnostic)
        for script in ("audio-reload.sh", "aidl-factory-diagnostics.sh"):
            subprocess.run(["sh", "-n", str(ROOT / script)], check=True)

    def test_experimental_zip_keeps_stable_separate(self):
        app = ROOT / "dist/JamesDSPManagerThePBone-v1.6.15-effect-status-test3.apk"
        if not app.is_file():
            self.skipTest("Locally signed test APK is not present")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test13.zip"
            script = ROOT / "tools/package_test13.py"
            import os
            result = subprocess.run(
                ["python3", str(script)],
                env={**os.environ, "JDSP_TEST13_PACKAGE_OUTPUT": str(output)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertNotIn("update.json", names)
                self.assertIn("aidl-factory-diagnostics.sh", names)
                self.assertIn("tools/libjamesdsp_pinwrap.so", names)
                self.assertIn("TEST13.md", names)
                self.assertEqual(archive.read("common/files/JamesDSPManagerThePBone.apk"), app.read_bytes())
                props = archive.read("module.prop").decode()
                self.assertIn("versionCode=123", props)
                self.assertIn("test13-samsung-effect-status", props)


if __name__ == "__main__":
    unittest.main()
