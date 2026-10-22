# Embedded native control v5 experiment

V5 is the LightningDSP project iteration, not a new Binder protocol. The root
client still uses `jdsp.control`, `lightning.dsp.IJamesDspControl` and protocol 3.
The signed root app remains 1.6.17/code 62. AudioEffect still owns attachment and
lifecycle; only enable, post-gain and prepared FIR use native control.

## What changes

The new native target compiles the AOSP base effect implementation and frozen
NDK audio interfaces/parcelables into the driver. It uses a static C++ runtime and
hides internal implementation symbols. It does not rename versioned dependencies
or make a V4 plugin advertise V3. The first embedded profile is Effect V4 with
media common types V5; vendor factory compatibility remains a target-device
question, not a consequence of embedding alone.

The module keeps the capability-driven late-load mounting and audited firmware
recovery path introduced in v6.6-beta-4-samsung-test2. The dependency check
recognizes the embedded profile: it must not demand audio DSOs that are incorporated into the
new driver. It rejects unexpected runtime dependencies and still checks required
system libraries. The real linker check remains active. Nothing here authorizes
permissive SELinux, broad service grants or repeated recovery attempts.

A five-second settings screen is not proof that audio was processed. Factory
registration, an authorized writable context, applied generations, increasing
frames and audible/measured output remain distinct checks. The earlier
v6.6-beta-4-samsung-test2 failure was not treated as fixed merely because the new
driver built.

## Confirmed Samsung mount blocker

The beta-5 report showed the old v4 library still visible and the mount bridge
blocked on `/vendor/etc/audio_effects.xml`. The supplied file was well-formed XML
with 25 CRLF and two LF records. Its exact bytes reproduced the rejection; merely
normalizing CRLF made the original parser pass.

Test2 strips only a terminal CR from the matching view and prints the original
record for all retained vendor lines. The reported file now passes byte-identically;
CRLF insertion/idempotence and malformed-input rejection are regression-tested.
This removes a demonstrated pre-mount failure, not proof of HAL loading or audio.
The driver/helper/app hashes below are unchanged. After updating to test2, the
collaborator reported that it works. The [Samsung record](SAMSUNG-RECOVERY.md)
separates that positive report from the missing post-fix instrumented checks.

## Released test2 identity

- Module: `v6.6-beta-5-samsung-test2`, versionCode 141.
- Native source: `8c70215c61676c2a3e0f2d570c0dc3d4255d5e74`.
- Private build record: `8395181fa1819b561e556cd899b159ba1eec58b9`.
- Driver SHA-256: `f8148f22d7e606273205d3f8512c62ef89c3d80043771c1555c45c7b3eb77097`.
- Helper SHA-256: `e91bc9724a06eb65ffb88ba575b63760d026710d7a8376f0eb40d70b932b1521`.

The compiler's gate report was reproduced independently on the integration host.
The driver has eight direct platform dependencies, no direct versioned audio AIDL
DSOs and exactly the three factory exports. This does not exclude dependencies
of the platform libraries themselves or prove vendor factory compatibility.
The compiler also ran the native/Soong host and isolated Binder suites; none of
those results substitutes for Android device, HAL, SELinux or audible testing.

## Installer discovery is not a compatibility verdict

The Samsung integration branch no longer aborts v5 installation merely because
`service list` does not enumerate an AIDL effect factory. The reported installer
used an MMRS metainstall environment; its listing was negative, but that log alone
does not establish whether the firmware lacks AIDL, the service is not yet
published, or the installer's Binder view differs. None of those explanations
has been confirmed on this second Samsung.

The v5 manifest selects the shipped ARM64 AIDL candidate and `.AIDL` path, rather
than falling through to historical legacy binaries that are absent from the ZIP.
A missing listing produces an explicit warning and an
`install-transport.status` diagnostic with `factory_discovery=not_observed` and
`compatibility=unverified`. Even an observed factory does not prove the driver
can load. The ARM64 device ABI check, artifact/signature checks, ELF dependency
validation, namespace checks and audited runtime recovery preflight remain.
No Binder stability relaxation or broader SELinux grants are introduced.

This permits an experimental installation, **not HIDL support**. A firmware that
only provides HIDL/legacy effect loading still needs a compatible native adapter;
removing this installer gate cannot create one. Successful installation does not
prove effect registration, native control or processed audio.

## Import and packaging

The compiler publishes artifacts, matching unstripped symbols, pinned AOSP
manifest and private build logs in the private builds repository. Do not copy
full logs, manifests or local paths into this public module repository.

The compiler also supplies the license/NOTICE texts for incorporated components.
Review these and save them as `native-control/v5-NOTICES.txt` before import. The
packager pins and redistributes this file; do not substitute a placeholder.

The integrator runs this from the module checkout, with explicit local artifact
paths and the final source commit pinned in `native-control/v5-candidate.json`:

```sh
python3 tools/import_native_control_v5.py \
  --driver "$DRIVER" --unstripped-driver "$UNSTRIPPED_DRIVER" --helper "$HELPER" \
  --manifest "$AOSP_MANIFEST" --source-commit "$SOURCE_COMMIT" \
  --readelf "$LLVM_READELF" --nm "$LLVM_NM"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
for file in *.sh common/*.sh; do sh -n "$file" || exit 1; done
JDSP_READELF="$LLVM_READELF" python3 tools/package_native_control_v5.py
```

The importer independently inspects the artifacts without executing them. It
requires matching stripped/unstripped load segments, embedded defined symbols,
NODELETE, factory exports and the restricted runtime dependency profile. It
stages all verification before replacing the candidate and retains only
allowlisted provenance. A failed inspection leaves existing payloads untouched.

This experiment is ARM64 AIDL-only. The installer checks the advertised AIDL
factory and device ABI before library copies or app migration; it does not silently
fall back to a historical legacy driver.

The ZIP includes one driver and matching helper, the authorized root APK and
v5-specific provenance. Historical manifests and alternate app UIs are excluded.
Its version metadata changes only after a successful import. Packaging refuses
an awaiting build, mismatching hashes, wrong branch or forbidden dependencies.
The old v4 packager is historical tooling, not the entry point for this candidate.

Build/ELF acceptance is not device validation. Do not install, restart audio or
publish a release merely because these checks passed.
