import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test18Tests(unittest.TestCase):
    def test_eager_wrapper_loads_real_library_only_in_test_build(self):
        source = (ROOT / "native/jdsp_aidl_pinwrap.c").read_text()
        self.assertIn("JDSP_EAGER_PRELOAD_REAL", source)
        self.assertIn("event=real_library_preload_ready", source)
        self.assertIn("event=real_library_preload_failed", source)
        builder = (ROOT / "native/build_jdsp_aidl_eager_pinwrap.sh").read_text()
        self.assertIn("-DJDSP_EAGER_PRELOAD_REAL", builder)
        self.assertNotIn("JDSP_EAGER_PRELOAD_REAL", (ROOT / "native/build_jdsp_aidl_pinwrap.sh").read_text())

    def test_samsung_refresh_and_ndk_adaptation_are_test_only_opt_ins(self):
        reload_script = (ROOT / "audio-reload.sh").read_text()
        self.assertIn('.test18-samsung-viper-refresh', reload_script)
        self.assertIn('samsung_h8q_refresh', reload_script)
        patch_script = (ROOT / "patch.sh").read_text()
        self.assertIn("PATCH_DEFAULT=0", patch_script)
        self.assertIn('.test18-samsung-ndk-retarget', patch_script)

    def test_test18_zip_scopes_experiments_and_preserves_the_signed_diagnostic_apk(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test18.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test18.py")],
                env={**os.environ, "JDSP_TEST18_PACKAGE_OUTPUT": str(output)},
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                props = archive.read("module.prop").decode()
                self.assertIn("test18-samsung-viper-method", props)
                self.assertIn("versionCode=127", props)
                self.assertIn(".test18-samsung-viper-refresh", names)
                self.assertIn(".test18-samsung-ndk-retarget", names)
                self.assertIn("common/files/JamesDSPManagerZahah.apk", names)
                self.assertEqual(
                    archive.read("common/files/JamesDSPManagerZahah.apk"),
                    (ROOT / "common/files/JamesDSPManagerZahah.apk").read_bytes(),
                )
                self.assertIn("real_library_preload_ready", archive.read(
                    "tools/libjamesdsp_pinwrap.so").decode("latin-1"))
                self.assertIn("test-only", archive.read(
                    ".test18-samsung-viper-refresh").decode())
                self.assertNotIn("update.json", names)


if __name__ == "__main__":
    unittest.main()
