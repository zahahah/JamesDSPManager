# JamesDSPManager

Root-only module for JamesDSPManager. Upstream project: [JamesDSPManager](https://github.com/therealahrion/JamesDSPManager). App source: [James34602/JamesDSPManager](https://github.com/james34602/JamesDSPManager).

## Pixel test build: v6.5.10-pixel-builtin-aidl-beta.2

This test build prepares the AIDL effect-factory config during the regular
KernelSU boot path, even when `KSU_LATE_LOAD` is unset. The existing late-load
preparation and reload path remains separate and unchanged. Config files are
staged through the module overlay, not written to system partitions.

The ZIP includes the Zahah-signed JamesDSP root app v1.6.15 (version code 56)
with the Volume Manager integration. Its version metadata is aligned with the
bundled 1.6.15 app, but the source snapshot is based on local 1.6.14 code. The
Rootless APK is retained as a repository release artifact only and is not part
of this root-only module ZIP.

The regular-boot AIDL config path and APK migration flow have host-test
coverage, but this beta has not yet been flashed or validated on a device.

At boot, the module tries to install the selected `james.dsp` APK with Android's
normal replace operation. If the existing app has the same signing certificate,
Android updates it in place and preserves its data. If Android rejects the
update because the signer differs, the module posts a notification and waits
30 seconds for a volume-key choice:

- **Volume Up:** remove `james.dsp` for all users, then install the module APK.
  Removing the old app also removes its app data. Back it up first if you need
  its presets or settings.
- **Volume Down or no response:** keep the installed app and copy the new APK to
  `/sdcard/Download/JamesDSPManager.apk`. No response is treated as **No**.

After a No choice or timeout, that same module APK won't ask again on every
boot. A changed module APK triggers a new prompt, and removing the old app lets
the module install the selected APK normally.

## Stable release: v6.5.9

I've tested this release on a Pixel 10 Pro XL (`mustang`) running Android 17,
KernelSU Next, and Magic Mount-rs 4.0.11. The late-load setup stayed working
through several soft reboots. It is stable in this setup, but audio behavior
can vary with firmware and root stage. Please report defects with device/build
details, root mode, logs, and steps to reproduce.

JamesDSP does not depend on PIXAML. Its module provides `libjamesdsp.so` and
adds the effect to the XML used by Android's `IFactory/default`. On my Pixel,
that is enough for the JamesDSP app to load and use the effect on its own.
PIXAML provides a separate AML service (`IFactory/aml`); Android does not
automatically route JamesDSP through it. Some devices or setups may still need
PIXAML for AML-specific compatibility or other AML-based effects, but that is
separate from JamesDSP's basic effect path. Installing PIXAML alone does not
make JamesDSP available.

During KernelSU late-load, repeated preparation callbacks are serialized with a
lock, and the generated XML is replaced atomically before Magic Mount-rs applies
the overlay. The single late-load audio refresh is guarded by the default
factory, the expected stock descriptors, and a marker scoped to the current HAL
process instance. There is no restart loop, `killall`, native hook, or write to
the physical system/vendor partitions. The built-in early-boot path stays
separate.

Removing the module never removes the installed `james.dsp` app. On module
boot, matching-signature APKs are updated in place. Different-signature
migrations require explicit Volume Up confirmation; declining or timing out
keeps the app and stages the APK in Downloads instead of touching app data.
The ThePBone APK remains version 1.6.15, version code 56.

## Build and test

Run the host tests and build the release ZIP with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/package_6510_pixel_aidl.py  # build this Pixel prerelease
python3 tools/package_659_mustang_late_load.py  # rebuild stable v6.5.9
```

For the previous release notes, see [changelog.md](changelog.md).
