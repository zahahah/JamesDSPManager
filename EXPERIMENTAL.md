# Galaxy late-load portability test

This ZIP is an experimental late-load diagnostic build. It keeps the validated
Mustang path intact, but unknown devices use conservative native AIDL config
preparation and do not restart the Audio HAL automatically.

The version is `v6.5.9-test1-portability`, not the stable v6.5.9 release.
The module ID and the two signed root APKs are unchanged. No APK was rebuilt
or resigned, and stable auto-update metadata is excluded from this ZIP.
The stable `dist/JamesDSPManager-v6.5.9.zip` remains the published artifact.

Portable preparation prefers the existing vendor `audio_effects_config.xml`,
or a unique supported candidate in vendor, ODM, system, product, system_ext or
SKU directories. It does not prove which file the factory actually reads.
It supports conservative line-oriented XML with double-quoted effect/library
attributes, one tag per line, and self-closing library/effect entries. Inline,
multiline or otherwise unsupported XML, ambiguous fallback candidates, and
unvalidated staged audio configuration payloads are blocked rather than guessed.
No legacy-to-AIDL translation or speculative SONAME substitution is performed
for unknown late-load firmware. Early boot retains its historical path.

Magic Mount-rs remains responsible for the overlay. There is no ViPER-style
direct-mount fallback, no native hook, no process kill, and no compatibility
library installed globally. Linker checks run in the module script environment;
they do not prove dependency visibility in the HAL's actual namespace.

Useful logs after installing/testing:

- `logs/late-load.status`
- `logs/late-load-context.txt`
- `logs/late-load-linker.txt`
- `logs/audio-reload.status`
- `logs/audio-reload-linker.txt`
- `logs/service.status`

A `BLOCKED reason=default_factory_needs_device_specific_refresh` status means
the module staged and mounted the library/config checks it can verify locally,
but the already-running default factory did not discover JamesDSP without a
device-specific, explicitly authorized refresh strategy.

This is not a Samsung success claim. Factory discovery, app creation/enabling,
audible processing, pause/resume, relevant AVCs and unexpected reboots still
need real-device validation. Installation, exploit repetition, manual mounts,
soft reboot, audio restart or policy changes require separate authorization.
Rollback uses the previously installed module artifact through an approved
device workflow. Never automatically uninstall `james.dsp` or clear app data.
