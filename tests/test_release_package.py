import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTests(unittest.TestCase):
    def test_beta_archive_contains_only_updated_signed_root_apk(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "JamesDSPManager-v6.9.10-beta-1.zip"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/package_6910_beta1.py")],
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "JDSP_PACKAGE_OUTPUT": str(output),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = result.stdout.split()[-1]

            with ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(
                    {name for name in names if name.endswith(".apk")},
                    {"common/files/JamesDSPManagerThePBone.apk"},
                )
                self.assertEqual(
                    archive.read("common/files/JamesDSPManagerThePBone.apk"),
                    (ROOT / "common/files/release/JamesDSPManagerThePBone.apk").read_bytes(),
                )
                props = archive.read("module.prop").decode()
                self.assertIn("version=v6.9.10-beta-1", props)
                self.assertIn("versionCode=132", props)
                update = json.loads(archive.read("update.json"))
                self.assertEqual(update["version"], "v6.9.10-beta-1")
                self.assertEqual(update["versionCode"], 132)
                self.assertIn("releases/download/v6.9.10-beta-1/", update["zipUrl"])
                self.assertIn("/v6.9.10-beta-1/changelog.md", update["changelog"])
            self.assertEqual(output.with_suffix(".zip.sha256").read_text().split()[0], digest)
