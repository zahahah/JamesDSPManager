# JamesDSP Manager

**Your music, with a little more say in how it sounds.**

This is our root-only JamesDSP module, paired with a modified version of ThePBone's JamesDSP app and our native audio library. It brings equalization, headphone correction, convolution and other DSP tools into Android's audio effects chain. You keep using your music player. JamesDSP handles the processing underneath.

The current release is **JamesDSP 6.6** (module code **153**), with our signed
**JamesDSP root app 1.6.17 (versionCode 62)**. It brings the latest
`reverb-ring-index-optimization` integration through the Samsung and Pixel
branches into `master`, without the separate LightningDSP app/module rebrand.

One ARM64 native driver provides both AIDL effect entrypoints and the legacy
`AELI` adapter used by HIDL effect factories. The release includes guarded
late-load and soft-reboot recovery, DSP scheduling and convolution improvements,
and the revised Soundstage stereo-width processing. See the
[v6 integration guide](DUAL-ENTRY-CONTROL-V6.md).

The beta series has been used on Pixel and Samsung devices with Android 17,
including temp-root/late-load setups. Those device reports do not establish
compatibility with every firmware or validate every later driver revision on
both devices. The exact native source, artifacts and host checks are recorded
in the release; further HIDL/Samsung device coverage is still welcome.

