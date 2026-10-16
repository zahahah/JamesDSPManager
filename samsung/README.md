# Samsung direct-driver development base

This is a separate packaging/runtime lane in **JamesDSPManager/samsung-test**.
It is not a released fix, a verified boot-safe module, or proof that JamesDSP
processes audio on Samsung. Do not send it to the tester as a replacement for
test20 before reviewing its exact temp-root callback behavior and driver build.

## Why a separate lane

Test20 mixes an AIDL wrapper, eager loading, dependency SONAME substitutions,
and a guarded HAL restart. The tester reports Dirty Frag 1.16, KernelSU Samsung
2.2 by diabl0w, automatic reboot behavior, OneUI Safe Mode, and an unavailable
JamesDSP effect. The exact cause and restart sequence have not been established.

The actual **ViPER4Android-RE-AIDL-v2.1.1.zip** (not just the legacy source
checkout) was inspected as a reference. Its archive SHA-256 is
`536f981610fe378b2ae5703b1c8a1ea5c87a8dce7ac34f904d641c0c701e2f1d`.
It uses a direct AIDL library, self-mounts, and an independent control service.
It also kills audio processes with a retry; this implementation intentionally
does **not** copy that behavior, its broad policy grants, or its property edits.
Reference: <https://github.com/likelikeslike/ViPERFX_RE/releases/tag/v2.1.1>.
Existing source attribution and licenses remain in their original repositories.

## What this lane implements

- An independent ZIP builder: no inheritance from the old experiment chain.
- One explicitly supplied Android ARM64 AIDL driver; no implicit old prebuild,
  pin wrapper, replacement framework DSO, or dependency rewriting.
- `skip_mount` / `skip_mountify` so the manager does not overlay the module tree.
- Inert `post-fs-data.sh` and `late-load.sh`: no binds before the manager mounts.
- `service.sh` activates only when **both** `KSU_LATE_LOAD=1` and
  `KSU_RUNTIME_MODE=late-load` are supplied for the current invocation. It never
  manufactures these from a saved marker. Activation also requires Android boot
  completion, Samsung ARM64, init namespace entry, and a verified driver digest.
- No mount-namespace fallback: failure to enter init's namespace blocks work.
- The currently scoped factory is `audiohalservice.qti`; its mount namespace
  must match init's. Other Samsung HAL process layouts fail closed. PID/namespace
  and boot readiness are checked again around live mounts, not only at entry.
- Linker dependency preflight before live mounts. This checks load dependencies
  in that context, **not** all HAL-domain policy, AIDL ABI, or descriptor semantics.
- Copy-on-stage bind mounts for `/vendor/lib64/soundfx` and existing native
  `audio_effects_config*.xml` files in `/vendor/etc` and the reported active SKU.
  Stock files, hidden files, postprocessing, and copied labels are retained.
- A bounded, deliberately line-oriented XML patcher. Unsupported layouts fail
  closed. It is not a complete XML parser/schema validator. No generated stock
  template, guessed SKU, `/vendor/etc` tree overlay, APEX mount or routing edits.
- Re-activation checks actual mount IDs and visible driver/config contents.
- Logs/work state use a private umask; mounted copies retain stock directory,
  library and config permissions so the audio process can still read them.
- Failed activation rolls back only this attempt's identified mounts, in reverse
  order. Failed rollback is reported; work directories are retained, not erased
  while they might back live mounts. No global unmount/disable-all operation.
- Status is `MOUNTED_UNVERIFIED`, never a claim of engine creation or processing.
- No automatic APK installation, HAL/audioserver/OS restart, live policy changes,
  or audio property modifications.

The module ID remains `ainur_jamesdsp`, so this is an alternative package, not a
second JamesDSP module to install alongside the existing one. Build/install paths
are independent, but prior live mounts are not magically undone by an update.
The runtime refuses existing JDSP payloads/configs and target overlays rather
than replacing another session's mounts. Review the temp-root recovery sequence
before any authorized device trial. Disabling a module does not necessarily
detach mounts that are already active. Do not delete work directories backing
active mounts. This base has no automatic uninstall-time mount cleanup.
The installer refuses a mixed legacy installation directory instead of deleting
old scripts/policy or silently combining them with this runtime.

## KernelSU callback evidence

The published `samsung-v2.2` sources (commit
`b38f4096f33632ad5871dc3fff0ec426e23c9358`) explicitly run:
`late-load` -> metamodule mount -> `post-mount` -> `service` -> `boot-completed`.
`get_common_script_envs()` supplies `KSU_RUNTIME_MODE` and, when applicable,
`KSU_LATE_LOAD=1` from the runtime. This is why self-mounting happens in
`service.sh`, not the pre-mount callback:

