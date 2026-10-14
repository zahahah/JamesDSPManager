# Galaxy h8q late-load refresh test

This ZIP is an experimental late-load test for the Samsung Galaxy h8q evidence
provided by a tester. It keeps the validated Mustang path intact. Other
unrecognized devices still use conservative native AIDL config preparation
and do not restart the Audio HAL automatically.

The version is v6.5.9-test8-samsung-legacy-name-aidl, not the stable v6.5.9 release.
The module ID and the two signed root APKs are unchanged. No APK was rebuilt
or resigned, and stable auto-update metadata is excluded from this ZIP.
The stable dist/JamesDSPManager-v6.5.9.zip remains the published artifact.

On ro.product.device=h8q only, if the descriptor is absent from
IFactory/default, the late-load stage makes one guarded restart request for
the observed init service vendor.audio-hal-aidl. It reports success only if
that service PID and the audioserver PID both change, the factory dump then
contains the JamesDSP implementation UUID, and both processes remain stable for
a short bounded check. If Samsung exposes a numeric effect count, the script
also rejects a decrease; if its factory dump omits that count, the exact JDSP
UUID is the post-refresh discovery gate. It does
not directly restart audioserver, retry in a loop, or apply this behavior to
other Samsung models. The service stage now explicitly passes the late-load
marker into the refresh script. A per-boot-and-module-version guard prevents
repeat attempts while allowing one attempt after updating the test module.

Portable preparation prefers the existing vendor audio_effects_config.xml,
or validated candidates from the highest-priority available partition. For
multiple SKU configs in that partition, it patches each SKU variant. It does
not prove which file the factory actually reads.
On h8q, device evidence showed that Magic Mount is visible inside the audio HAL
but neither patched SKU config was consumed by IFactory/default. The Samsung
profile therefore also discovers audio_effects_config variants such as
audio_effects_config_stub.xml and audio_effects_config_sec.xml. Only files that
pass the same bounded native-AIDL XML validation are staged; unsupported
variants are logged and left untouched. Other portable profiles keep the
narrow audio_effects_config.xml search.
Test7 proved that all five config/config_sec/config_stub candidates were staged
and visible but still not consumed by IFactory/default. On h8q, this build also
considers audio_effects.xml and audio_effects_sec.xml because Samsung may retain
legacy-looking names for AIDL content. These names are accepted only when the
document passes structural validation and declares at least one AIDL-suffixed
effect library. Dedicated haptic and spatializer XMLs remain excluded.
It supports conservative line-oriented XML with double-quoted effect/library
attributes, one tag per line, and self-closing library/effect entries. Inline,
multiline or otherwise unsupported XML and unvalidated staged audio
configuration payloads are blocked rather than guessed.
No legacy-to-AIDL translation is performed for unknown late-load firmware.
Versioned AIDL NDK SONAMEs may be retargeted to the highest installed matching
version in the module-local library. The subsequent linker check must succeed
before the overlay is allowed; an unresolved or incompatible dependency still
blocks mounting. JDSP_PATCH_AIDL_NDK=0 disables this adaptation. Early boot
and the Mustang profile retain their existing behavior.

Magic Mount-rs remains responsible for the overlay. There is no direct-mount
fallback, native hook, process kill, or compatibility library installed
globally. Linker checks run in the module script environment; they do not prove
dependency visibility in the HAL's actual namespace.

Useful logs after installing/testing:

- logs/late-load.status
- logs/late-load-context.txt
- logs/late-load-linker.txt
- logs/audio-reload.status
- logs/audio-reload-linker.txt
- logs/service.status

READY from module preparation only means config and library staging passed.
On h8q, audio-reload.status separately reports whether the bounded refresh led
to factory discovery. A BLOCKED result after the attempt is not evidence of a
working effect.

This is not a Samsung success claim. The new behavior has not yet been
validated on a Galaxy h8q. Factory discovery, app creation/enabling, audible
processing, pause/resume, relevant AVCs and unexpected reboots still need
real-device validation. Installation, exploit repetition, manual mounts,
soft reboot, additional audio restarts or policy changes require separate
authorization. Rollback uses the previously installed test artifact through
an approved device workflow. Never uninstall james.dsp or clear app data
automatically.
