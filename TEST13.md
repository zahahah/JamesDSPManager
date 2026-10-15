# Test13: Samsung h8q effect-status experiment

This is a local test build, not evidence that JamesDSP processes audio on the
Samsung h8q. The built-in Mustang path and original APK are unchanged.

The ThePBone root APK remains versionName 1.6.15, with versionCode 58 and the
same authorized certificate as test12. Its executable DEX files are unchanged
from test12. Only the failure-screen text was corrected: a library invisible
to the app does not prove that the module is absent. The failure screen still
blocks claiming that audio processing is active.

For h8q only, when the mounted library and XML exist but the AIDL factory does
not expose JamesDSP's implementation UUID, the service writes
`logs/samsung-aidl-diagnostics.txt` and reports
`BLOCKED reason=samsung_factory_descriptor_missing`. It does **not** restart
the audio HAL or audioserver. The diagnostic records the relevant mount
namespaces, visible paths, loaded library maps, and the factory descriptor
result. It does not mount files or alter device state.

Successful module preparation, mount visibility, and app launch are separate
from successful AIDL registration. The test must not be called working until
the UUID is exposed by the factory, effect creation succeeds, and audible
processing is verified on the device. No device installation or restart was
performed while building this ZIP.
