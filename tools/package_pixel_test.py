#!/usr/bin/env python3
"""Package the Pixel A/B candidate; exactly two payload changes are allowed."""
import importlib.util
import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = "d60a800161ed6fcb6c01aa3026069dffff54bf7a"
APP_REVISION = "1529b67b90acd786a0368fa4f8c01f04cbb904ba"
EXPECTED = {
    "common/files/aidl/libjamesdsp.so": "8a774733621c4b5f34b3dafef27ab3f5b02fdf7c6cf97bbef9af3535cea66955",
    "common/files/JamesDSPManagerThePBone.apk": "b69214755c723988d9456ef6381ee2fd9fd956e67f26960f2ab0b45bd7de5f55",
}

def validate_payloads(current, baseline):
    if current.keys() != baseline.keys():
        raise ValueError("Payload paths changed")
    changed = {name for name in current if current[name] != baseline[name]}
    if changed != EXPECTED.keys():
        raise ValueError(f"Expected exactly the driver and Pixel APK changes, got {sorted(changed)}")
    for name, expected in EXPECTED.items():
        if sha256(current[name]).hexdigest() != expected:
            raise ValueError(f"Unexpected replacement hash: {name}")
    return sorted(changed)

def build():
    spec = importlib.util.spec_from_file_location("baseline_package", ROOT / "tools/package_659_mustang_late_load.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    current = {name: (ROOT / name).read_bytes() for name in package.PAYLOADS}
    baseline = {name: subprocess.check_output(["git", "show", f"{BASE}:{name}"], cwd=ROOT) for name in package.PAYLOADS}
    changed = validate_payloads(current, baseline)
    output = Path(os.environ.get("JDSP_PACKAGE_OUTPUT", ROOT / "dist/JamesDSPManager-v6.5.9-pixel-test-rebuilt-aidl.zip"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, mode in package.PAYLOADS.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
            archive.writestr(info, current[name])
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == list(package.PAYLOADS)
        assert all(archive.read(name) == data for name, data in current.items())
    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    report = {"module_base": BASE, "app_source_branch": "pixel-test", "app_source_revision": APP_REVISION,
              "app_release": "https://github.com/zahahah/RootJamesDSP/releases/tag/pixel-test",
              "app_release_asset_id": 652150602, "changed_payloads": changed, "replacement_sha256": EXPECTED,
              "zip_sha256": digest, "native_source_revision": "not supplied; user-provided build",
              "device_tested": False, "module_version_intentionally_unchanged": True}
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    return output

if __name__ == "__main__":
    print(build())
