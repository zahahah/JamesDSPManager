# Samsung h8q recovery candidate

This branch is an experiment for the reported `h8q` firmware. The library,
`jdspctl`, and signed root app 1.6.17 (code 62) are unchanged from beta-4.
No Samsung audio processing or safe-recovery result has been demonstrated yet.

## Why this differs from Pixel

The Samsung default effect factory is hosted by `audiohalservice.qti` under
`vendor.audio-hal-aidl`. Its `dumpsys` returns success without a descriptor
list. Both this HAL and `secaudiohalaidl` have `onrestart restart audioserver`.
The firmware also provides `sys.audio.restart.hal`: a stop/start sequence for
several audio services, designed to avoid the direct restart cycle.

The experiment uses that audited firmware handler, never `ctl.restart` or
guessed Binder transaction numbers. It verifies the exact handler body and
service declarations as data, plus the device, current boot's late-load state,
typed policy refresh, factory-owner PID, executable identities, and overlays
visible to both HALs. A shell-linker check is only a prerequisite; it is not a
test of the running HAL's linker namespace.

## Defaults and consent

**No automatic Samsung reload is enabled.** The existing 10-second scheduler
reports `samsung_requires_explicit_retry` on h8q without touching audio.
An installed module alone does not authorize the firmware sequence. The
opt-in marker is not included in the ZIP. Other Samsung models remain blocked.

Read-only preflight (logs are written, but no restart property or boot guard):

```sh
su -c '/data/adb/modules/ainur_jamesdsp/samsung-audio-recovery.sh --check'
```

Only after the owner authorizes the test and has a recovery plan:

```sh
su -c 'touch /data/adb/modules/ainur_jamesdsp/.samsung-firmware-recovery-opt-in'
```

Then use the code-62 app's **Retry** button, or the equivalent explicit command:

```sh
su -c '/data/adb/modules/ainur_jamesdsp/audio-hal-recovery.sh --retry'
```

The handler stops and starts multiple services. Audio and calls may be
interrupted, `audioserver` may also restart as a consequence of vendor behavior,
and temp-root can become unstable or enter safe mode. A normal reboot may lose
root. Do not test during a call or without a usable recovery path.

A shared nonblocking lock prevents concurrent module reloads. A per-boot guard
is written **before** the one property request; even a failed request consumes
that attempt. There is no automatic retry, timeout reset, or rollback restart.
Do not remove guards or reinstall the module to force another attempt.

To disable Samsung recovery, without uninstalling the app or clearing data:

```sh
su -c 'touch /data/adb/modules/ainur_jamesdsp/.samsung-firmware-recovery-disabled'
```

## Interpreting results

- `PREFLIGHT`: prerequisites passed, but loading and processing are unverified.
- `LOADED`: matching library file is visible and mapped in the verified factory
  process. Following a reload, both target HAL PIDs changed, the firmware
  property reset, and a bounded stability check passed. **This is not proof of
  effect registration, a writable native context, or processed audio.**
- `BLOCKED`: a preflight/reload check failed; consult the reason and logs. Do not
  bypass the check or assume a new native build is required.

On `LOADED`, exit success lets the existing app recreate its screen and perform
`AudioEffect.queryEffects()` again. The app, not a parsed vendor dump, checks the
JamesDSP UUID and handles Global-mode attachment. If the factory still does not
advertise the effect, the error remains visible; no second reload is permitted.

Evidence stays in `logs/samsung-audio-recovery*`: before/after PID and service
snapshots, linker preflight, native helper replies when available, and a bounded
loader-log excerpt on failure. It is not included in packages or public release
provenance. Check native context, accepted/applied generations, increasing frames,
and audible output separately after registration and attachment succeed.
