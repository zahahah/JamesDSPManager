# Pixel effect-bound-control-v1 module test — experimental

Candidate: `v6.5.14-effect-bound-control-v1-test`, module versionCode 118.
Target branch: `pixel-test-new-aidl`.

The ZIP replaces only the AIDL driver payload relative to the immediately
preceding test candidate; the existing root APK payload is retained unchanged
(JamesDSP 1.6.15, versionCode 57). The driver is ARM64, built from LightningDSP
`native/effect-bound-control-v1` commit
`bbc9bcee2f402c4ced87c10e64dfdf29a5fc5cfb`, and its SHA-256 is
`cf6e202262dd7925c1245670f3e3e7aa5aacf321fdf8f71ad0378e6e81b33e4a`.

The library directly depends on Audio Effect AIDL V4, media common types V5,
hardware common V2 and common FMQ V1. The pre-mount dependency validation is
strict: if its exact dependencies cannot be resolved, the module marks
`skip_mount` and does not mount the candidate. This is not a V3 compatibility
build. Even if dependency files exist, that alone does not prove the HAL factory
implements a compatible interface.

## Test status and limits

This exact artifact has NOT been installed or runtime-tested. Previous Pixel
results were for another library build and do not validate this one. The
bundled APK has not been updated to encode/send the effect-bound protocol, so
this ZIP cannot verify new protocol control writes. It is an experimental
library A/B package only; no audible-processing or Samsung compatibility claim
is made.

Keep the known-good module ZIP and a tested temp-root recovery path available.
Do not install this candidate on Samsung AIDL V3 based on the current evidence.
No Android service restart is performed by the module. Never uninstall or clear
app data to resolve signature/version issues. Device installation or restarting
services must be separately authorized.

## Reproduce

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
for f in *.sh common/*.sh; do sh -n "$f" || exit 1; done
python3 tools/package_6511_pixel_native_control_v3.py
```

The reproducible ZIP and sidecars are written under `dist/`.
