# Test 15: Samsung app/HAL mount namespace detection

This is an experimental module package. It keeps the existing module payload,
Pixel/built-in configuration path, and AIDL diagnostic wrapper from test14.
The staged ThePBone app remains version 1.6.15 but has versionCode 59 and the
authorized signing certificate.

The app-side patch handles two Samsung-specific conditions inferred from the
reports: Android may return `null` from `AudioEffect.queryEffects()`, and the
app process can have a different mount namespace from the audio HAL. It first
uses the standard effect query and app-visible library paths; only if those
checks fail does the root-enabled app inspect the vendor/ODM/system library
paths through `/proc/<audio-HAL-pid>/root`. This changes the app's
"plugin installed" detection; it does **not** prove that AudioFlinger accepts
the descriptor or that audio processing works.

The port still has an unresolved factory-registration issue: prior reports
showed the HAL loading the pin wrapper but no query callback for JamesDSP, and
AudioFlinger did not expose the JamesDSP descriptor. Test this separately
after confirming the app now gets past the "not installed" screen. Do not
restart audio services automatically; use a manual service restart only when
the tester explicitly chooses to do so.

## Test

1. Install this module and select the ThePBone 1.6.15 app when prompted. Keep
   the existing app installed; the code version is incremented to allow an
   in-place update with the same authorized certificate.
2. Open the app. Expected immediate result: it no longer crashes when
   `queryEffects()` returns null and can detect the library in the HAL mount
   view even when it is absent from the app mount view.
3. If the app proceeds, enable/attach an effect and capture logs:

```sh
su -c 'logcat -d -b all -v threadtime | grep -iE "JDSPPinWrap|EffectsFactoryHalAidl|JamesDspRemoteEngine|AudioEffect: set|createEffect|f27317f4|f98765f4|avc: denied.*(jamesdsp|soundfx|audio.effect)" | tail -n 180'
```

Interpretation:

- `JamesDSP library detected in app or audio HAL mount view` means only the
  app's availability gate passed.
- `event=query_effect_entered` in the wrapper means the AIDL factory queried
  the plugin; `event=query_effect_returned result=0` means the library
  returned a descriptor.
- Successful session creation and audible processing are still required to
  establish that the Samsung port works.
