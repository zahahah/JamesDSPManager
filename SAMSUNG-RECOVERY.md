# Samsung temp-root: the reported working configuration

After updating to **v6.6-beta-5-samsung-test2 (code 141)**, the collaborator
reported: **“Dude this one works”** This is a positive device report following
the XML mount fix, not an instrumented confirmation of every DSP/control stage.

Earlier diagnostics from this collaborator identified `h8q`, reported model
`SM-F971U`, Android 17 / API 37, and a KernelSU root context in a DFRoot temp-root /
late-load environment. The success message did not include a fresh firmware
fingerprint or a complete configuration dump. Do not generalize it to every
Samsung firmware, root manager, output route or Audio Effect AIDL version.

## Pin the actual working release

Use the [test2 prerelease](https://github.com/zahahah/LightningDSPManager/releases/tag/v6.6-beta-5-samsung-test2),
not an older ZIP with a similar branch or test name.

| Component | Identity |
|---|---|
| Module | `v6.6-beta-5-samsung-test2`, versionCode **141** |
| Released module source | `82b4fc38b1f7a41288aefe6a647a27845538e3fb` |
| XML parser fix | `1a1dcb02be5f0082c44923b0d122872c3ee6f040` |
| ZIP SHA-256 | `a0cf48bcf2a8a641306539da43bc1e83737789bda1a1093c452991c98c59daa9` |
| Native source | `8c70215c61676c2a3e0f2d570c0dc3d4255d5e74` |
| Driver installed as | `/vendor/lib64/soundfx/lightningdsplib.so` |
| Driver SHA-256 | `f8148f22d7e606273205d3f8512c62ef89c3d80043771c1555c45c7b3eb77097` |
| Matching helper | `/vendor/bin/ldspctl` |
| Helper SHA-256 | `e91bc9724a06eb65ffb88ba575b63760d026710d7a8376f0eb40d70b932b1521` |
| Root app | `com.lightning.dsp`, **1.6.17 / code 62**, unchanged from the first beta-5 test |

The APK identity, signer and complete artifact hashes remain pinned in
[`native-control/v5-candidate.json`](native-control/v5-candidate.json).
The compiled source uses embedded **Effect AIDL V4 / media common V5** bindings;
our independent `ldsp.control` protocol is still **3**. These are different version
numbers. A working report does not prove general Effect V3 factory compatibility.

## The pieces that need to stay together

1. **Embed the native implementation, not just headers.** The v5 driver contains
   the AOSP base effect and frozen NDK bindings/parcelables, with a static C++
   runtime. ELF inspection found eight direct platform dependencies, no direct
   versioned audio AIDL DSOs, exactly the three factory exports, and NODELETE.
   Platform-library dependencies and factory ABI requirements still exist.
2. **Prepare the overlay before activation.** `post-fs-data.sh` stages the driver
   and effect configuration for the mount manager. `native-control.sh` prepares
   the root helper and typed service mapping, then refreshes typed policy after
   the overlay becomes visible. There are no broad app grants or requests for
   SELinux permissive mode.
3. **Mount in init's namespace, not merely the root shell's.** After the existing
   ten-second late-load delay in `service.sh`, `aidl-effect-mount.sh` stages the
   library and live vendor/ODM/system/product/system_ext/SKU XMLs. Every config
   must pass before any planned bind mount is applied. Existing effects, routing,
   labels and stock soundfx files are preserved; there is no whole `/vendor/etc`
   replacement or Pixel-specific library-name translation in this bridge.
4. **Accept mixed XML line endings without rewriting stock lines.** Strip only
   the terminal CR in the AWK matching view. Print the original record for retained
   vendor lines and comments. Keep the malformed/ambiguous-config checks and the
   all-before-mount preflight. Do not work around this bug by skipping a config.
5. **Recover through verified firmware capabilities when needed.**
   `audio-hal-recovery.sh` dispatches to `aidl-audio-recovery.sh`. It discovers the
   default factory owner and its init service instead of choosing by model. It
   audits the firmware's ordered `sys.audio.restart.hal=1` stop/start handler,
   requires typed policy readiness, and records a once-per-boot guard before a
   request. Automatic activation and Retry share that limit, including failed
   requests. PID, mapping and six-second stability checks follow. This describes
   the implemented path, not a post-success trace proving which branch ran.
6. **Keep framework attachment and app root authorization.** `AudioEffect` still
   discovers/creates the effect and owns its lifecycle. Writes through the
   root-native helper require UID 0 and cover enable, post-gain and prepared FIR,
   not every DSP parameter. The helper requires exactly one writable context;
   Global mode is an attachment/session setting, not a Binder transport selector.
   No app reinstall or data clear was needed for the script update. The test instructions were to update the
   module, wait at least 30 seconds after late-load activation, and reopen the app;
   the success reply did not spell out each action or the Global mode setting.

Earlier firmware diagnostics placed the default effect factory in
`audiohalservice.qti` / `vendor.audio-hal-aidl`, alongside
`secaudiohalaidl` / `vendor.secaudiohal-aidl`. Their init declarations restarted
`audioserver` on HAL restart, while audioserver also managed HAL restarts. That
potential cascade is why this path audits the firmware's ordered stop/start
handler instead of blindly restarting one named HAL. These are earlier firmware
observations, not a newly collected trace of the successful run.

For recovery risks, disable markers, Retry semantics and status meanings, read
[`TEMP-ROOT-RELOAD.md`](TEMP-ROOT-RELOAD.md). Do not delete boot guards to force
another request. A firmware handler or Binder disconnection may also restart
`audioserver`; the module does not explicitly request an audioserver restart.
Normal-boot handling is separate. A reboot can lose temp-root.

## What actually explained the last failure

The first beta-5 test reported module code **140**, but the root Termux view of
`/vendor/lib64/soundfx/lightningdsplib.so` still had the old v4 hash
`05b034cda6cf4b17d89d00efd612d01da3897b07f544d7e266ddca570ea1ae5a`.
Its recovery status was:

```text
BLOCKED reason=effect_mount_failed restart=not_requested
BLOCKED reason=config_structure_not_supported target=/vendor/etc/audio_effects.xml
LDSPCTL:ERR:service-unavailable-or-find-denied
```

The supplied XML was well-formed, with **25 CRLF records and two LF records**.
The original parser rejected those exact bytes; normalizing CRLF alone made it
pass. Structural patterns ending in `[ \t]*$` did not accept the terminal CR.
Because all configs are checked before mounting, this failure aborted the staged
mount plan before the firmware recovery request. An installed version string was
therefore not evidence that the new driver was active in the relevant namespace.

The file is retained byte-exact as
[`tests/fixtures/samsung-audio_effects-mixed.xml`](tests/fixtures/samsung-audio_effects-mixed.xml),
SHA-256 `ac1107a21c28f6b40bddf01d9d9f828499329249b82cf65fd29e2fc2b803db95`.
Its Git attributes prevent line-ending conversion on checkout. With the fix,
the supplied file passes and its output is byte-identical; insertion into other
CRLF files preserves stock records and is idempotent. Malformed CRLF input still
blocks before mounting.

**Nothing native was rebuilt between beta-5 test and test2.** Driver, helper and
signed APK hashes are unchanged. The reproduced preflight defect explains the
last mount blocker; the follow-up success is consistent with removing it. We do
not have a controlled comparison proving that every earlier change was necessary,
or a post-fix HAL trace establishing the entire causal chain.

## Evidence and remaining boundaries

- **Reproduced:** exact-file parser failure before the fix and success afterward;
  stock-byte preservation, idempotence and fail-closed staging tests.
- **Verified before release:** independent ELF inspection, signed APK identity,
  deterministic ZIP, and **124 passing CI tests** on the released source
  ([run 39705935441](https://github.com/zahahah/LightningDSPManager/actions/runs/39705935441)).
- **Reported after release:** the same collaborator said test2 works.
- **Not newly collected:** active driver/helper hashes in the factory namespace,
  factory UUID discovery, `ldsp.control` probe/status, accepted/applied generations,
  processed frames, a specific audible adjustment, playback route, Global mode
  setting, calls, stock-effect behavior or repeated boots.

Do not turn the short success report into invented telemetry. The earlier Pixel
v4 evidence is separate, and the previous five-second UI display was not proof
that DSP had been processing and then stopped. Keep this release as the reported
working baseline while checking those remaining stages when evidence is available.

## Historical test names

- **v6.6-beta-4-samsung-test1:** model-specific, manual opt-in firmware recovery.
- **v6.6-beta-4-samsung-test2:** common capability-driven bridge, still the v4
  native artifacts. It did not resolve the collaborator's reported problem.
- **v6.6-beta-5-samsung-test:** embedded v5 native artifacts; the mixed-newline
  XML preflight still blocked activation.
- **v6.6-beta-5-samsung-test2:** same v5 artifacts and app, corrected XML preflight,
  followed by the positive collaborator report documented here.

The old model-specific scripts remain historical source, not the current ZIP's
primary path. Do not use an old import script to regress versions or replace the
matching v5 driver/helper with historical prebuilds.
