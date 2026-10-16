# Test 16 — Samsung AIDL effect diagnostic APK

This is a diagnostic-only `james.dsp` APK, version name `1.6.15`, version code
`60`. It preserves the normal Pixel path. On Samsung only, the app logs the
`AudioEffect.queryEffects()` descriptors and performs one create-and-immediate-
release probe for the JamesDSP implementation UUID. The probe is never enabled.
It does not change the module or restart audio services.

Install the APK as an update over the current test app (same package and signing
certificate). Do not uninstall the existing app or clear its data. Then run the
following command in Termux. Grant any permission prompt, return to JamesDSP,
and leave it open until the command finishes. Send back the complete output or
`/sdcard/Download/jdsp-samsung-aidl-test16.txt`.

```sh
su -c '
OUT=/sdcard/Download/jdsp-samsung-aidl-test16.txt
MARK="JDSP_TEST16_BEGIN_$(date +%s)"
umask 022

log -t JDSP_AIDL_DIAG "$MARK"
am force-stop james.dsp
am start -W -n james.dsp/me.timschneeberger.rootlessjamesdsp.activity.MainActivity
echo "Grant any permission prompt, return to JamesDSP, and leave it open for 20 seconds."
sleep 20

{
  echo "=== APP VERSION ==="
  dumpsys package james.dsp | grep -E "codePath=|versionCode=|versionName=" | head -n 5
  echo
  echo "=== AIDL FACTORY SERVICE ==="
  service list 2>&1 | grep -i "android.hardware.audio.effect.IFactory" | head -n 20
  echo
  echo "=== HAL PROCESS / JDSP LIBRARY MOUNTS ==="
  H=$(pidof audiohalservice.qti | cut -d " " -f 1)
  echo "audiohalservice.qti PID=${H:-not_running}"
  if [ -n "$H" ]; then
    grep -iE "libjamesdsp|audio_effects_config" "/proc/$H/mountinfo" | tail -n 20
    grep -i "libjamesdsp" "/proc/$H/maps" | head -n 12
  fi
  echo
  echo "=== DIAGNOSTIC / FACTORY LOGS SINCE TEST START ==="
  logcat -d -b all -v threadtime 2>&1 |
    awk -v mark="$MARK" "index(\$0, mark) { seen=1 } seen" |
    grep -iE "JDSP_AIDL_DIAG|JDSPPinWrap|EffectsFactoryHalAidl|AudioFlinger.*(effect|descriptor)|AudioEffect|UUID not found|libjamesdsp|dlopen|avc: denied" |
    tail -n 220
} > "$OUT" 2>&1

chmod 644 "$OUT"
echo "Report saved to: $OUT"
cat "$OUT"
'
```

Interpretation:

- `jamesdsp_descriptor=present` means the Android API listed the matching type
  and implementation UUID; `absent` or `queryEffects_result=null` means it did
  not.
- `createEffect_result=success` means AudioFlinger accepted and instantiated the
  requested effect; the diagnostic immediately disables/releases it.
- A `JDSPPinWrap` query/create event plus its result shows whether the Samsung
  factory reached the wrapper and what the plugin returned.
- This probe is diagnostic evidence, not proof that global audio processing is
  active. The `IFactory` service's `dumpsys` may remain empty on this device.
