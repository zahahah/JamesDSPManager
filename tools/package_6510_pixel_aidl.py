#!/usr/bin/env python3
"""Build the Pixel regular-boot AIDL prerelease ZIP."""

from hashlib import sha256
import os
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_659_mustang_late_load as stable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get(
    "JDSP_PACKAGE_OUTPUT",
    ROOT / "dist/JamesDSPManager-v6.5.10-pixel-builtin-aidl-beta.1.zip",
))
VERSION = "v6.5.10-pixel-builtin-aidl-beta.1"
VERSION_CODE = 112
ROOT_APK = "common/files/JamesDSPManagerThePBone.apk"
ROOT_APK_SHA256 = "70aa92562017856777a9a616ec8b55e8354f0dee093812df53fe2404dd9c24f9"
PAYLOADS = dict(stable.PAYLOADS)
SIGNED_APK_HASHES = dict(stable.SIGNED_APK_HASHES)
SIGNED_APK_HASHES[ROOT_APK] = ROOT_APK_SHA256


def build(output: Path = OUTPUT) -> str:
    for name, expected in SIGNED_APK_HASHES.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Unexpected APK payload: {name}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, mode in PAYLOADS.items():
            source = ROOT / name
            if not source.is_file():
                raise FileNotFoundError(source)
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = ZIP_STORED
            archive.writestr(info, source.read_bytes())

    with ZipFile(output) as archive:
        names = archive.namelist()
        if set(names) != set(PAYLOADS):
            raise ValueError("Unexpected module payload list")
        if {name for name in names if name.endswith(".apk")} != stable.ROOT_APKS:
            raise ValueError("Unexpected APK set")
        if any("rootless" in name.lower() for name in names):
            raise ValueError("Rootless APKs must not be included in this root-only ZIP")
        props = archive.read("module.prop").decode("utf-8")
        if f"version={VERSION}" not in props or f"versionCode={VERSION_CODE}" not in props:
            raise ValueError("Unexpected module version")
        update = archive.read("update.json").decode("utf-8")
        if f'"version": "{VERSION}"' not in update or f'"versionCode": {VERSION_CODE}' not in update:
            raise ValueError("Unexpected update metadata")
        if "KSU_LATE_LOAD" not in archive.read("post-fs-data.sh").decode("utf-8"):
            raise ValueError("Missing regular and late-load boot handling")

    return sha256(output.read_bytes()).hexdigest()


def main() -> None:
    print(f"{OUTPUT.name} SHA-256 {build()}")


if __name__ == "__main__":
    main()
