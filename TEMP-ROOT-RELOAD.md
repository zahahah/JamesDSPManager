# Common AIDL late-load bridge

The bridge introduced in v6.6-beta-4-samsung-test2 remains the capability-driven
path in v6.6-beta-5-samsung-test2. There is no model allowlist. The current ARM64
v5 driver embeds Effect AIDL V4 / media common V5 bindings and the base effect
implementation rather than requiring their versioned audio DSOs directly. This
does not erase factory ABI requirements or the remaining platform dependencies.
Dependency and artifact integrity checks remain enabled. See the
[reported working Samsung configuration](SAMSUNG-RECOVERY.md).

## Order of operations

1. Prepare the module overlay before the mount manager consumes it. Preserve an
   existing vendor AIDL config. If it is absent, stage a dedicated LightningDSP-only
   AIDL config rather than translating legacy library names using Pixel aliases.
2. Ten seconds after KernelSU late-load, bind the driver and patched live XMLs
   into **init's mount namespace**. Scan vendor, ODM, system, product, system_ext
   and Qualcomm SKU config locations. Preserve vendor entries, routing and XML
   labels. Matching accepts CRLF/LF records without rewriting retained vendor
   lines. A missing driver file uses a shadow soundfx directory preserving its
   existing files and symlinks. There is no shell-namespace fallback.
3. Identify the default AIDL factory PID, its executable, and its unique running
   init service from firmware declarations. No process names are guessed from
   the device model, and an empty vendor factory dump is not parsed as an API.
4. Audit the firmware's `sys.audio.restart.hal=1` handler. Accept only one bounded,
   ordered stop/start list of audio services followed by its property reset. It
   must include the factory owner. Reject unrelated services, direct `restart`,
   `exec`, extra conditions/actions and ambiguous service identities.
5. When needed, request that handler **once per verified Android session**,
   including failed requests.
   Automatic activation does not require an opt-in marker in test2. Observe all
   initially running handler targets returning with new verified PIDs, the new
   factory owner, matching library mappings and a six-second stability window.
   New XML remains pending until this activation succeeds.
6. Let the existing app discover the LightningDSP UUID and attach its AudioEffect.
   A root-native writable context, applied commands, processed frames and audio
   output must still be checked separately.

## Retry, disable, and diagnostics

The app's Retry uses this same path. It can recover a preflight failure that did
not request the firmware sequence, but **cannot request a second reload in the
same Android session**. There is no kernel-boot cap across repeated soft reboots:
a newer zygote64 and its newer system_server (verified executable, parent and
process start times) allow a fresh attempt. A HAL-only restart or a Retry tap
does not. The lifecycle is rechecked immediately before consuming the guard.
The existing ten-second scheduler runs when KernelSU invokes the module service
hook; this is not a promise that every vendor's soft reboot invokes that hook.

Old guards without a lifecycle record remain blocked, since their original
framework identity cannot be reconstructed safely. The AIDL guard can be seeded
without a restart when the matching mapped driver already has a live, writable
native context and no pending mount generation. That marks the current session
as consumed and permits recovery after a later verified soft reboot. Otherwise,
a new kernel boot is needed; older non-AIDL guards remain respected. Do not
delete those guards or reinstall to force retries. Malformed lifecycle records
also block recovery. These checks prevent repeated requests
within a session, not vendor restart loops across full framework recreations.

```sh
su -c '/data/adb/modules/ainur_lightningdsp/audio-hal-recovery.sh --check'
su -c '/data/adb/modules/ainur_lightningdsp/audio-hal-recovery.sh --retry'
```

`--check` stages diagnostic files and labels outside system paths but does not
bind-mount, change properties or consume the boot guard. Do not run Retry during
a call. To disable both the new bridge and its recovery before activation:

```sh
su -c 'touch /data/adb/modules/ainur_lightningdsp/.aidl-recovery-disabled'
```

The older `.samsung-firmware-recovery-disabled` marker is also respected. The old
Samsung opt-in marker is no longer necessary. Disabling does not undo mounts
already active in this boot. The normal module-disable/boot recovery procedure
removes systemless overlays; reboot can also lose temp-root. No automatic
rollback restart is attempted.

Read `logs/audio-hal-recovery.status`, `logs/aidl-audio-recovery.status`,
`logs/aidl-effect-mount.status` and the bounded `logs/aidl-recovery-*` evidence.
`MOUNTED` means namespace files were verified. `LOADED` means a matching library
was mapped, **not** that the effect was registered or that audio was processed.
A native-ready probe can avoid an unnecessary restart only if there is no
unapplied mount generation. Reopen the app or use Retry after activation so its
existing UUID discovery runs again. Five seconds of visible controls is not
validation of any of these stages.

## Boundaries and risks

This follows the mounting-first approach of
[ViPERFX_RE v2.1.1](https://github.com/likelikeslike/ViPERFX_RE/releases/tag/v2.1.1),
without copying its broad process termination, app service grants or repeated
`resetprop` behavior. Firmware without an auditable stop/start handler is left
mounted but **not restarted**. A true `ro.audio.ignore_effects` blocks recovery
rather than being silently overridden. SELinux remains enforcing.

The mount manager still exposes the prepared canonical config, helper and typed
service mapping. This is not yet a manager-independent replacement: if the
canonical config target is absent, the bridge blocks rather than replacing all
of `/vendor/etc` and hiding nested mounts. APEX/32-bit paths and HIDL drivers are
not injected speculatively.

The dedicated config fallback does not reconstruct a vendor's full effect list;
if the factory chooses it instead of a legacy fallback, stock effect availability
can differ. Existing vendor XMLs are preserved when present. This needs device
regression testing, including stock effects, calls and all playback routes.
Audio can be interrupted, vendor behavior can also restart `audioserver`, and
DFRoot can destabilize. Our guard limits our requests, not vendor restart loops.
Keep runtime staging files under `.aidl-mount` while their mounts are active.

Neither successful host mocks nor ViPER working on a device proves this driver
works there. Our v5 driver retains its existing NODELETE lifetime protection;
the test2 CRLF fix changed the mount script, not that native mechanism. The
collaborator's positive test2 report is recorded separately from host tests and
from the still-uncollected post-fix Binder/frame telemetry.

## Pixel soft-reboot investigation (2026-10-21)

On the connected mustang running test2, a soft reboot retained the kernel boot
ID but replaced the HAL and Android framework processes. The current HAL saw the
correct v5 library and patched XML on disk, yet did not map the driver; its
factory listed 21 stock effects without LightningDSP. The existing kernel-boot guard
blocked another activation. This is consistent with the factory starting before
the late-load overlay was available, although startup visibility was not traced.

A single owner-authorized firmware recovery, without clearing existing guards,
changed the HAL PID, mapped the matching v5 driver, and registered LightningDSP as the
22nd effect. The native service initially had zero contexts. After reopening the
app, the live probe reported one writable context, accepted/applied generations
matched, and frames were nonzero. The owner confirmed audio processing returned.
This validates that recovery on this run, not repeated unattended soft reboots.

The Pixel branch now scopes the recovery guard to the kernel boot ID plus the
verified zygote/system_server start times. The Samsung test2 branch and release
remain the previously reported working baseline, without this guard change.
