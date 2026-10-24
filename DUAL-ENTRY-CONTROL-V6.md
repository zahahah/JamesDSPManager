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

## Vendor DSP-thread scheduling profile

The module starts a small root-side watcher for the effect thread named
`James Audio DS`. It applies the vendor `RealtimePerformance` task profile only
when `/vendor/etc/task_profiles.json` defines that profile as exactly one
`WriteFile` action to `/proc/vendor_sched/groups/ta/set_task_group`, and the
matching `ta`/`fg` controls plus `/proc/vendor_sched/dump_task` exist. It moves
only a matching thread currently in `fg` whose host has a live `libjamesdsp.so`
mapping. Its thread start time is checked before restoring an assignment so a
reused TID is not treated as the old thread. Unknown profiles and other thread
groups are left alone. This prevents falling through to AOSP's generic
`cpu/rt` profile on devices with different policy.

The watcher checks every five seconds for late thread creation and HAL thread
replacement. It restores threads it changed when the module is disabled or the
watcher exits; a reboot resets the runtime assignment. It does not pin cores,
change governors, request FIFO scheduling, restart audio services, or adjust
effect settings. Devices without the exact vendor profile report a skipped
status and retain the existing behavior. The profile was manually tested on a
Pixel 10 Pro XL; support on other vendor implementations remains unverified.

`v6.6-beta-6.3-dsp-scheduler` also imports native source `8f80739614c6`:
bounded head sizing for eligible short/medium stereo FIRs, matrix-kernel loop
consolidation, and fewer out-of-line Soundstage calls. Strict, fast-math and
sanitizer regression suites passed. Synthetic timings do not establish a
live callback deadline improvement. Reverb source remains unchanged from the
previous candidate; the attempted vector rewrite failed its state/timing gate
and was rejected. The app, effect presets and control protocol are unchanged.

## Evidence required on a device

Verify the imported artifact/hash, loaded ELF, effect discovery/creation, helper
protocol/authorization, correct writable context, accepted/applied generations,
increasing frame counters and an audible or measurable change independently.
Then test playback changes, screen on/off and soft reboots, and regress AIDL on
the reference devices. Build/host tests and ELF gates cannot replace these steps.

Public candidate/provenance files contain allowlisted artifact/source facts;
full compiler logs, pinned manifests and debug binaries remain private. Existing
v5 releases remain available for rollback. No APK migration is needed here.

## Separate reverb experiment

`v6.6-beta-6.1-reverb-test` is built on the separate
`reverb-ring-index-optimization` module branch. It keeps the v6 loading/control
interfaces and existing APK, but tests a native circular-buffer index
optimization without changing reverb presets, filters or oversampling.

The previous v6 driver is the reference for bit-identical output/state tests,
including a real threaded Convolver + Plate High chain. Standalone timing
results vary with CPU placement and workload; improvement of the combined
chain and elimination of audible chopping are not established. This is a
playback comparison candidate, not a confirmed fix. The original beta-6
release and Samsung integration branch remain separate and available.


## Combined-effects DSP experiment

`v6.6-beta-6.2-dsp-test` continues on the same optimization branch. It adds
fixed-size Soundstage loop specialization, aligned channel storage, and safer
existing convolution-tail workers with serial fallback on creation failure.
Production partition selection remains unchanged: broader offload worsened
standalone Pixel timing and was rejected. No effect-count trigger, app rebuild,
audio restart or new transport is added.

The isolated widening stage used about 29% less thread CPU in three matched
Android standalone runs; full-chain timings were variable. This remains
experimental: live Android playback with five/six effects and the actual IR /
presets must verify processing margin and audible continuity. The earlier
beta-6.1 and original Samsung branch remain available for rollback.


## Soundstage tonal-transparency candidate

`v6.6-beta-6.4-soundstage` replaces only the width algorithm: a linear mid/side
matrix takes the place of fast multiband centre extraction. A bass-plus-treble
host signal exposed new components in the former implementation even without
other effects or clipping. The new stage retains the parameter scale and
pure-mid/pure-side gain curves, but intentionally changes mixed stereo output.
Width 50 is exact bypass; there is no Soundstage filterbank, envelope or delay
in the callback. Other effects, dual-entry loading, helper, scheduler watcher
and APK are unchanged. This needs listening validation on the packaged build;
previous releases remain available for comparison and rollback.
