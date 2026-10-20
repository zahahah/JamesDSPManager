#!/usr/bin/env python3
"""Build the v6.9.10-beta-1 ZIP with the current modified ThePBone root APK."""

from hashlib import sha256
import json
import os
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_659_mustang_late_load as base


ROOT = base.ROOT
VERSION = "v6.9.10-beta-1"
VERSION_CODE = 131
APP_PATH = ROOT / "common/files/release/JamesDSPManagerThePBone.apk"
APP_SHA256 = "d696cea84d589310f2b3bde79553e13cbb16940c8906c31b5dd798ba1552ca9a"
OUTPUT = Path(os.environ.get(
    "JDSP_PACKAGE_OUTPUT", ROOT / f"dist/JamesDSPManager-{VERSION}.zip"
))


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("Prerelease cannot overwrite the stable release archive")
    app = APP_PATH.read_bytes()
    if sha256(app).hexdigest() != APP_SHA256:
        raise ValueError("Unexpected modified ThePBone root APK")

    payloads: dict[str, tuple[bytes, int]] = {}
    for name, mode in base.PAYLOADS.items():
        source = APP_PATH if name == "common/files/JamesDSPManagerThePBone.apk" else ROOT / name
        payloads[name] = (source.read_bytes(), mode)

    props = payloads["module.prop"][0].decode()
    props = props.replace("version=v6.5.9\n", f"version={VERSION}\n")
    props = props.replace("versionCode=111\n", f"versionCode={VERSION_CODE}\n")
    if f"version={VERSION}\n" not in props or f"versionCode={VERSION_CODE}\n" not in props:
        raise ValueError("Could not set prerelease module metadata")
    payloads["module.prop"] = (props.encode(), payloads["module.prop"][1])

    update = json.loads(payloads["update.json"][0])
    update.update({
        "version": VERSION,
        "versionCode": VERSION_CODE,
        "zipUrl": f"https://github.com/zahahah/JamesDSPManager/releases/download/{VERSION}/JamesDSPManager-{VERSION}.zip",
        "changelog": f"https://raw.githubusercontent.com/zahahah/JamesDSPManager/{VERSION}/changelog.md",
    })
    payloads["update.json"] = (
        (json.dumps(update, indent=2, ensure_ascii=False) + "\n").encode(),
        payloads["update.json"][1],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, (data, mode) in payloads.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = ZIP_STORED
            archive.writestr(info, data)

    with ZipFile(output) as archive:
        names = archive.namelist()
        if set(names) != set(payloads):
            raise ValueError("Unexpected module payload list")
        if {name for name in names if name.endswith(".apk")} != {
            "common/files/JamesDSPManagerThePBone.apk"
        }:
            raise ValueError("The prerelease must contain only the modified root APK")
        if archive.read("common/files/JamesDSPManagerThePBone.apk") != app:
            raise ValueError("Bundled app differs from the verified APK")
        if f"version={VERSION}" not in archive.read("module.prop").decode():
            raise ValueError("Unexpected module.prop version")
        final_update = json.loads(archive.read("update.json"))
        if final_update["version"] != VERSION or final_update["versionCode"] != VERSION_CODE:
            raise ValueError("Unexpected update metadata")

    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n")
    return digest


if __name__ == "__main__":
    print(f"{OUTPUT.name} SHA-256 {build()}")
