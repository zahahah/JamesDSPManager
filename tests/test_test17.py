import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test17Tests(unittest.TestCase):
    def test_early_capture_is_bounded_and_one_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "module.prop").write_text("versionCode=126\n")
            (module / "samsung-aidl-early-log.sh").write_bytes(
                (ROOT / "samsung-aidl-early-log.sh").read_bytes()
            )
            fake_logcat = module / "logcat"
            fake_logcat.write_text(
                "#!/bin/sh\n"
                "echo 'JDSPPinWrap: event=query_effect_entered'\n"
                "while :; do sleep 1; done\n"
            )
            fake_logcat.chmod(0o755)
            env = {
                **os.environ,
                "JDSP_LOGCAT_BIN": str(fake_logcat),
                "JDSP_CAPTURE_SECONDS": "2",
            }
            command = ["sh", str(module / "samsung-aidl-early-log.sh")]
            first = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            status = (module / "logs/samsung-aidl-early-log.status").read_text()
            log = (module / "logs/samsung-aidl-early-log.txt").read_text()
            self.assertIn("COMPLETE", status)
            self.assertIn("query_effect_entered", log)
            self.assertIn("capture_end=", log)

            second = subprocess.run(command, env=env, capture_output=True, text=True, timeout=3)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(log, (module / "logs/samsung-aidl-early-log.txt").read_text())

    def test_package_contains_only_diagnostic_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test17.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test17.py")],
                env={**os.environ, "JDSP_TEST17_PACKAGE_OUTPUT": str(output)},
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                props = archive.read("module.prop").decode()
                post_fs = archive.read("post-fs-data.sh").decode()
                self.assertIn("test17-samsung-early-log", props)
                self.assertIn("versionCode=126", props)
                self.assertIn("samsung-aidl-early-log.sh", names)
                self.assertIn("JDSP_PROFILE\" = samsung_h8q", post_fs)
                self.assertNotIn("update.json", names)
                self.assertFalse(any("rootless" in name.lower() for name in names))


if __name__ == "__main__":
    unittest.main()
