# Manual late-load audio recovery (experimental)

The AIDL effect factory reads its effect configuration when its process starts.
After temp-root mounts the module late, a visible XML and library do not mean
the already-running factory has registered JamesDSP. The `service.sh` boot hook
intentionally **does not** restart audio automatically.

`manual-audio-reload.sh` is an opt-in, one-attempt-per-boot recovery tool. It
does not mount files, change SELinux policy, restart `audioserver`, or retry a
failed restart. It checks root, the module and late-load state, typed policy,
the library and XML visible through the selected HAL process, linker
dependencies, and the existing factory before requesting an init-service
restart. It requires **both** an explicit init service name and the process
name that hosts the default AIDL effect factory. Do not guess these names or
reuse names from another device.

For a device with a confirmed, recoverable audio-stack restart procedure, the
manual invocation is:

```sh
su -c 'JDSP_AUDIO_HAL_INIT_SERVICE=CONFIRMED_INIT_SERVICE JDSP_AUDIO_HAL_PROCESS=CONFIRMED_HAL_PROCESS /data/adb/modules/ainur_jamesdsp/manual-audio-reload.sh --manual-once'
```

Only run this after specific authorization for that device. Audio may stop,
calls may be interrupted, and a temp-root environment may enter safe mode or
lose root. Keep a recovery path available. The script writes its result to
`logs/manual-audio-reload.status`, plus bounded before/after factory dumps.
`DISCOVERED` means the factory lists the effect after a single restart. It does
**not** prove context creation, an applied command, processed frames, or an
audible change; those remain separate device checks.

After `DISCOVERED`, return to the JamesDSP app and tap **Retry** if its error
screen is visible. The app checks factory discovery again and, in Global mode,
requests session 0 if it is missing. Do not toggle Global mode merely to force
attachment. Check a live `jdspctl probe`, applied generation and processed
frames separately before claiming that audio is being modified.

If any preflight check fails, the script does not request a restart. If a
restart was requested but did not yield the effect, the boot guard prevents a
second attempt in the same boot. Do not remove the guard to force retries.
