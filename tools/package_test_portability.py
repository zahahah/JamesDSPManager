#!/usr/bin/env python3
"""Package the isolated late-load experiment without touching stable artifacts."""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo
import package_659_mustang_late_load as stable

ROOT = stable.ROOT
OUTPUT = Path(os.environ.get("JDSP_TEST_PACKAGE_OUTPUT", ROOT / "dist/JamesDSPManager-v6.5.9-test3-portability.zip"))


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("The experimental builder cannot overwrite the stable release")
    with TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "baseline.zip"
        stable.build(baseline)
        with ZipFile(baseline) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist() if name != "update.json"}
    props = payloads["module.prop"].decode()
    props = props.replace("version=v6.5.9\n", "version=v6.5.9-test3-portability\n")
    props = props.replace("versionCode=111\n", "versionCode=113\n")
    props = props.replace("name=JamesDSP Manager\n", "name=JamesDSP Manager (portability test)\n")
    props = props.replace("description=Root-only JamesDSP module for built-in and KernelSU late-load, with a guarded audio refresh", "description=Experimental late-load portability; unknown firmware never triggers an automatic audio restart")
    payloads["module.prop"] = props.encode()
    payloads["README.md"] = (b"> Experimental portability build. Read EXPERIMENTAL.md first.\n> Stable-release validation below does not validate this test ZIP.\n\n" + payloads["README.md"])
    payloads["EXPERIMENTAL.md"] = (ROOT / "EXPERIMENTAL.md").read_bytes()
    helper = ROOT / "late-load-common.sh"
    if helper.is_file():
        payloads[helper.name] = helper.read_bytes()
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
