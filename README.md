# LightningDSP Manager

**Your music, with a little more say in how it sounds.**

This is our root-only LightningDSP module, paired with a modified version of ThePBone's LightningDSP app and our native audio library. It brings equalization, headphone correction, convolution and other DSP tools into Android's audio effects chain. You keep using your music player. LightningDSP handles the processing underneath.

This is the **`ldsp-rebrand` experimental branch**. The module, app integration and native control service use the LightningDSP names. The app package is `com.lightning.dsp` and the module ID is `ainur_lightningdsp`. On installation, the previous `ainur_jamesdsp` module is identity-checked, disabled, and removed so its payload cannot compete with LightningDSP. The old `james.dsp` app is removed before installing the new package; its private app data is not migrated.

LightningDSP is the new name for our maintained JamesDSP-based project,
inspired by the original JamesDSP work. The rebrand updates the product identity,
not the history: original contributors and license notices remain credited below
and in the source repositories.

The prerelease target is **v6.6-beta-7-ldsp**. It carries one ARM64 dual-entry native effect driver and `ldspctl`; both the AIDL effect implementation and the legacy effect-factory adapter are included in the same binary. Static ELF and host-test results are recorded in the module. Actual Android factory discovery, audio processing and device compatibility remain unverified for this build.

[App source](https://github.com/zahahah/RootJamesDSP) · [Native library source (currently private)](https://github.com/zahahah/LibLightningDSP-OSS)

## What can it do?

LightningDSP gives you more than a few bass and treble sliders:

- **FIR and IIR equalization** to shape the frequency response.
- **Convolution** to apply impulse responses, including headphone or speaker correction profiles.
- **DDC/VDC correction** for compatible headphone profiles.
- **Dynamics processing and output controls**, including a compander, limiter and post-gain.
- **Crossfeed, stereo enhancement, bass boost, reverb and tube-style effects** for more specific adjustments.
- **Live programmable processing** if you enjoy going beyond the built-in controls.

It's a collection of tools, not a preset that automatically makes everything sound better. Start with a small adjustment, listen, then decide what actually helps. Turning every switch on is a valid experiment, but not necessarily a good listening strategy.

## What's different in this fork?

We're keeping the familiar ThePBone-based interface while changing how the app talks to the audio engine. The main control path is now **`ldsp.control`**, a global **Binder service** provided by `lightningdsplib.so`.

There are three parts to the setup:

1. **The module** makes the native library and audio configuration available through a systemless mount overlay. It doesn't permanently rewrite your physical `/system` or `/vendor` partitions.
2. **Android's audio HAL** loads LightningDSP as an audio effect. This is where the native engine processes audio, rather than inside the settings screen.
3. **The app** changes the engine's settings. For supported native controls, it uses the root helper `ldspctl` to communicate with `ldsp.control`.

The short version:

```text
App settings → ldspctl (root) → ldsp.control → LightningDSP in the audio HAL
                                                        ↓
                                                  Processed audio
```

That diagram describes the control path. Audio samples aren't being sent through the root helper. Android's `AudioEffect` mechanism still handles effect attachment and lifecycle.

### Native first, legacy when needed

The app checks the native control path first. **Power, post-gain and FIR EQ** can use `ldsp.control`; features outside that contract still use the existing Android effect-parameter path. If native control isn't available or a supported operation fails, the legacy path remains a fallback.

So this isn't “we removed everything old and hoped for the best.” We're moving the controls we support to the new path while keeping the rest of LightningDSP usable.

The native service currently accepts writes from **root only**. Installing the module isn't enough: you also need to grant the **LightningDSP app** root access in your root manager. Granting root to Termux or ADB doesn't grant it to LightningDSP.

## Compatibility: what we've actually checked

This rebrand build packages one ARM64 **dual-entry** effect driver: it contains both the embedded Audio Effect AIDL V4 implementation and the legacy effect-factory entry point. The native artifact passed host tests and static ELF checks. Those checks do **not** prove that a device's factory discovers the effect, loads it, or processes audio. No physical-device validation has been completed for this build.

The control protocol version is **3**; that is separate from Android's Audio Effect AIDL version. Root-manager mount behavior, firmware, output routing and other audio modules can all affect whether audio reaches the effect. A visible module or settings screen is not proof of processing.

**PIXAML isn't required for LightningDSP's basic effect path on the tested Pixel setup.** This module supplies the library and registers it with Android's default effect factory. PIXAML provides a separate AML service and may matter for other effects or device-specific setups, but installing it alone won't make LightningDSP work.

The common late-load path mounts first, then uses a validated firmware stop/start handler, at most once per verified Android session. Repeated soft reboots are supported without a kernel-boot attempt cap; a HAL-only restart does not re-arm recovery. See [lifecycle guards](TEMP-ROOT-RELOAD.md#retry-disable-and-diagnostics). There is no model-based preference or hidden opt-in requirement in this path. It never directly requests an `audioserver` restart, but vendor actions or Binder disconnections can still cause one. Normal boot remains separate, and SELinux stays enforcing.

## Installation

1. Download the module ZIP from [Releases](https://github.com/zahahah/JamesDSPManager/releases).
2. Install it through your compatible root manager. For normal-boot root, follow its reboot procedure. For temp-root/late-load, use its activation flow; do not assume reboot preserves root.
3. Open LightningDSP and **grant it root access**. After late-load activation, allow at least 30 seconds and reopen the app if its initial check ran too early.
4. Enable processing, play some music and try an obvious EQ adjustment at a comfortable volume.

The module includes only our modified **ThePBone-based root app**, package `com.lightning.dsp`. There is no classic-app selection or Rootless APK in the ZIP. The signed APK is also attached to the release if you want to download it separately.

### Migrating from JamesDSP

The installer verifies the module ID, marks the old `ainur_jamesdsp` module disabled, then removes its directory. Any already-active mounts are replaced on the normal reboot after installation. It also removes the old `james.dsp` app and installs `com.lightning.dsp`. The package ID changed, so Android keeps their app data separate; this migration does not copy the old app's private data. Export or back up presets before installing if you need them. The normal update path for an already-installed `com.lightning.dsp` remains unchanged: matching signatures update in place; a signature mismatch still requires the existing volume-key confirmation and best-effort backup flow.

The boot service won't silently uninstall an existing app. Removing the module also leaves the installed LightningDSP app alone.

## Checking the native path

With music playing and LightningDSP enabled, run these commands in a root-capable terminal:

```sh
su -c '/vendor/bin/ldspctl probe'
su -c '/vendor/bin/ldspctl status'
```

A ready native path reports `ready=1`, `protocol=3`, `publication=3` and a writable context. In the status output, accepted and applied generations tell you whether a control update reached the DSP. Increasing processed-frame counters show that the context is processing audio.

Those checks are more useful than simply finding the app in your launcher. They still don't replace listening to a specific adjustment, and the absence of the native service doesn't, by itself, tell you why it failed.

If something goes wrong, include your device model, Android build, root manager, module/app versions and the helper output. Mention whether you're using normal boot or temp-root/late-load, plus any other audio modules. That gives us something to investigate instead of asking the audio stack to confess.

For the deeper contract, authorization and mounting details, see [LIGHTNINGDSP-CONTROL.md](LIGHTNINGDSP-CONTROL.md).

## Building the module ZIP

This repository packages the app and native artifacts. It doesn't compile the native audio library as part of ZIP generation.

Use Python 3, trusted `llvm-readelf`/`readelf` through `PATH` or `LDSP_READELF`, and Android SDK build tools through `ANDROID_HOME`, `ANDROID_SDK_ROOT` or `PATH`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
LDSP_READELF=llvm-readelf ANDROID_HOME="$ANDROID_HOME" python3 tools/package_lightningdsp.py
```

The LightningDSP packager verifies native hashes, provenance, APK package/version and the authorized signing certificate before producing the ZIP in `dist/`. Historical JamesDSP v4/v5 packagers remain separate and are not used for this prerelease.

Native development belongs in [LibLightningDSP-OSS](https://github.com/zahahah/LibLightningDSP-OSS). That repository is currently private, but I plan to make it public in the future. App development belongs in [RootLightningDSP](https://github.com/zahahah/RootLightningDSP). For historical release notes, see [changelog.md](changelog.md).

## Contributors

Previously JamesDSP. Maintained by **lightning zahah**. Contributors to the earlier project and module: james34602, zackptg5, ahrion, anonymix007 and ShadoV90.

## Credits and licensing

LightningDSP is the current project name, inspired by the original JamesDSP
project. The rebrand does not replace or erase that lineage. Our thanks go to:

- [JamesDSP by James Fung (james34602)](https://github.com/james34602/JamesDSPManager),
  the original audio-processing project behind this work.
- [ThePBone's RootlessJamesDSP](https://github.com/ThePBone/RootlessJamesDSP), the original upstream basis of our modified root app.
- [The original JamesDSPManager module](https://github.com/therealahrion/JamesDSPManager)
  and [ShadoV90's JamesDSPManager fork](https://github.com/ShadoV90/JamesDSPManager),
  along with the contributors credited in those projects.

The native library's GPL-2.0 license is included in [native-control/LightningDSP-Main-LICENSE.txt](native-control/LightningDSP-Main-LICENSE.txt). See the linked source repositories for their respective licenses and attribution. Our changes don't replace those credits or terms.
