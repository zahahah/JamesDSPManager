#!/usr/bin/env python3
"""Package an isolated Samsung test: eager real-DSO load + guarded refresh."""

from hashlib import sha256
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_659_mustang_late_load as stable
import package_test17 as previous


ROOT = stable.ROOT
OUTPUT = Path(os.environ.get(
    "JDSP_TEST18_PACKAGE_OUTPUT",
    ROOT / "dist/JamesDSPManager-v6.5.9-test18-samsung-viper-method.zip",
))


def build(output: Path = OUTPUT) -> str:
    if output.resolve() == (ROOT / "dist/JamesDSPManager-v6.5.9.zip").resolve():
        raise ValueError("Experimental package cannot overwrite the stable release")

    with TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "test17.zip"
        eager_wrapper = Path(tmp) / "libjamesdsp_pinwrap.so"
        previous.build(baseline)
        subprocess.run(
            ["sh", str(ROOT / "native/build_jdsp_aidl_eager_pinwrap.sh"),
             str(eager_wrapper)],
            check=True,
        )
        with ZipFile(baseline) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()
                        if name != "update.json"}

        props = payloads["module.prop"].decode()
        props = props.replace(
            "version=v6.5.9-test17-samsung-early-log\n",
            "version=v6.5.9-test18-samsung-viper-method\n",
        ).replace("versionCode=126\n", "versionCode=127\n")
        if "versionCode=127\n" not in props:
            raise ValueError("Unexpected test17 module version")
        payloads["module.prop"] = props.encode()
        payloads["audio-reload.sh"] = (ROOT / "audio-reload.sh").read_bytes()
        payloads["patch.sh"] = (ROOT / "patch.sh").read_bytes()
        payloads["tools/libjamesdsp_pinwrap.so"] = eager_wrapper.read_bytes()
        payloads[".test18-samsung-viper-refresh"] = b"test-only; one-shot guarded audio HAL refresh\n"
        payloads[".test18-samsung-ndk-retarget"] = b"test-only opt-in for the validated linker adaptation\n"
        payloads["TEST18.md"] = (ROOT / "TEST18.md").read_bytes()

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, data in payloads.items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = stable.PAYLOADS.get(name, 0o100755 if name.endswith(".sh") else 0o100644)
            info.external_attr = mode << 16
            archive.writestr(info, data)

    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n"
    )
    return digest


if __name__ == "__main__":
    print(f"{OUTPUT.name} SHA-256 {build()}")