- <https://github.com/diabl0w/KernelSU/blob/samsung-v2.2/userspace/ksud/src/late_load.rs>
- <https://github.com/diabl0w/KernelSU/blob/samsung-v2.2/userspace/ksud/src/module.rs>
- <https://github.com/diabl0w/KernelSU/blob/samsung-v2.2/userspace/ksud/src/ksucalls.rs>

This establishes the published code's ordering, not that the tester's installed
APK/daemon exactly matches it. Dirty Frag 1.16's actual reboot implementation and
the active metamodule still need identification. Do not infer missing runtime
variables or add a marker-based fallback for another version.

The existing unmodified JamesDSP prebuild at
`common/files/aidl/libjamesdsp.so` has SHA-256
`3005729e46acb16b04bc16e32c0c83db1859ff92ad524990e3b774ae9acb1252`.
Static ELF inspection shows a dependency on
`android.hardware.audio.effect-V2-ndk.so`; the tester's process maps showed
`android.hardware.audio.effect-V3-ndk.so`. This is a concrete build/dependency
fact to investigate, **not proof that V2 effects cannot work with a V3 HAL**.
Changing a dependency name alone does not establish C++/descriptor compatibility.
This builder does not implicitly select, patch, or claim to rebuild that prebuild.

## Build prerequisites / packaging

The driver itself must first be compiled in a compatible Android platform
environment, e.g. the Debian x86_64 Dell build workspace. The host architecture
is not the Android target architecture. LightningDSP is a **reference**, not a
new binary already built or validated by this change:
<https://github.com/zahahah/LightningDSP>.

Its relevant target is `libjamesdspaidl`, using AOSP/Soong and dependencies such
as `aidlaudioeffectservice_defaults` and `effectCommonFile`. Do not pretend a
desktop shared library, stub-linked wrapper or legacy driver is that target.

After producing a real Android ARM64 AIDL library, the host-only packaging form is:

```sh
python3 tools/package_samsung_direct.py \
  --driver /absolute/path/to/libjamesdspaidl.so \
  --sha256 <actual-64-character-sha256> \
  --source-revision <actual-git-commit> \
  --notices /absolute/path/to/source-build-NOTICE.txt \
  --readelf /absolute/path/to/llvm-readelf \
  --output dist/JamesDSPManager-v6.5.9-test21-samsung-direct-driver-base.zip
```

Replace the placeholders; they are not runnable values. The builder inspects ELF
metadata without executing the library, requires ARM64/shared-library shape and
the three factory exports, rejects obvious desktop libc dependencies, and records
the unmodified bytes, declared source revision, dependencies, exports and hash.
The revision is supplied by the build operator, **not a verified provenance
attestation**. These checks cannot prove Android compatibility or bit-for-bit
equivalence to the source. Preserve the AOSP manifest, product, build command,
toolchain, native source notices/licenses and logs beside the actual build.
Before distributing any real driver, collect and review all required license
notices from that source build; this package skeleton does not invent a license
for an arbitrary supplied binary.

No real test21 driver/package is produced automatically. There is no APK in this
ZIP; keep the existing owner-signed root app under user control. No signing
credentials are needed for this native packaging step. It is version code 130
only to identify a future local candidate; no update feed is included.

## Validation and explicit limitations

Host tests mock all namespace, linker, label and mount operations against
temporary fixtures. They do not run module scripts on a phone. Package tests use
non-executable fixture bytes and a readelf mock; that is contract testing, not a
compiled driver. Existing Pixel/stable runtime files are unchanged.

Pending before any functional claim:

1. Compile and audit the actual AIDL library, ABI/dependency set and build notices.
2. Confirm the installed binaries match the published KernelSU Samsung 2.2
   callback/env contract, and identify Dirty Frag 1.16's reboot behavior.
   Before-boot calls are deferred, not waited on or retried in a background loop.
3. Verify mount visibility from the factory process and the HAL's SELinux domain.
4. Verify descriptor query, effect creation/open, buffers, channels and lifecycle,
   including DSO lifetime while Binder objects exist. Removing the wrapper does
   not implement native self-pinning or prove safe library unloading.
5. Verify frames traverse the DSP, parameters apply, and EQ changes are audible.
   Existing live factories may cache descriptors; this runtime does not restart
   them or ask DFRoot to reboot to force discovery.
6. Add a native control/telemetry service and a matching app backend if warranted.
   There is **no `jdsp.control` service yet**. Such a service controls the DSP;
   it cannot substitute for factory acceptance and a working audio path.

Do not publish this base as a solution, enable automated phone trials, transplant
ViPER UUIDs/parameters or change Pixel's backend to conceal these gaps.
