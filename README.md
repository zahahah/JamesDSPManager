# JamesDSPManager

Root-only module for JamesDSPManager. Upstream project: [JamesDSPManager](https://github.com/therealahrion/JamesDSPManager). App source: [James34602/JamesDSPManager](https://github.com/james34602/JamesDSPManager).

## AIDL native-control-v3 test build: v6.5.11-pixel-native-control-v3-test

This is a device-test candidate that replaces the AIDL driver with the
Android-built `libjamesdspaidl.so` from LightningDSP native control v3. The
module installs it under Android's expected filename, `libjamesdsp.so`, and
keeps the existing effect UUID/type and XML factory path. The driver SHA-256 is
`266909b6aaf9a81648538369a2671d3f79d47d1f0ea02b56b21cf6cfc1df54ce`.

The new library contains a versioned `jdsp.control` Binder endpoint
(`lightning.dsp.IJamesDspControl`) for protocol/status and a limited initial
set of same-context controls (enable, post-gain, FIR EQ). The native default
write authorization is root UID only. This module does not include a client
implementation in JamesDSPManager or RootJamesDSP; the app UI therefore does
not yet send these Binder controls. Existing `AudioEffect` operation remains
the fallback. Service registration, Pixel ABI compatibility, descriptor
discovery, effect creation, audio processing, and audible control changes are
all unverified with this candidate.

The binary was built against Android audio-effect AIDL V4, media common types
V5, hardware common V2, and common FMQ V1. This candidate requires Android API
36 or newer, but has no device-model restriction. It also includes an explicit
experimental cross-ABI probe mode: missing AIDL dependencies or a failed linker
preflight are logged but do not block the overlay, so devices exposing AIDL V3
can be tested. The ELF dependency names are never rewritten. This is a test
attempt, not evidence that an AIDL V3 device can load the library or process
audio; a device may simply reject the effect.

Late-load does not restart Audio HAL or audioserver. A ready mount/config status
is not evidence that `jdsp.control` registered or that audio is processed. See
[`NATIVE-CONTROL.md`](NATIVE-CONTROL.md) for limitations and manual evidence
needed before making a functional claim. The exact binary provenance and the
LightningDSP GPL-2.0 license text are included in `native-control/`.

The module package retains the existing app APK payload unchanged. No app-side
control client is included in this module candidate.

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
python3 tools/package_6511_pixel_native_control_v3.py  # build this Pixel prerelease
python3 tools/package_659_mustang_late_load.py  # rebuild stable v6.5.9
```

For the previous release notes, see [changelog.md](changelog.md).
