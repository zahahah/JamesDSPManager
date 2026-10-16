# Test18 — Samsung AIDL eager-load + guarded refresh

This experimental package is based on test17 and changes only the Samsung
`samsung_h8q` late-load path. It leaves the Mustang and other profiles on their
existing behavior. It reuses the signed test17 diagnostic app; it does not
rebuild or re-sign the APK.

## What this test changes

- The h8q wrapper eagerly attempts to `dlopen` `libjamesdsp_real.so` and resolve
  its AIDL symbols from its constructor. It logs `real_library_preload_ready` or
  `real_library_preload_failed` before a later effect query. Query/create/destroy
  remain forwarded to the original library, and the wrapper still pins itself
  when first called.
- The Samsung path makes the existing versioned AIDL SONAME adaptation an
  explicit test-only opt-in. This test ZIP carries that opt-in marker because
  previous h8q preparation reached READY with this adaptation enabled.
- If the descriptor is still absent, the existing h8q refresh function makes
  one guarded request to restart `vendor.audio-hal-aidl`. It does not issue a
  separate `audioserver` kill or retry in a loop. The guard is scoped to boot ID
  and module version; status/dump and process-stability checks run afterward.
- The one-shot restart is present only in this experimental ZIP. It may
  interrupt audio and has not been validated on-device. It is intentionally not
  enabled by the stable package.
- The ZIP also carries `common/files/JamesDSPManagerZahah.apk`, a separately
  signed RootJamesDSP `james.dsp` build (`1.6.14-zahah-samsung-test`, version
  code 61). It is an optional sidecar for manual testing, not installed or
  updated automatically; the module leaves any existing app installation
  untouched. It uses the authorized maintainer certificate and can update the
  test APK at version code 60 without uninstalling it. SHA-256:
  `e64c7d5d1ea558e43a76a5321d0b8ae367f83ec86cf175c6964ffc42031694f3`.

## Logs to return

After installing this test package and opening the test APK once, return:

```sh
su -c 'M=/data/adb/modules/ainur_jamesdsp; \
echo "=== VERSION / STATUS ==="; grep -E "^(version|versionCode)=" "$M/module.prop"; \
cat "$M/logs/late-load.status" "$M/logs/audio-reload.status" "$M/logs/service.status" 2>&1; \
echo "=== LIBRARY LOAD ==="; logcat -d -b all -v threadtime | grep -iE "JDSPPinWrap|real_library_preload|real_library_open_failed|real_symbols_resolved|EffectsFactoryHalAidl|f27317f4|f98765f4" | tail -n 160; \
echo "=== HAL PROCESS ==="; pidof audiohalservice.qti audioserver; \
echo "=== FACTORY DESCRIPTOR ==="; dumpsys android.hardware.audio.effect.IFactory/default 2>&1 | grep -iE "Effects \(|james|jdsp|f27317f4|f98765f4|UUID:" | head -n 120'
```

Do not use this build as a success claim unless the factory lists the JamesDSP
UUID, the app creates/enables the effect, and audio processing is independently
confirmed. Do not uninstall the app or clear its data for rollback.
