# Global native control v4 — source candidate, not a release

Branches:
- Module / RootJamesDSP: `pixel-test-native-control-v4`.
- LightningDSP: `native/control-completion-v4`, based on global-control v3.

The effect-bound experiment and its v6.5.14 package are retired. This branch
uses the named global `jdsp.control` / `lightning.dsp.IJamesDspControl` service,
matching the ViPER AIDL architecture (whose corresponding service is
`viper.control`). The native contract is still frozen protocol V3: iteration v4
must not be confused with Android Effect AIDL V4 or a claim of Samsung V3 ABI
compatibility.

## Flow and supported controls

RootJamesDSP -> libsu -> /vendor/bin/jdspctl (UID 0, vendor NDK) -> global Binder
service -> selected live DSP context -> bounded audio-boundary update.

Enable, post-gain and prepared FIR use the global service when it is available;
other controls and failures use the legacy fallback. The helper refuses zero or
multiple contexts rather than writing to an arbitrary instance. The app keeps
Android AudioEffect.enabled independent from native DSP enable. Accepted
requests, applied generations, processed frames and audible changes are separate
proofs. No direct app-UID write authorization is promised.

## Module and policy

`native-control.sh prepare` stages a vendor-service-context overlay and the
native helper. Only the module tree is modified. `sepolicy.rule` and
`native-control/global-service.rule` permit the typed service producer. No
ordinary app is granted default-service discovery or HAL writes. Root helper
access still depends on the root manager's policy and must be tested.

Late-load warning: replacing vendor_service_contexts after ServiceManager has
cached its labels does NOT reload that cache. The default typed path may remain
unavailable in a temp-root session. The ViPER release also grants its HAL domain
add permission to default_android_service as a compatibility fallback. That
fallback cannot be restricted to just one service name by SELinux.

For an explicitly authorized test ONLY, marker
`.jdsp-control-default-label-opt-in` makes the preparation script apply
`native-control/default-label-opt-in.rule`. This broadens add/find for
hal_audio_default, not app authorization; the native service still rejects
non-root writes. It is OFF by default. Do not enable it silently, disable
SELinux, restart ServiceManager, or assume a new file means a live label changed.
The real producer/root SELinux domains must also be verified on each device.

There are no automatic Audio HAL/audioserver restarts, including late-load.
Dependency checks use the actual compiled interface versions, never SONAME
rewrites or linker-failure bypasses. A real Effect V3 build can be packaged for a
V3 device; a V4 build cannot become compatible by renaming a dependency.

## Compilation and distribution gate

The tracked native-v3 driver is a HISTORICAL BASELINE, not the v4 artifact.
`native-control/v4-candidate.json` remains `awaiting-native-build` until BOTH
new libjamesdspaidl.so and jdspctl are compiled from the exact v4 commit. Import
provenance with matching hashes, sizes and DT_NEEDED reports for both. A new
owner-signed `james.dsp` 1.6.15 / versionCode 58 app must also be verified.

`python3 tools/package_native_control_v4.py` refuses to create a ZIP without
these prerequisites, and explicitly rejects the former v3/effect-bound hashes.
The Actions workflow can validate source while waiting; it must not advertise
a nonexistent module release. See LightningDSP/GLOBAL-CONTROL-V4-BUILD.md for
compiler instructions and mandatory host/kernel Binder tests.

## Import the compiler output and create the test ZIP

The signed root APK 1.6.15 / code 58 is already included. Keep `update.json`
pointing at the existing release until a new prerelease actually exists.
Check out `pixel-test-native-control-v4`; use the exact native commit pinned in
`native-control/v4-candidate.json` (currently `9aaaeea63f7470f462df4035a76f441a2e8d4768`).
The compiler must return BOTH the driver and `jdspctl`, plus the provenance shape
documented in `LightningDSP/GLOBAL-CONTROL-V4-BUILD.md`.

```sh
export ANDROID_HOME="$HOME/Documents/Android/SDK" # use your actual SDK path
export JDSP_READELF="/path/to/android-ndk/toolchains/llvm/prebuilt/host/bin/llvm-readelf"
python3 tools/import_native_control_v4.py --driver /path/libjamesdspaidl.so --helper /path/jdspctl --provenance /path/provenance.json
python3 -m unittest discover -s tests -v
for file in *.sh common/*.sh; do sh -n "$file" || exit 1; done
python3 tools/package_native_control_v4.py
```

The importer never executes the supplied binaries. It verifies the pinned
source, SHA-256, ELF64 AArch64, actual dependencies, library SONAME/NODELETE,
factory exports and the existing APK signer/package/version before changing the
candidate. Only allowlisted provenance is copied publicly; private host paths
and full build logs stay outside this repository. A rejected import leaves the
tracked candidate unchanged. Success promotes `module.prop` to the test version
and enables Actions packaging; it does NOT install, publish or validate audio.
The ZIP will be `dist/JamesDSPManager-v6.5.15-native-control-v4-test.zip`, with
matching checksum and manifest. Review the diff, commit as lightning zahah and
then publish a clearly experimental prerelease. Device tests below remain
mandatory; never advertise host test success as Samsung compatibility.

## Device verification after the new artifacts exist

1. Verify exact library/helper/APK hashes and signer; update in place only.
2. Confirm library mapped in the audio HAL, then jdsp.control registered.
3. As root run `/vendor/bin/jdspctl probe` and `/vendor/bin/jdspctl status`.
4. With playback running, verify app logs native accepted/applied generations,
   increasing processed frames, and AudioFlinger Enabled=y.
5. Make a safe, obvious gain/EQ cut and confirm audible change in real time.
6. Verify fallback, app reopen and non-root rejection. Samsung factory discovery
   and ABI compatibility remain independent prerequisites.

No Pixel/Samsung device or audio-service change has been performed for this
source branch. A successful host test/build alone is not device validation.
