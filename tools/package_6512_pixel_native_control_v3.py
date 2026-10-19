#!/usr/bin/env python3
"""Build the guarded Pixel native-control-v3 test ZIP reproducibly."""

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_6510_pixel_aidl as previous

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "3ea15a5bae87bdbe17f39d5a161c002b655fe3d8"
VERSION = "v6.5.12-pixel-native-control-v3-test"
VERSION_CODE = 116
DRIVER = "common/files/aidl/libjamesdsp.so"
DRIVER_SHA256 = "266909b6aaf9a81648538369a2671d3f79d47d1f0ea02b56b21cf6cfc1df54ce"
OUTPUT = Path(os.environ.get(
    "JDSP_PACKAGE_OUTPUT",
    ROOT / f"dist/JamesDSPManager-{VERSION}.zip",
))
NEW_FILES = {
    "NATIVE-CONTROL.md": 0o100644,
    "native-control/provenance.json": 0o100644,
    "native-control/LightningDSP-Main-LICENSE.txt": 0o100644,
}
CHANGED_FILES = {
    ".github/workflows/pixel-test-native-control-v3.yml",
    "NATIVE-CONTROL.md",
    "README.md",
    "changelog.md",
    "common/functions.sh",
    DRIVER,
    "module.prop",
    "native-control/LightningDSP-Main-LICENSE.txt",
    "native-control/provenance.json",
    "patch.sh",
    "post-fs-data.sh",
    "service.sh",
    "tests/test_late_load.py",
    "tests/test_native_control_patch.py",
    "tests/test_pixel_native_control_package.py",
    "tools/package_6512_pixel_native_control_v3.py",
    "update.json",
}
PAYLOADS = dict(previous.PAYLOADS)
PAYLOADS.pop("audio-reload.sh", None)
PAYLOADS.update(NEW_FILES)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_worktree() -> None:
    branch = git("branch", "--show-current")
    if branch != "pixel-test-new-aidl":
        raise ValueError(f"Build is restricted to pixel-test-new-aidl, got {branch!r}")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    changed = set(git("diff", "--name-only", BASELINE, "--").splitlines())
    if changed != CHANGED_FILES:
        raise ValueError(
            "Unexpected tracked source changes relative to the Pixel baseline: "
            f"missing={sorted(CHANGED_FILES - changed)}, extra={sorted(changed - CHANGED_FILES)}"
        )
    for name in CHANGED_FILES:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(ROOT / name)
    for name in NEW_FILES:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(ROOT / name)


def verify_payloads() -> None:
    for name, mode in previous.PAYLOADS.items():
        if name == "audio-reload.sh":
            continue
        current = (ROOT / name).read_bytes()
        baseline = subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT)
        if name in CHANGED_FILES:
            if current == baseline:
                raise ValueError(f"Expected test-candidate change missing: {name}")
        elif current != baseline:
            raise ValueError(f"Unapproved module payload change relative to baseline: {name}")

    driver = (ROOT / DRIVER).read_bytes()
    if sha256(driver).hexdigest() != DRIVER_SHA256:
        raise ValueError("AIDL driver does not match the pinned native-control-v3 artifact")
    if not driver.startswith(b"\x7fELF") or driver[4] != 2 or driver[5] != 1:
        raise ValueError("AIDL driver must be a little-endian ELF64 shared object")
    provenance = json.loads((ROOT / "native-control/provenance.json").read_text(encoding="utf-8"))
    artifact = provenance["artifact"]
    if artifact["sha256"] != DRIVER_SHA256 or artifact["size_bytes"] != len(driver):
        raise ValueError("Artifact provenance does not match the packaged AIDL driver")
    required_deps = {
        "android.hardware.audio.effect-V4-ndk.so",
        "android.media.audio.common.types-V5-ndk.so",
        "android.hardware.common-V2-ndk.so",
        "android.hardware.common.fmq-V1-ndk.so",
    }
    if not required_deps.issubset(set(provenance["direct_dt_needed"])):
        raise ValueError("Provenance is missing one or more pinned AIDL dependencies")
    if not (ROOT / "native-control/LightningDSP-Main-LICENSE.txt").read_text(encoding="utf-8").strip():
        raise ValueError("Missing upstream license text")

    for name, expected in previous.SIGNED_APK_HASHES.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"APK payload differs from the established Pixel test build: {name}")

    service = (ROOT / "service.sh").read_text(encoding="utf-8")
    late_load_branch = service.split('if [ "${KSU_LATE_LOAD:-0}"', 1)[1].split("fi", 1)[0]
    if "audio-reload.sh" in late_load_branch or "killall" in late_load_branch:
        raise ValueError("Late-load service must not restart audio services")
    if "restart=not_requested" not in late_load_branch:
        raise ValueError("Late-load service must explicitly report restart disabled")

    installer = (ROOT / "common/functions.sh").read_text(encoding="utf-8")
    permission_reset = installer.index("set_perm_recursive $MODPATH 0 0 0755 0644")
    permission_finalize = installer.index("set_permissions", permission_reset)
    patchelf_restore = installer.index('chmod 0755 "$MODPATH/tools/patchelf"', permission_finalize)
    if not permission_reset < permission_finalize < patchelf_restore:
        raise ValueError("Installer must restore patchelf executable mode after permission normalization")


def write_zip(output: Path) -> None:
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


def build(output: Path = OUTPUT) -> str:
    verify_worktree()
    verify_payloads()
    write_zip(output)

    with ZipFile(output) as archive:
        names = archive.namelist()
        if set(names) != set(PAYLOADS) or len(names) != len(set(names)):
            raise ValueError("Unexpected or duplicate ZIP payload paths")
        if "audio-reload.sh" in names:
            raise ValueError("Audio restart helper must not be included in this test ZIP")
        patchelf_mode = archive.getinfo("tools/patchelf").external_attr >> 16
        if patchelf_mode & 0o777 != 0o755:
            raise ValueError("Packaged patchelf must be executable")
        if {name for name in names if name.endswith(".apk")} != set(previous.SIGNED_APK_HASHES):
            raise ValueError("Unexpected APK set")
        if archive.read(DRIVER) != (ROOT / DRIVER).read_bytes():
            raise ValueError("Packaged AIDL driver differs from the pinned source")
        props = archive.read("module.prop").decode("utf-8")
        update = json.loads(archive.read("update.json"))
        if f"version={VERSION}" not in props or f"versionCode={VERSION_CODE}" not in props:
            raise ValueError("Unexpected module version metadata")
        if update.get("version") != VERSION or update.get("versionCode") != VERSION_CODE:
            raise ValueError("Unexpected update metadata")
        if any("rootless" in name.lower() for name in names):
            raise ValueError("Rootless APKs must not be included in this root-only ZIP")
    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    sidecar = {
        "file": output.name,
        "sha256": digest,
        "version": VERSION,
        "versionCode": VERSION_CODE,
        "driverSha256": DRIVER_SHA256,
        "branch": "pixel-test-new-aidl",
        "deviceScope": "Google Pixel 10 Pro XL (mustang), API 36+; not device-validated",
        "audioServiceRestart": "disabled",
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return digest


def main() -> None:
    print(f"{OUTPUT.name} SHA-256 {build()}")


if __name__ == "__main__":
    main()
