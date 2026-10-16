#!/usr/bin/env python3
"""Build test20 from test19 with the Samsung discovery-retry app build."""

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_test19 as previous


ROOT = previous.ROOT
APP = ROOT / "common/files/JamesDSPManagerZahah-test62.apk"
APP_SHA256 = "9edbb02857e39cb1f3b4085ad669043e5009a038976cacad5ad75595faf211d4"
OUTPUT = Path(os.environ.get(
    "JDSP_TEST20_PACKAGE_OUTPUT",
    ROOT / "dist/JamesDSPManager-v6.5.9-test20-samsung-discovery-retry.zip",
))


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("Experimental package cannot overwrite the stable release")
    app = APP.read_bytes()
    if sha256(app).hexdigest() != APP_SHA256:
        raise ValueError("Unexpected owner-signed Samsung retry app")

    with TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "test19.zip"
        previous.build(baseline)
        with ZipFile(baseline) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()}

    props = payloads["module.prop"].decode()
    props = props.replace(
        "version=v6.5.9-test19-samsung-root-app\n",
        "version=v6.5.9-test20-samsung-discovery-retry\n",
    ).replace("versionCode=128\n", "versionCode=129\n")
    if "versionCode=129\n" not in props:
        raise ValueError("Unexpected test19 module version")
    payloads["module.prop"] = props.encode()
    payloads["common/files/JamesDSPManagerZahah.apk"] = app
    payloads["TEST20.md"] = (ROOT / "TEST20.md").read_bytes()

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, data in payloads.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = previous.previous.stable.PAYLOADS.get(
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
