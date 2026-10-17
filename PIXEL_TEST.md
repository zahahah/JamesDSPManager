# Pixel rebuilt AIDL comparison — experimental

Base: stable module master d60a800161ed6fcb6c01aa3026069dffff54bf7a (v6.5.9 / 111).
This branch is NOT based on the Samsung experiments.

The packaged ZIP differs from that base in exactly two entries:

- `common/files/aidl/libjamesdsp.so`: user-supplied ARM64 rebuild, unchanged bytes.
  SHA-256: 8a774733621c4b5f34b3dafef27ab3f5b02fdf7c6cf97bbef9af3535cea66955.
  Native source revision/build manifest has not been supplied; no provenance or
  runtime-equivalence claim is made.
- `common/files/JamesDSPManagerThePBone.apk`: ROOT flavor (`james.dsp`) from
  RootJamesDSP pixel-test 1529b67b90acd786a0368fa4f8c01f04cbb904ba,
  successful GitHub Actions run 38926545942, universal preview artifact.
  Re-signed locally using the authorized owner certificate; no source edits.
  Version 1.6.14-1 / 51, NOT upstream ThePBone 1.6.15. The legacy payload filename
  is retained solely to preserve installer behavior. Select ThePBone to stage it.

The other Original APK remains unchanged. No Rootless APK is included.
No script, XML, SELinux rule, module version, or update metadata changes are
included. Existing stable installer/late-load behavior (including guarded audio
refresh and dependency-name patching) is inherited, not newly introduced.
Do not mistake an unchanged versionCode for the old driver: verify hashes.

## Reproduce locally

Run `python3 tools/package_pixel_test.py`. It compares every module payload
against the fixed base commit and rejects any changes outside the two pinned
replacements. The old stable packager deliberately retains its old APK hash
pin; use the Pixel packager, not the stable one, on this branch.
The ZIP, SHA-256 and provenance JSON are written to dist/. Documentation,
packaging tools and tests are not device payloads.

## Device test boundaries

This package has NOT been installed or runtime-tested by the agent. Preliminary
read-only checks on the connected Pixel 10 Pro XL (Android 17 / SDK 37) found
Audio Effect V4, Common Types V5 and libaudio_aidl_conversion_common_ndk.so
under /system/lib64. Presence is not proof of HAL namespace/ABI/SELinux access.

Keep the known-good module ZIP and a tested temp-root recovery path available.
Do not deploy to Samsung based on a Pixel result. Existing james.dsp apps are
not automatically replaced by the module service; selecting the app at module
install does not prove the running APK changed. Never uninstall or clear app
data to resolve a signature/version mismatch. Any app/device install and
service restart must be separately authorized. For a driver-only A/B test,
keep the running APK unchanged for the first comparison, then test the supplied
Pixel APK separately. Audible FIR/EQ response is required; Binder registration
or an enabled UI alone is insufficient evidence of processing.
