# JamesDSP Manager

**Your music, with a little more say in how it sounds.**

This is our root-only JamesDSP module, paired with a modified version of ThePBone's JamesDSP app and our native audio library. It brings equalization, headphone correction, convolution and other DSP tools into Android's audio effects chain. You keep using your music player. JamesDSP handles the processing underneath.

The current prerelease is **v6.6-beta-4**, with the **JamesDSP root app 1.6.17 (versionCode 62)**. In KernelSU temp-root/late-load, the module waits 10 seconds, then makes one guarded audio-HAL recovery attempt on devices with a verified target. The app's Retry action can request one additional attempt. No path restarts `audioserver`; unknown HAL targets fail closed. The new beta-4 recovery flow still needs device validation, and Samsung compatibility remains unverified. Development is on `pixel-test-new-aidl`; `master` has not received these changes.

[Download the module and APK](https://github.com/zahahah/JamesDSPManager/releases/tag/v6.6-beta-4) · [App source](https://github.com/zahahah/RootJamesDSP) · [Native library source (currently private)](https://github.com/zahahah/LibLightningDSP-OSS)

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

The current global-control setup has been checked on a **Pixel 10 Pro XL (`mustang`) running Android 17, KernelSU and Magic Mount**. On that device, `jdsp.control` was published, the helper reported a writable DSP context, accepted control generations were applied, and processed-frame counters increased during playback.

That's evidence for this setup, not a universal Android compatibility badge.

- The bundled native library is **ARM64** and links against **Audio Effect AIDL V4** libraries. Compatible dependencies and an audio factory that can load the effect are required.
- **Samsung and Audio Effect AIDL V3 compatibility remain unresolved.** There isn't a blanket device-model or V3-version rejection, but letting a device attempt installation doesn't make missing native dependencies disappear.
- The control protocol reports **version 3**. That's the version of our control interface, not the Android Audio Effect AIDL version. They're separate numbers describing different things.
- Root-manager mount behavior, firmware, output routing and other audio mods can affect whether audio reaches the effect. A visible module or a working settings screen isn't proof of processing.

**PIXAML isn't required for JamesDSP's basic effect path on the tested Pixel setup.** This module supplies the library and registers it with Android's default effect factory. PIXAML provides a separate AML service and may matter for other effects or device-specific setups, but installing it alone won't make JamesDSP work.

Late-load support can restart the verified audio HAL once after a delay. It never restarts `audioserver`. The normal boot path and late-load preparation are handled separately, and SELinux stays enforcing.

## Installation

1. Download the module ZIP from [Releases](https://github.com/zahahah/JamesDSPManager/releases).
2. Install it through your compatible root manager, then reboot normally.
3. Open JamesDSP and **grant it root access**.
4. Enable processing, play some music and try an obvious EQ adjustment at a comfortable volume.

The module includes only our modified **ThePBone-based root app**, package `james.dsp`. There is no classic-app selection or Rootless APK in the ZIP. The signed APK is also attached to the release if you want to download it separately.

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

For the deeper contract, authorization and mounting details, see [NATIVE-CONTROL.md](NATIVE-CONTROL.md).

## Building the module ZIP

This repository packages the app and native artifacts. It doesn't compile the native audio library as part of ZIP generation.

With Python 3 and Android SDK build tools available through `ANDROID_HOME`, `ANDROID_SDK_ROOT` or `PATH`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/package_native_control_v4.py
```

The packager verifies the native hashes, provenance, APK package/version and authorized signing certificate before producing the ZIP in `dist/`. It supports `master` and `pixel-test-new-aidl`. GitHub Actions runs the same verification and packaging flow.

Native development belongs in [LibLightningDSP-OSS](https://github.com/zahahah/LibLightningDSP-OSS). That repository is currently private, but I plan to make it public in the future. App development belongs in [RootJamesDSP](https://github.com/zahahah/RootJamesDSP). For historical release notes, see [changelog.md](changelog.md).

## Credits and licensing

This work builds on JamesDSP and the people who made it possible:

- [JamesDSP by james34602](https://github.com/james34602/JamesDSPManager), the audio processing project behind it all.
- [ThePBone's RootlessJamesDSP](https://github.com/ThePBone/RootlessJamesDSP), the basis of our modified root app.
- [The original JamesDSPManager module](https://github.com/therealahrion/JamesDSPManager) and [ShadoV90's fork](https://github.com/ShadoV90/JamesDSPManager), along with the contributors credited in the project.

The native library's GPL-2.0 license is included in [native-control/LightningDSP-Main-LICENSE.txt](native-control/LightningDSP-Main-LICENSE.txt). See the linked source repositories for their respective licenses and attribution. Our changes don't replace those credits or terms.
