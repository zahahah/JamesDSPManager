# JamesDSPManager

Root-only module for JamesDSPManager. Upstream project: [JamesDSPManager](https://github.com/therealahrion/JamesDSPManager). App source: [James34602/JamesDSPManager](https://github.com/james34602/JamesDSPManager).

## AIDL effect-bound-control-v1 test build: v6.5.14-effect-bound-control-v1-test

This is an experimental ARM64 driver package for testing the new
LightningDSP effect-bound control implementation. It replaces only the AIDL
library payload at `common/files/aidl/libjamesdsp.so`; the module installs it
under Android's expected filename `libjamesdsp.so` while preserving the
existing effect UUID/type and XML factory path.

Driver SHA-256:
`cf6e202262dd7925c1245670f3e3e7aa5aacf321fdf8f71ad0378e6e81b33e4a`.
The source is LightningDSP commit `bbc9bcee2f402c4ced87c10e64dfdf29a5fc5cfb`;
Android 17 / AOSP `android-17.0.0_r1`, ARM64. Full provenance and build notes
are in `native-control/`.

**Important limitations:** this binary directly depends on Android Audio Effect
AIDL V4. The installer now blocks the systemless mount when the exact AIDL
dependencies cannot be resolved; this is not a Samsung AIDL V3 build. The matching effect-bound
control transport is not yet integrated into the bundled APK, and neither
Pixel nor Samsung runtime behavior has been established with this exact
artifact. Treat this as a driver-loading / A-B test candidate, not a working
control release. No Android service restart is performed by late-load.

The bundled APK payload remains the signed root build `james.dsp` 1.6.15,
versionCode 57, unchanged from the preceding test branch. The package builder
checks payload hashes and embeds artifact provenance. See
[`NATIVE-CONTROL.md`](NATIVE-CONTROL.md) and [`PIXEL_TEST.md`](PIXEL_TEST.md)
for test boundaries.

## Prior Pixel test build: v6.5.10-pixel-builtin-aidl-beta.3

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

During module installation, the installer checks the selected APK against the
installed `james.dsp` app. If the signing certificate matches, it installs only
when the bundled APK's `versionCode` is newer, updating in place and preserving
app data. If the certificates differ, the installer asks for a volume-key
choice:

- **Volume Up:** remove `james.dsp` for all users, then install the module APK.
  Removing the old app also removes its app data. Back it up first if you need
  its presets or settings.
- **Volume Down or no response within 30 seconds:** keep the installed app and
  copy the new APK to `/sdcard/Download/JamesDSPManager.apk`. No response is
  treated as **No**.

If package management is unavailable during installation, the boot service
retries the same safe update/migration flow as a fallback. After a No choice,
that same module APK won't ask again on every boot. A changed module APK can
trigger a new prompt.

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
python3 tools/package_6511_pixel_native_control_v3.py  # build the v6.5.14 test prerelease
python3 tools/package_659_mustang_late_load.py  # rebuild stable v6.5.9
```

For the previous release notes, see [changelog.md](changelog.md).