[Download the module and APK](https://github.com/zahahah/JamesDSPManager/releases/tag/v6.6) · [App source](https://github.com/zahahah/RootJamesDSP) · [Native library source (currently private)](https://github.com/zahahah/LibLightningDSP-OSS)

## What can it do?

JamesDSP gives you more than a few bass and treble sliders:

- **FIR and IIR equalization** to shape the frequency response.
- **Convolution** to apply impulse responses, including headphone or speaker correction profiles.
- **DDC/VDC correction** for compatible headphone profiles.
- **Dynamics processing and output controls**, including a compander, limiter and post-gain.
- **Crossfeed, stereo enhancement, bass boost, reverb and tube-style effects** for more specific adjustments.
- **Live programmable processing** if you enjoy going beyond the built-in controls.

It's a collection of tools, not a preset that automatically makes everything sound better. Start with a small adjustment, listen, then decide what actually helps. Turning every switch on is a valid experiment, but not necessarily a good listening strategy.

## What's different in this fork?

We're keeping the familiar ThePBone-based interface while changing how the app talks to the audio engine. The main control path is now **`jdsp.control`**, a global **Binder service** provided by our native `libjamesdsp` library, which I compiled myself.

There are three parts to the setup:

1. **The module** makes the native library and audio configuration available through a systemless mount overlay. It doesn't permanently rewrite your physical `/system` or `/vendor` partitions.
2. **Android's audio HAL** loads JamesDSP as an audio effect. This is where the native engine processes audio, rather than inside the settings screen.
3. **The app** changes the engine's settings. For supported native controls, it uses the root helper `jdspctl` to communicate with `jdsp.control`.

The short version:

```text
App settings → jdspctl (root) → jdsp.control → JamesDSP in the audio HAL
                                                        ↓
                                                  Processed audio
```

That diagram describes the control path. Audio samples aren't being sent through the root helper. Android's `AudioEffect` mechanism still handles effect attachment and lifecycle.

### Native first, legacy when needed

The app checks the native control path first. **Power, post-gain and FIR EQ** can use `jdsp.control`; features outside that contract still use the existing Android effect-parameter path. If native control isn't available or a supported operation fails, the legacy path remains a fallback.

So this isn't “we removed everything old and hoped for the best.” We're moving the controls we support to the new path while keeping the rest of JamesDSP usable.

The native service currently accepts writes from **root only**. Installing the module isn't enough: you also need to grant the **JamesDSP app** root access in your root manager. Granting root to Termux or ADB doesn't grant it to JamesDSP.

## Compatibility: what we've actually checked

The earlier v4 global-control setup was checked on a **Pixel 10 Pro XL (`mustang`) running Android 17, KernelSU and Magic Mount**. On that device, `jdsp.control` was published, the helper reported a writable DSP context, accepted control generations were applied, and processed-frame counters increased during playback.

That's evidence for this setup, not a universal Android compatibility badge.

- The v6 profile is **ARM64**, with embedded **Audio Effect AIDL V4** bindings, media common types V5 and a legacy `AELI` adapter in one binary. HIDL hosts use that legacy adapter; there is no replacement HAL. Embedded bindings reduce mandatory runtime DSOs, but do not remove factory/plugin ABI requirements or add support for 32-bit-only hosts.
- **Samsung `h8q`: reported working after the beta-5 test2 mount fix**, in the collaborator's DFRoot/KernelSU late-load setup. This is a user report, not a general Samsung or Audio Effect AIDL V3 compatibility result. Details and outstanding checks are in [the Samsung record](SAMSUNG-RECOVERY.md).
- The control protocol reports **version 3**. That's the version of our control interface, not the Android Audio Effect AIDL version. They're separate numbers describing different things.
- Root-manager mount behavior, firmware, output routing and other audio mods can affect whether audio reaches the effect. A visible module or a working settings screen isn't proof of processing.

**PIXAML isn't required for JamesDSP's basic effect path on the tested Pixel setup.** This module supplies the library and registers it with Android's default effect factory. PIXAML provides a separate AML service and may matter for other effects or device-specific setups, but installing it alone won't make JamesDSP work.

The common late-load path mounts first, then uses a validated firmware stop/start handler, at most once per verified Android session. Repeated soft reboots are supported without a kernel-boot attempt cap; a HAL-only restart does not re-arm recovery. See [lifecycle guards](TEMP-ROOT-RELOAD.md#retry-disable-and-diagnostics). There is no model-based preference or hidden opt-in requirement in this path. It never directly requests an `audioserver` restart, but vendor actions or Binder disconnections can still cause one. Normal boot remains separate, and SELinux stays enforcing.

## Installation

1. Download the module ZIP from [Releases](https://github.com/zahahah/JamesDSPManager/releases).
2. Install it through your compatible root manager. For normal-boot root, follow its reboot procedure. For temp-root/late-load, use its activation flow; do not assume reboot preserves root.
3. Open JamesDSP and **grant it root access**. After late-load activation, allow at least 30 seconds and reopen the app if its initial check ran too early.
4. Enable processing, play some music and try an obvious EQ adjustment at a comfortable volume.

The module includes only our modified **ThePBone-based root app**, package `james.dsp`. There is no classic-app selection or Rootless APK in the ZIP. The signed APK is also attached to the release if you want to download it separately.

Do not enable this module alongside the separate LightningDSP rebrand: they
share the effect UUID and can compete for the same audio chain. This release
does not automatically remove or migrate an installed LightningDSP module/app.

### If JamesDSP is already installed

The installer handles the existing app according to its signing certificate:

- **Same signature:** update in place, preserving app data.
- **Different signature:** ask before replacing the installed app. **Volume Down confirms replacement. Volume Up or a 10-second timeout keeps the existing app.**

After you confirm replacement, the installer attempts to back up the old app's data, installs our APK and restores what it can. If the backup fails, it warns and continues with the replacement you confirmed. **Back up important presets yourself.** Android Keystore-backed data may not survive a signing-key change.

The boot service won't silently uninstall an existing app. Removing the module also leaves the installed JamesDSP app alone.

## Checking the native path

With music playing and JamesDSP enabled, run these commands in a root-capable terminal:

```sh
su -c '/vendor/bin/jdspctl probe'
su -c '/vendor/bin/jdspctl status'
```

A ready native path reports `ready=1`, `protocol=3`, `publication=3` and a writable context. In the status output, accepted and applied generations tell you whether a control update reached the DSP. Increasing processed-frame counters show that the context is processing audio.

Those checks are more useful than simply finding the app in your launcher. They still don't replace listening to a specific adjustment, and the absence of the native service doesn't, by itself, tell you why it failed.

If something goes wrong, include your device model, Android build, root manager, module/app versions and the helper output. Mention whether you're using normal boot or temp-root/late-load, plus any other audio modules. That gives us something to investigate instead of asking the audio stack to confess.

For the current loading contract and runtime limits, see [DUAL-ENTRY-CONTROL-V6.md](DUAL-ENTRY-CONTROL-V6.md). The older [NATIVE-CONTROL.md](NATIVE-CONTROL.md) is historical documentation, not the current packaging guide.

## Building the module ZIP

This repository packages the app and native artifacts. It doesn't compile the native audio library as part of ZIP generation.

Use Python 3, trusted `llvm-readelf`/`readelf` through `PATH` or `JDSP_READELF`, and Android SDK build tools through `ANDROID_HOME`, `ANDROID_SDK_ROOT` or `PATH`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/package_native_control_v6.py
```

The packager verifies native hashes, provenance, APK package/version and the authorized signing certificate before producing the ZIP in `dist/`. The v6 packager accepts `master`, `pixel-test-new-aidl`, `samsung-test-new-aidl` and `reverb-ring-index-optimization`, requiring the exact distribution version and independently verified native import. Historical v4/v5 tooling remains separate. GitHub Actions verifies and packages; it does not install the module or publish a release.

Native development belongs in [LibLightningDSP-OSS](https://github.com/zahahah/LibLightningDSP-OSS). That repository is currently private, but I plan to make it public in the future. App development belongs in [RootJamesDSP](https://github.com/zahahah/RootJamesDSP). For historical release notes, see [changelog.md](changelog.md).

## Credits and licensing

This work builds on JamesDSP and the people who made it possible:

- [JamesDSP by james34602](https://github.com/james34602/JamesDSPManager), the audio processing project behind it all.
- [ThePBone's RootlessJamesDSP](https://github.com/ThePBone/RootlessJamesDSP), the basis of our modified root app.
- [The original JamesDSPManager module](https://github.com/therealahrion/JamesDSPManager) and [ShadoV90's fork](https://github.com/ShadoV90/JamesDSPManager), along with the contributors credited in the project.

The native library's GPL-2.0 license is included in [native-control/LightningDSP-Main-LICENSE.txt](native-control/LightningDSP-Main-LICENSE.txt). See the linked source repositories for their respective licenses and attribution. Our changes don't replace those credits or terms.
