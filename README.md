# JamesDSP Manager v6.6-beta-1

Current branch: `pixel-test-new-aidl`. Global `jdsp.control` is the primary
backend for the library's native enable, post-gain and FIR controls; legacy
controls remain available for fallback and features outside that contract.
The root app is v1.6.17, versionCode 60. The v4 native library and `jdspctl`
are unchanged; no new native compilation is required.

The boot service waits for the service-label overlay to be visible to
ServiceManager, then reapplies only the dedicated typed rules. AOSP refreshes
its label handle after a SELinux policy-status update; merely staging the
file before mounting it is insufficient. This does not restart audio or
ServiceManager, disable SELinux, or enable generic default-service grants.
The status log records `READY` only after the real native helper reports a
published, protocol-3 service with one writable context. It does not infer
native readiness from a legacy AudioFlinger effect.

The existing library bounds publication retries per HAL process. A process that
has already exhausted its retries may require a normal user-initiated reboot
after installing the fixed module; this module never restarts audio for it.

Reference: [AOSP ServiceManager label-handle refresh](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/cmds/servicemanager/Access.cpp).
See [NATIVE-CONTROL.md](NATIVE-CONTROL.md) for the native contract and policy
boundaries. The sections below describe historical builds.

---

# JamesDSPManager

Root-only module for JamesDSPManager for Android 16 and 17, works on Traditional and Temp root. Upstream project: [JamesDSPManager](https://github.com/therealahrion/JamesDSPManager). App source: [James34602/JamesDSPManager](https://github.com/james34602/JamesDSPManager).

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

The module offers only the ThePBone root APK (package `james.dsp`, versionName
1.6.15, versionCode 58) with the experimental global-control client. The
installer no longer offers the classic UI APK. It first asks Package Manager to
update an existing app in place; only an explicit signer-mismatch response
starts a replacement prompt.

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

For a signer mismatch, **Volume Down** confirms uninstall/replacement, while
**Volume Up** or no response within 10 seconds keeps the installed app and its
data. Before an explicitly confirmed uninstall, the installer attempts a
private temporary archive of app-private and package-specific external data;
it restores the archive after installation and reapplies ownership/SELinux
labels. If backup fails, it warns and proceeds only because the user already
confirmed. Android Keystore-protected secrets may not survive a signer change.
If Package Manager is unavailable during flashing, first install is deferred
to the boot service; that service will not prompt for or uninstall an existing
app.

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

Removing the module never removes the installed `james.dsp` app. A module
signer migration is opt-in: Volume Down confirms replacement, and Volume Up or
timeout keeps the installed app. A temporary data backup is attempted only
after explicit confirmation; it is not a guarantee that Keystore-bound secrets
can be transferred between signing identities.

## Build and test

Run the host tests and build the release ZIP with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/package_6511_pixel_native_control_v3.py  # build this Pixel prerelease
python3 tools/package_659_mustang_late_load.py  # rebuild stable v6.5.9
```

For the previous release notes, see [changelog.md](changelog.md).
