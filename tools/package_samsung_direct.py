#!/usr/bin/env python3
"""Package an explicitly built direct AIDL driver; never build/guess a driver."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import ZIP_STORED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist/JamesDSPManager-v6.5.9-test21-samsung-direct-driver-base.zip"
EXPORTS = {"queryEffect", "createEffect", "destroyEffect"}


def inspect_driver(driver: Path, tool: str) -> tuple[str, list[str], list[str]]:
    result = subprocess.run([tool, "--file-header", "--dynamic", "--dyn-syms", str(driver)],
                            capture_output=True, text=True, check=True, timeout=60)
    report = result.stdout
    if not re.search(r"Class:\s+ELF64\b", report) or not re.search(r"Machine:\s+AArch64\b", report):
        raise ValueError("Driver must be an ELF64 Android ARM64 library")
    if not re.search(r"Type:\s+DYN\b", report):
        raise ValueError("Driver must be a shared object")
    needed = sorted(set(re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", report)))
    if not needed or any(name.startswith(("libc.so.", "libpthread.so.", "ld-linux")) for name in needed):
        raise ValueError("Expected Android/Bionic dependencies, not a Linux desktop library")
    exports = set()
    for line in report.splitlines():
        fields = line.split()
        if (len(fields) >= 8 and fields[3] == "FUNC" and fields[4] in ("GLOBAL", "WEAK")
                and fields[5] in ("DEFAULT", "PROTECTED") and fields[6] != "UND"):
            exports.add(fields[7].split("@")[0])
    if not EXPORTS <= exports:
        raise ValueError("Missing AIDL factory exports: " + ", ".join(sorted(EXPORTS - exports)))
    return report, needed, sorted(exports)


def build(driver: Path, digest: str, revision: str, notices: Path, readelf: str, output: Path) -> str:
    if output.resolve() in (driver.resolve(), notices.resolve()) or output.suffix != ".zip":
        raise ValueError("Output must be a separate ZIP file")
    if output.resolve().parent == (ROOT / "dist").resolve() and output.name != DEFAULT_OUTPUT.name:
        raise ValueError("Use the direct-driver candidate name, never another release's path")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("An explicit SHA-256 digest is required")
    if not re.fullmatch(r"[0-9a-f]{7,40}", revision):
        raise ValueError("Record the actual source Git revision")
    data = driver.read_bytes()
    if not data.startswith(b"\x7fELF") or sha256(data).hexdigest() != digest:
        raise ValueError("Driver ELF magic or SHA-256 mismatch")
    report, needed, exports = inspect_driver(driver, readelf)
    notice_data = notices.read_bytes()
    if not notice_data.strip():
        raise ValueError("Supply the actual source build's license/copyright notices")
    metadata = {
        "sha256": digest,
        "source_revision": revision,
        "provenance_note": "Operator-supplied revision, not verified build provenance",
        "needed": needed,
        "exports": exports,
        "validation_boundary": "ELF/package checks only; processing=unverified; Samsung ABI not validated",
    }
    payloads = {
        "module.prop": (
            "id=ainur_jamesdsp\nname=JamesDSP Samsung direct-driver development base\n"
            "version=v6.5.9-test21-samsung-direct-driver-base\nversionCode=130\n"
            "author=zahahah\n"
            "description=Samsung-only experimental self-mount; no automatic audio restart; processing unverified\n"
        ).encode(),
        "skip_mount": b"",
        "skip_mountify": b"",
        "driver/libjamesdsp.so": data,
        "driver.sha256": (digest + "\n").encode(),
        "driver-build.json": (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode(),
        "driver-readelf.txt": report.encode(),
        "README.md": (ROOT / "samsung/README.md").read_bytes(),
        "NOTICE": notice_data,
    }
    for name in ("runtime.sh", "post-fs-data.sh", "service.sh", "late-load.sh", "customize.sh", "uninstall.sh"):
        payloads[name] = (ROOT / "samsung" / name).read_bytes()
    for name in ("META-INF/com/google/android/update-binary", "META-INF/com/google/android/updater-script"):
        payloads[name] = (ROOT / name).read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        candidate = Path(tmp) / "candidate.zip"
        with ZipFile(candidate, "w", compression=ZIP_STORED) as archive:
            for name, contents in sorted(payloads.items()):
                info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                executable = name.endswith(".sh") or name.endswith("/update-binary")
                info.external_attr = (0o100755 if executable else 0o100644) << 16
                archive.writestr(info, contents)
        package_digest = sha256(candidate.read_bytes()).hexdigest()
        candidate.replace(output)
    output.with_suffix(output.suffix + ".sha256").write_text(f"{package_digest}  {output.name}\n")
    return package_digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--notices", required=True, type=Path)
    parser.add_argument("--readelf", default=shutil.which("llvm-readelf") or shutil.which("readelf"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.readelf:
        parser.error("readelf/llvm-readelf is required; supply --readelf")
    try:
        digest = build(args.driver, args.sha256, args.source_revision, args.notices, args.readelf, args.output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Cannot package driver: {error}\n")
    print(f"{args.output.name} SHA-256 {digest}")


if __name__ == "__main__":
    main()
