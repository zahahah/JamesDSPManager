#!/usr/bin/env python3
"""Build test19 from test18 with the updated optional RootJamesDSP APK."""

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_test18 as previous


ROOT = previous.ROOT
OUTPUT = Path(os.environ.get(
    "JDSP_TEST19_PACKAGE_OUTPUT",
    ROOT / "dist/JamesDSPManager-v6.5.9-test19-samsung-root-app.zip",
))


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("Experimental package cannot overwrite the stable release")

    with TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "test18.zip"
        previous.build(baseline)
        with ZipFile(baseline) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()}

    props = payloads["module.prop"].decode()
    props = props.replace(
        "version=v6.5.9-test18-samsung-viper-method\n",
        "version=v6.5.9-test19-samsung-root-app\n",
    ).replace("versionCode=127\n", "versionCode=128\n")
    if "versionCode=128\n" not in props:
        raise ValueError("Unexpected test18 module version")
    payloads["module.prop"] = props.encode()
    payloads["TEST19.md"] = (ROOT / "TEST19.md").read_bytes()

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, data in payloads.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = previous.stable.PAYLOADS.get(
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
