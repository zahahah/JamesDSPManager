# Native control v3 module candidate

This ZIP replaces the AIDL implementation library only. The Android module
loader still sees the expected path `libjamesdsp.so`; the packaged ELF's SONAME
is `libjamesdspaidl.so`. The existing implementation UUID and effect type stay
unchanged, so the intended effect path remains Android `IFactory/default` ->
`IEffect`/FMQ -> the library's existing DSP context.

## What the new binary adds

The library adds a versioned Binder control/status interface:

- Binder service: `jdsp.control`
- Descriptor: `lightning.dsp.IJamesDspControl`
- Protocol: versioned native control v1
- Initial control surface: context/status queries, enable, post-gain, and FIR EQ
- Controls target actual live effect contexts; stale/invalid targets are
  rejected by the native implementation.
- Writes are authorized to UID 0 by default. The app UID has not been granted
  write access.
- RootJamesDSP branch `pixel-test-new-aidl` includes an experimental client and
  the matching root APK is bundled in this ZIP. It discovers the service,
  negotiates protocol/capabilities, and attempts writes only if the provider
  explicitly reports direct app authorization and a single live context.

This does not grant app-UID write access, and the app UI's EQ controls are not
yet mapped to the new endpoint. With the current root-only provider policy, the
client should preserve the legacy `AudioEffect` path. It does not replace that
path with a parallel DSP engine.

## ABI and device scope

The pinned library was built for Android 16 ARM64 and directly needs:

- `android.hardware.audio.effect-V4-ndk.so`
- `android.media.audio.common.types-V5-ndk.so`
- `android.hardware.common-V2-ndk.so`
- `android.hardware.common.fmq-V1-ndk.so`

There is no SDK or device-model gate in the test module. An experimental
cross-ABI probe allows the systemless overlay attempt to proceed when expected
AIDL V4 dependencies are missing or linker preflight fails. The binary still
has those direct dependencies; removing the gate does not make it compatible
with an AIDL V3 factory. The module logs mismatch and never changes `DT_NEEDED`
or SONAMEs. A `lib=experimental_link_check_bypassed` status means the library
was not resolved by preflight and must not be treated as loaded.

## Do not over-interpret status

An installed/mounted library, `service check jdsp.control`, or a visible effect
descriptor is not proof of a working Binder descriptor, authorization,
successful effect creation, audio frames traversing the DSP, or audible EQ
changes. This candidate has not been tested on a device. It does not alter
SELinux policy and late-load does not restart Audio HAL or audioserver.

For a future manual test, collect evidence in separate steps:

1. Confirm the module's driver SHA-256 equals the hash recorded in
   `native-control/provenance.json`.
2. Check whether `jdsp.control` is visible after an app/audio session causes the
   HAL to query or create the effect. A service lookup alone is only discovery
   evidence.
3. Query the interface descriptor and protocol/capabilities with a client
   generated from the matching AIDL contract. Do not use guessed raw Binder
   transaction numbers.
4. Verify authorized versus unauthorized writes. The production default only
   authorizes UID 0; don't grant broader access or add SELinux rules for this
   candidate.
5. Verify live-context telemetry and measured/audible gain or FIR changes while
   checking that the legacy `AudioEffect` path and app behavior remain intact.

Do not restart audio services from a module script. If the existing HAL has
already cached its effect factory, stop and report that limitation instead of
adding an automatic restart or an ABI rename.

## Provenance and license

The binary SHA-256 is
`266909b6aaf9a81648538369a2671d3f79d47d1f0ea02b56b21cf6cfc1df54ce`. Its
original build record is included in `native-control/provenance.json`; that
record identifies the LightningDSP source commit used at build time and an
Android 16 `mini_arm64-userdebug` Soong build. LightningDSP history was later
rewritten to correct the GitHub author identity without changing source trees;
the corresponding current source branch is
[`native/control-completion-v3`](https://github.com/zahahah/LightningDSP/tree/native/control-completion-v3).
The original `Main/LICENSE` GPL-2.0 text is included at
`native-control/LightningDSP-Main-LICENSE.txt`.

The recorded native host tests do not establish Android ServiceManager/SELinux
access, AIDL factory discovery, Pixel hardware compatibility, or real-device
audio processing. No device install or restart is performed by the package
builder.
