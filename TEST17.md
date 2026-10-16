# Test 17 — Samsung early AIDL factory log

This is a diagnostic-only module for the h8q temp-root late-load path. It
starts a 75-second, tag-filtered logcat capture when post-fs-data detects the
Samsung profile. The capture begins before the module prepares its overlay and
before the observed factory process starts. It does not restart the audio HAL
or audioserver, install a hook, change effect descriptors, or enable an effect.

The result is saved at:

`/data/adb/modules/ainur_jamesdsp/logs/samsung-aidl-early-log.txt`

The companion status file is `samsung-aidl-early-log.status`. A per-boot and
module-version guard prevents duplicate late-load callbacks from truncating
the capture. The ZIP includes the signed v1.6.15 diagnostic APK; the module's
existing app installer does not replace an already installed app. Pixel and
other non-Samsung profiles do not start the capture.

After the tester's normal approved late-load/soft-reboot workflow, wait at
least 90 seconds and run:

```sh
su -c 'M=/data/adb/modules/ainur_jamesdsp/logs; echo "=== STATUS ==="; cat "$M/samsung-aidl-early-log.status" 2>&1; echo "=== EARLY FACTORY LOG ==="; cat "$M/samsung-aidl-early-log.txt" 2>&1; echo "=== MODULE ==="; grep -E "^(version|versionCode)=" /data/adb/modules/ainur_jamesdsp/module.prop'
```

Send the complete output. `JDSPPinWrap event=query_effect_entered` proves the
factory called the wrapper; `real_library_open_failed` includes the loader
reason. No wrapper event is only conclusive if capture status is COMPLETE and
its timestamps span factory startup. Even a registered descriptor would not
prove audible processing; that requires a separate device test.
