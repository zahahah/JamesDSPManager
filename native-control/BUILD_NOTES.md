# Experimental effect-bound-control-v1 ARM64 build

- Source: `zahahah/LightningDSP`, commit `bbc9bcee2f402c4ced87c10e64dfdf29a5fc5cfb`.
- Target: Soong `libjamesdspaidl`, product `mini_arm64-userdebug`, ARM64/AArch64.
- Artifact: `libjamesdspaidl.so`; see `provenance.json` for SHA-256 and complete build metadata.
- The library directly depends on Android Audio Effect AIDL V4. Samsung's observed Effect AIDL V3 compatibility is unresolved.
- This is an experimental build artifact, not a stable release. Android ServiceManager/SELinux and Pixel/Samsung runtime behavior have not been validated with this build.
- The full host test runner stops at `check_audio_boundary.py` because baseline commit `cdb014c` is absent from the local repository objects. The separately rerun control-core, publication-gate, protocol, sanitizer, optimized, and unsafe-fast-math rejection tests passed.
- No app, module, or device changes are included.
