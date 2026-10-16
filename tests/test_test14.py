import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class Test14Tests(unittest.TestCase):
    def test_wrapper_logs_each_aidl_boundary(self):
        source = (ROOT / "native/jdsp_aidl_pinwrap.c").read_text()
        for marker in (
            "event=wrapper_loaded",
            "event=query_effect_entered",
            "event=real_library_open_failed",
            "event=real_library_loaded",
            "query_effect_returned",
            "create_effect_entered",
            "create_effect_returned",
        ):
            self.assertIn(marker, source)

    def test_experimental_zip_contains_query_trace_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test14.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_test14.py")],
                env={**os.environ, "JDSP_TEST14_PACKAGE_OUTPUT": str(output)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output) as archive:
                props = archive.read("module.prop").decode()
                self.assertIn("versionCode=124", props)
                self.assertIn("test14-samsung-aidl-query-trace", props)
                self.assertIn("event=query_effect_entered", archive.read(
                    "tools/libjamesdsp_pinwrap.so").decode("latin-1"))
                self.assertIn("query trace", archive.read("TEST14.md").decode())


if __name__ == "__main__":
    unittest.main()
