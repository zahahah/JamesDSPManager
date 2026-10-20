# Late-load audio recovery

The AIDL effect factory reads its effect configuration when its process starts.
After temp-root mounts the module, the library and XML can be visible while the
already-running factory still has not registered JamesDSP.

In the KernelSU late-load path, `service.sh` waits 10 seconds and schedules one
guarded recovery. It can restart only the verified audio HAL init service, never
`audioserver`. Device identity is allowlisted; unknown devices are left alone
until their exact HAL service and factory-host process are validated. At this
time the allowlist covers Pixel 10 Pro XL (`mustang`). The previously observed
Samsung process names are not sufficient evidence to restart its HAL safely.

The recovery validates root, module/late-load state, refreshed typed policy,
the library and XML visible through the selected HAL process, linker
dependencies, and the existing factory before requesting a restart. It records
its result in `logs/manual-audio-reload.status` with bounded before/after
factory dumps. `DISCOVERED` means the factory lists the effect, not that a
context was created or audio was processed.

The app's Retry action checks again and can request one additional guarded
recovery if needed:

```sh
su -c '/data/adb/modules/ainur_jamesdsp/audio-hal-recovery.sh --retry'
```

The automatic attempt and explicit retry each have separate per-boot guards,
so they cannot form a loop. A HAL restart can briefly interrupt audio or calls;
temp-root may be destabilized. Neither path restarts `audioserver`. Check live
probe, applied generation, processed frames, and audible output separately.
