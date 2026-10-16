# Test 14: Samsung AIDL query trace

This test package adds diagnostic logging to the Samsung AIDL pin wrapper. It
does not change the Pixel/Mustang path, automatically restart audio services,
or claim that the Samsung effect is working.

After installing the module and rebooting, open JamesDSP once. Then collect:

```sh
su -c 'logcat -d -b all -v threadtime | grep -iE "JDSPPinWrap|EffectsFactoryHalAidl|f27317f4|f98765f4" | tail -n 100'
```

Interpretation:

- `event=wrapper_loaded` confirms the AIDL factory loaded the wrapper.
- `event=query_effect_entered` confirms the factory requested its descriptor.
- `event=real_library_open_failed` gives the dynamic-linker failure for each
  candidate path.
- `event=query_effect_returned result=0` means the real library returned a
  descriptor successfully; it does not by itself prove playback processing.
- If the wrapper loads but no query event appears after opening the app, the
  effect identity is not reaching the factory query path.
