# Test 20 — Samsung effect-discovery retry

Test20 carries RootJamesDSP test app version `1.6.14-zahah-samsung-test`
(version code 62) as an optional sidecar. On Samsung, this app now treats the
AudioEffect descriptor as the readiness signal (not an app-visible vendor
library path) and retries discovery briefly while the app is foregrounded. If
the descriptor becomes available, it restores the normal interface and starts
the configured processor without requiring an app force-stop. The app never
restarts audio services.

The module remains the test19 Samsung late-load experiment with module version
code 129. Its one-shot audio-HAL refresh remains test-only and can interrupt
audio. Descriptor discovery is not proof of effect creation or audible
processing. Keep the existing app/data; update the app manually from
`common/files/JamesDSPManagerZahah.apk` only if needed.

After installing/updating, open JamesDSP and leave it foregrounded for up to
30 seconds. If the app recovers, toggle processing and test a dramatic EQ
change during music playback. If it still shows the missing-effect screen,
return the module status and logs below; do not reboot audio services manually
or uninstall the app.

```sh
su -c 'M=/data/adb/modules/ainur_jamesdsp; \
echo "=== APP/MODULE ==="; dumpsys package james.dsp | grep -E "versionCode=|versionName=" | head -n 2; grep -E "^(version|versionCode)=" "$M/module.prop"; \
echo "=== MODULE STATUS ==="; cat "$M/logs/late-load.status" "$M/logs/audio-reload.status" 2>&1; \
echo "=== EFFECT DISCOVERY/CREATION ==="; logcat -d -b all -v threadtime | grep -iE "JDSP effect discovery|Samsung JDSP|JDSPPinWrap|EffectsFactoryHalAidl|JamesDspRemoteEngine|AudioEffect: set|createEffect|f27317f4|f98765f4|avc: denied.*(jamesdsp|soundfx|audio.effect)" | tail -n 180; \
echo "=== AUDIO SERVICES ==="; pidof audiohalservice.qti audioserver'
```

This test does not claim Samsung audio processing works until the effect is
created and an audible change is confirmed.
