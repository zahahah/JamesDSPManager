# Test 19 — Samsung AIDL experiment with the updated root app

This pre-release continues the test18 `samsung_h8q` late-load experiment and
adds the owner-signed RootJamesDSP root-flavor APK as an optional sidecar. It
does not automatically replace or install an existing app. The included app
is `james.dsp`, version `1.6.14-zahah-samsung-test`, version code 61; its
certificate matches the authorized maintainer key. The app source is based on
RootJamesDSP 1.6.14, not upstream 1.6.15.

The module version is test19 / version code 128. The guarded eager-load,
SONAME-retarget, and one-shot `vendor.audio-hal-aidl` refresh remain
experimental; refreshing the HAL can interrupt audio and this build is not
evidence of successful processing. Do not uninstall the app or clear its data.

To manually update the app on a tester device, extract
`common/files/JamesDSPManagerZahah.apk` from this ZIP and install it with
`adb install -r` (or the equivalent package-installer update flow). It is
signed with the same owner certificate and has a higher version code than the
diagnostic test app. The module itself intentionally does not perform that
update.

Return the following after installing the module and manually updating/opening
the app:

```sh
su -c 'M=/data/adb/modules/ainur_jamesdsp; \
echo "=== MODULE ==="; grep -E "^(version|versionCode)=" "$M/module.prop"; \
echo "=== STATUS ==="; cat "$M/logs/late-load.status" "$M/logs/audio-reload.status" 2>&1; \
echo "=== EFFECT / APP LOGS ==="; logcat -d -b all -v threadtime | grep -iE "JDSPPinWrap|EffectsFactoryHalAidl|JamesDspRemoteEngine|f27317f4|f98765f4|AudioEffect|avc: denied.*(jamesdsp|soundfx|audio.effect)" | tail -n 160; \
echo "=== AUDIO SERVICES ==="; pidof audiohalservice.qti audioserver'
```

Do not claim success without confirming effect creation and audible processing.
