#!/usr/bin/env python3
"""Package a Samsung late-load factory-startup log capture experiment."""

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_test15 as previous
import package_659_mustang_late_load as stable


ROOT = stable.ROOT
OUTPUT = Path(os.environ.get(
    "JDSP_TEST17_PACKAGE_OUTPUT",
    ROOT / "dist/JamesDSPManager-v6.5.9-test17-samsung-early-log.zip",
))
APP = ROOT / "dist/JamesDSPManagerThePBone-v1.6.15-samsung-aidl-diagnostic-test1.apk"
APP_SHA256 = "3a33f6fe4c0d68e7f14ff0944a21c074f53d66136337fa3b87797ebdc978426e"


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("Experimental package cannot overwrite the stable release")
    app = APP.read_bytes()
    if sha256(app).hexdigest() != APP_SHA256:
        raise ValueError("Unexpected signed Samsung diagnostic APK")

    with TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "test15.zip"
        previous.build(baseline)
        with ZipFile(baseline) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()
                        if name != "update.json"}

    props = payloads["module.prop"].decode()
    props = props.replace(
        "version=v6.5.9-test15-samsung-mountns-detection\n",
        "version=v6.5.9-test17-samsung-early-log\n",
    ).replace("versionCode=125\n", "versionCode=126\n")
    if "versionCode=126\n" not in props:
        raise ValueError("Unexpected test15 module version")
    payloads["module.prop"] = props.encode()
    payloads["post-fs-data.sh"] = (ROOT / "post-fs-data.sh").read_bytes()
    payloads["samsung-aidl-early-log.sh"] = (ROOT / "samsung-aidl-early-log.sh").read_bytes()
    payloads["common/files/JamesDSPManagerThePBone.apk"] = app
    payloads["TEST17.md"] = (ROOT / "TEST17.md").read_bytes()

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, data in payloads.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = stable.PAYLOADS.get(
                name, 0o100755 if name.endswith(".sh") else 0o100644
            )
            info.external_attr = mode << 16
            archive.writestr(info, data)

    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n"
    )
    return digest


if __name__ == "__main__":
    print(f"{OUTPUT.name} SHA-256 {build()}")
