# LightningDSP v6: one driver, two loading paths

This candidate distributes one ARM64 driver, exposing both the AIDL effect
factory entrypoints and legacy `AELI`. The firmware's HIDL wrapper consumes the
legacy ABI; we do not install a replacement HAL or a second effect service.
Both adapters share the DSP and the `jdsp.control` registry inside that process.
The existing signed root app and control protocol 3 are retained.

The S23 Ultra report showed `libjamesdsp.so` mapped in the legacy audio host.
The shipped v5 binary did not export AELI; the report itself did not hash the
mapped file. Mapping was not evidence of successful effect registration.
V6 addresses that missing ABI; it is not a guarantee that every Samsung firmware
will load, instantiate, route and process the effect correctly.

## Host selection and late-load

The module first uses the live standard AIDL factory PID. On the v6 profile,
when that lookup is unavailable, read-only HIDL discovery requires a vendor/ODM
manifest declaring the effect interface plus one live ARM64 audio process with
`hal_audio_default`, a mapped vendor legacy effects loader and an hwbinder FD.
This is a validated loader candidate, not RPC proof of effect registration.
Unknown/ambiguous hosts remain diagnostic failures, not guessed restart targets.

Recovery still validates the init service against the actual executable and
uses only the firmware's inspected audio stop/start property handler. A unique
base declaration plus one override is accepted only when the effective binary
matches the running process. Ambiguous overrides remain blocked. Existing
per-framework lifecycle guards and recovery opt-out markers remain in force.
The firmware can indirectly restart audioserver; no claim of isolation is made.

The historical `.AIDL` marker now also enables the dual-entry profile's existing
overlay/dependency hooks. It does not identify the active firmware transport.
The installer stages the same ELF even when service discovery is inconclusive;
real ABI/dependency/hash failures are not bypassed. ARM64 does not cover a
32-bit-only effect host. Older driver variants are excluded from the ZIP.

## Native behavior and limits

The legacy adapter validates UUID/handle/configuration and parameter envelopes,
attaches/detaches live telemetry, and consumes native controls at the block
boundary. Scratch space is allocated at creation, not grown by processing.
Supported legacy layouts are stereo PCM float/16/32/packed24/8.24, with write or
accumulate output. The legacy adapter rejects larger-than-8192-frame blocks,
unsupported layouts and deferred parameter commands. AIDL keeps its existing
stereo/5.1 behavior. Try-lock contention returns EBUSY instead of blocking the
callback; firmware behavior under contention still needs device testing.

The global control service remains separately subject to its publication,
Binder dispatch and SELinux gates. A working HIDL effect does not alone prove
native enable/post-gain/prepared-FIR control works. Other app parameters retain
the existing AudioEffect path. No effect-bound transport, Binder driver switch,
permissive SELinux or broad ordinary-app authorization is introduced.

## Evidence required on a device

Verify the imported artifact/hash, loaded ELF, effect discovery/creation, helper
protocol/authorization, correct writable context, accepted/applied generations,
increasing frame counters and an audible or measurable change independently.
Then test playback changes, screen on/off and soft reboots, and regress AIDL on
the reference devices. Build/host tests and ELF gates cannot replace these steps.

Public candidate/provenance files contain allowlisted artifact/source facts;
full compiler logs, pinned manifests and debug binaries remain private. Existing
v5 releases remain available for rollback. No APK migration is needed here.
