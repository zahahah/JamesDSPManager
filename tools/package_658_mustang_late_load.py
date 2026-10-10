#!/usr/bin/env python3
"""Build the JamesDSPManager v6.5.8 module ZIP from tracked module files."""

from hashlib import sha256
import os
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get("JDSP_PACKAGE_OUTPUT", ROOT / "dist/JamesDSPManager-v6.5.8.zip"))
PAYLOADS = {
    "tools/patchelf": 0o100755,
    "post-fs-data.sh": 0o100755,
    "JDSP_banner.png": 0o100644,
    "module.prop": 0o100644,
    "sepolicy.rule": 0o100644,
    "changelog.md": 0o100644,
    "uninstall.sh": 0o100755,
    "jdsp_app.sh": 0o100755,
    "META-INF/com/google/android/update-binary": 0o100755,
    "META-INF/com/google/android/updater-script": 0o100644,
    "README.md": 0o100644,
    "service.sh": 0o100755,
    "common/addon/Volume-Key-Selector/README.md": 0o100644,
    "common/addon/Volume-Key-Selector/install.sh": 0o100644,
    "common/addon/Volume-Key-Selector/tools/arm/keycheck": 0o100755,
    "common/addon/Volume-Key-Selector/tools/x86/keycheck": 0o100755,
    "common/files/JamesDSP/Convolver/CorredHRTFCrossfeed.wav": 0o100644,
    "common/files/JamesDSP/Convolver/CorredHRTF_Surround1.wav": 0o100644,
    "common/files/JamesDSP/Convolver/CorredHRTF_Surround2.wav": 0o100644,
    "common/files/JamesDSP/Convolver/SwapChannels.wav": 0o100644,
    "common/files/JamesDSP/Convolver/binChurch.wav": 0o100644,
    "common/files/JamesDSP/DDC/Butterworth.vdc": 0o100644,
    "common/files/JamesDSP/DDC/mh750.vdc": 0o100644,
    "common/files/JamesDSP/liveprog/autopeakfilter.eel": 0o100644,
    "common/files/JamesDSP/liveprog/dc_remove.eel": 0o100644,
    "common/files/JamesDSP/liveprog/firFilter.eel": 0o100644,
    "common/files/JamesDSP/liveprog/fractionalDelayline.eel": 0o100644,
    "common/files/JamesDSP/liveprog/hadamVerb.eel": 0o100644,
    "common/files/JamesDSP/liveprog/simpleFDNReverb.eel": 0o100644,
    "common/files/JamesDSP/liveprog/stft-filter.eel": 0o100644,
    "common/files/JamesDSP/liveprog/stftCentreCut.eel": 0o100644,
    "common/files/JamesDSP/liveprog/stftPitchShifter.eel": 0o100644,
    "common/files/JamesDSPManager.apk": 0o100644,
    "common/files/JamesDSPManagerThePBone.apk": 0o100644,
    "common/files/aidl/libjamesdsp.so": 0o100644,
    "common/files/arm/libjamesdsp.so": 0o100644,
    "common/files/arm64/libjamesdsp.so": 0o100644,
    "common/files/x86/libjamesdsp.so": 0o100644,
    "common/functions.sh": 0o100644,
    "common/install.sh": 0o100644,
    "patch.sh": 0o100755,
    "late-load.sh": 0o100755,
    "customize.sh": 0o100755,
    "update.json": 0o100644,
    "aml.sh": 0o100755,
    "jdsp_app_handle.sh": 0o100755,
    "audio-reload.sh": 0o100755,
}
ROOT_APKS = {
    "common/files/JamesDSPManager.apk",
    "common/files/JamesDSPManagerThePBone.apk",
}
SIGNED_APK_HASHES = {
    "common/files/JamesDSPManager.apk":
        "ff123bf20047738666443f148e52135bbd398c61a4fa8fde2b53f37c6d8299ca",
    "common/files/JamesDSPManagerThePBone.apk":
        "840f98fa2136588d590d0819d88d5a92f991587e871c3a981c85416ac8ddc67a",
}


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
        if {name for name in names if name.endswith(".apk")} != ROOT_APKS:
            raise ValueError("Unexpected APK set")
        if any("rootless" in name.lower() for name in names):
            raise ValueError("Rootless APKs are not allowed")
        props = archive.read("module.prop").decode("utf-8")
        if "version=v6.5.8" not in props or "versionCode=110" not in props:
            raise ValueError("Unexpected module version")

    return sha256(output.read_bytes()).hexdigest()


def main() -> None:
    print(f"{OUTPUT.name} SHA-256 {build()}")


if __name__ == "__main__":
    main()
