# Global native-control v4 development branch

This is a source candidate, not an installable v4 release. The effect-bound
experiment is retired. See [NATIVE-CONTROL.md](NATIVE-CONTROL.md) for the global
`jdsp.control` architecture, compilation gate, policy limits and verification.

---

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
set of same-context controls (enable, post-gain, FIR EQ). The bundled root APK
is built from RootJamesDSP branch `pixel-test-new-aidl` (source commit
`53134a2`), with versionName 1.6.15 and versionCode 57. It includes an
experimental AIDL client that probes protocol/capabilities and only attempts
writes when the provider explicitly authorizes direct app access. The provider
currently authorizes UID 0 by default, so this app build is expected to retain
the legacy `AudioEffect` path; this package does not establish app-UID write
access or map the UI EQ controls to the new service. Service registration,
Pixel ABI compatibility, descriptor discovery, effect creation, audio
processing, and audible native-control changes remain unverified.

The binary was built against Android audio-effect AIDL V4, media common types
V5, hardware common V2, and common FMQ V1. There is no Android SDK or device-
model gate in this test module. An experimental cross-ABI probe logs missing
AIDL dependencies or a failed linker preflight without blocking the systemless
overlay, allowing lower-API/AIDL V3 devices to be tested. The ELF dependency
names are never rewritten. Removing the gate does not make the artifact
compatible: a device may fail to load the library or reject the effect, and
no AIDL V3 processing is claimed.

Late-load does not restart Audio HAL or audioserver. A ready mount/config status
is not evidence that `jdsp.control` registered or that audio is processed. See
[`NATIVE-CONTROL.md`](NATIVE-CONTROL.md) for limitations and manual evidence
needed before making a functional claim. The exact binary provenance and the
LightningDSP GPL-2.0 license text are included in `native-control/`.

The module replaces the previous root APK payload with the signed experimental
client build (package `james.dsp`, versionName 1.6.15, versionCode 57). The APK
uses the authorized maintainer certificate and is included at the module's
legacy `JamesDSPManagerThePBone.apk` payload path so the existing installer can
update versionCode 56 in place while preserving app data. The source branch and
commit are recorded above; this is a test build, not a claim of verified DSP
control.

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
