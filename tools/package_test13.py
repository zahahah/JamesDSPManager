#!/usr/bin/env python3
"""Package the Samsung effect-status experiment without changing stable assets."""

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_659_mustang_late_load as stable


ROOT = stable.ROOT
OUTPUT = Path(os.environ.get(
    "JDSP_TEST13_PACKAGE_OUTPUT",
    ROOT / "dist/JamesDSPManager-v6.5.9-test13-samsung-effect-status.zip",
))
APP = ROOT / "dist/JamesDSPManagerThePBone-v1.6.15-effect-status-test3.apk"
APP_SHA256 = "cb134663fe5b01132733173d11182cf1766f31097043eefa24ee64a354bd63ad"


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("Experimental package cannot overwrite the stable release")
    app = APP.read_bytes()
    if sha256(app).hexdigest() != APP_SHA256:
        raise ValueError("Unexpected signed test13 APK")

    with TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "baseline.zip"
        stable.build(baseline)
        with ZipFile(baseline) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()
                        if name != "update.json"}

    props = payloads["module.prop"].decode()
    props = props.replace("version=v6.5.9\n", "version=v6.5.9-test13-samsung-effect-status\n")
    props = props.replace("versionCode=111\n", "versionCode=123\n")
    props = props.replace("name=JamesDSP Manager\n", "name=JamesDSP Manager (portability test)\n")
    payloads["module.prop"] = props.encode()
    payloads["common/files/JamesDSPManagerThePBone.apk"] = app
    payloads["aidl-factory-diagnostics.sh"] = (ROOT / "aidl-factory-diagnostics.sh").read_bytes()
    payloads["tools/libjamesdsp_pinwrap.so"] = (ROOT / "tools/libjamesdsp_pinwrap.so").read_bytes()
    payloads["TEST13.md"] = (ROOT / "TEST13.md").read_bytes()

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, data in payloads.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = stable.PAYLOADS.get(name, 0o100755 if name.endswith(".sh") else 0o100644)
            info.external_attr = mode << 16
            archive.writestr(info, data)

    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n")
    return digest


if __name__ == "__main__":
    print(f"{OUTPUT.name} SHA-256 {build()}")
