# Effect-bound native control — experimental driver package

This test branch packages the ARM64 library built from LightningDSP commit
`bbc9bcee2f402c4ced87c10e64dfdf29a5fc5cfb` (Android 17 / AOSP
`android-17.0.0_r1`). The source adds a versioned little-endian request protocol
carried through the active `IEffect::setParameterSpecific` vendor-effect
channel. Its parameter ID is `0x4a445343`; supported request operations are
enable, post-gain, and FIR configuration.

The module replaces only `common/files/aidl/libjamesdsp.so`; Android's XML
still references the loader filename `libjamesdsp.so`. Packaged driver SHA-256:
`cf6e202262dd7925c1245670f3e3e7aa5aacf321fdf8f71ad0378e6e81b33e4a`.
See `native-control/provenance.json` and `native-control/BUILD_NOTES.md` for
build metadata.

## What this does not establish

- The bundled app has not yet been updated to encode/send this new protocol.
  The package does not demonstrate app-to-effect control writes.
- This artifact directly depends on Effect AIDL V4, media common types V5,
  hardware common V2 and common FMQ V1. Samsung's reported Effect AIDL V3
  compatibility is unresolved. The package requires the exact V4 dependency set
  and blocks mounting when it is unavailable; this does not establish that the
  target factory itself implements V4.
- The artifact has not been validated on Pixel or Samsung. Host protocol tests
  are not HAL, Binder-policy, or device-audio tests.
- The existing `jdsp.control` registration path is separate; this effect-bound
  protocol avoids relying on its ServiceManager discovery for control, but it
  does not make a HAL discover an effect whose descriptor/factory path is
  missing.

This package is a test candidate only. Keep a known-good recovery route
available. The module does not automatically restart Audio HAL or audioserver.
No SELinux policy is changed. See `PIXEL_TEST.md` for safe manual test scope.
