### v6.7-beta-1 (LightningDSP rebrand prerelease)

* Start the 6.7 beta series as LightningDSP, previously JamesDSP. Preserve the
  original JamesDSP lineage, contributor credits and licenses.
* Include the blue app theme and launcher icon, root package `com.lightning.dsp`
  (1.6.18/code 63), module `ainur_lightningdsp`, library `lightningdsplib.so`,
  helper `ldspctl` and global `ldsp.control` service as a matched bundle.
* Keep the existing DSP effects, effect UUIDs, dual AIDL/legacy entrypoints,
  protocol 3 and guarded late-load recovery. This version change does not
  rebuild the current app or native artifacts or establish new device support.
* Include the opt-in Extra Post Gain setting for +/-30 dB, off by default with
  the warning "Use it cautiously". The normal range remains +/-15 dB.
* During module flash, identity-check and remove the old `ainur_jamesdsp` module
  and remove the old `james.dsp` package before installing the rebranded app.
  Private data from the old app is not migrated; export important presets first.
* Align documentation with that migration and verify/package LightningDSP in CI.
  The stable JamesDSP 6.6 release remains separate and available.

### v6.6-beta-6.5-soundstage (experimental prerelease)

* Keep centred voices and bass at unity while adjusting stereo side width.
  The existing 30..75 controls now span a gentler 0.8..1.25x side width,
  replacing beta 6.4's exaggerated centre attenuation. Width 50 stays bypass.
* Keep the frequency-independent, stateless Soundstage path. No new crossover,
  delay or virtual surround is added. Centre level can sound louder than 6.4;
  start at a comfortable volume when comparing.
* Prepare finite -30..+30 dB post-gain support in the DSP, legacy parameter,
  global control and matching helper. The APK and its +/-15 dB UI are unchanged;
  an explicit extended-range app option will follow separately. Positive boost
  still reaches the existing limiter and is not guaranteed output loudness.
* Add centre/hard-pan regressions and extended gain boundary checks. Preserve
  AIDL/legacy loading, control protocol, other effects and scheduler recovery.
  Host verification does not replace listening on the target device.

### v6.6-beta-6.4-soundstage (experimental prerelease)

* Replace Soundstage's fast nonlinear multiband centre extraction with a
  frequency-independent linear mid/side matrix, addressing spectral components
  reproduced by bass-plus-treble host tests without other effects or clipping.
* Preserve the existing width controls and pure-mid/pure-side gain curves.
  Width 50 is now an exact, zero-latency bypass; arbitrary stereo output is
  intentionally different from the previous nonlinear effect.
* Remove Soundstage filterbank/envelope work from the callback. Generic
  filterbank users, the other effects, scheduler watcher and APK are unchanged.
* Add spectral, neutral-bypass, bounded-parameter and matrix regression tests.
  The frozen legacy algorithm must fail the spectral gate. Host measurements
  are not a substitute for listening to this new build on Android.

### v6.6-beta-6.3-dsp-scheduler (experimental prerelease)

* Apply the vendor's `RealtimePerformance` profile to the LightningDSP processing
  thread only when the vendor profile is a single, verified task-group mapping
  to its own `ta` scheduler group. Generic AOSP `cpu/rt` behavior and unknown
  vendor profiles are explicitly skipped.
* Watch for the effect thread across late creation and HAL lifecycle changes;
  only threads named `James Audio DS` currently in `fg` are eligible. No core
  pinning, FIFO policy, governor changes, HAL restart, or audio-quality change.
* Include bounded FFT-head selection for eligible short/medium stereo FIRs,
  matrix-kernel iteration cleanup, and Soundstage block-call consolidation.
  Reverb vectorization was rejected after exact state and timing tests failed.
* Host strict/fast/sanitizer response tests passed. Pixel live playback showed
  no audible interference during a temporary one-minute profile test, then the
  original group was restored. This is promising device evidence, not a claim
  that all devices or workloads are glitch-free.

### v6.6-beta-5.3

* Include the Pixel branch's soft-reboot lifecycle guard changes.
* Stop treating a missing AIDL factory listing in the installer as definitive
  incompatibility. Stage the shipped ARM64 AIDL candidate with an explicit
  warning and transport diagnostic instead of aborting or selecting an absent
  legacy payload.
* Keep ABI, artifact integrity and runtime loading/recovery checks. No HIDL
  adapter, driver rebuild or compatibility guarantee is added.

### v6.6-beta-5-pixel-test

* Bring the Pixel integration branch up to the reported-working Samsung test2
  baseline, preserving that Samsung branch and release.
* Allow one audited late-load recovery per verified Android framework session,
  rather than exhausting recovery for the whole kernel boot. Repeated soft
  reboots have no global attempt cap; HAL-only restarts and repeated Retry taps
  do not re-arm the guard.
* Preserve failed-request guards and recheck framework identity before recovery.
  An old AIDL guard can be seeded without a restart only from a matching mapped
  driver with a ready native context and no pending mount generation.
* Keep the signed app, v5 driver and helper unchanged. The Pixel's authorized
  recovery restored registration and processing; ten repeated soft reboots were
  simulated in host tests, not validated unattended on physical hardware.

### v6.6-beta-5-samsung-test2

* Fix rejection of valid Samsung audio-effect XML with mixed CRLF/LF endings,
  which blocked the mount plan before the new driver could be activated.
* Preserve existing vendor lines and their original line endings; keep malformed
  configuration rejection and all-before-mount validation intact.
* Add the exact reported file as a byte-preserved regression fixture, plus CRLF
  preservation and idempotence coverage.
* Keep the v5 driver, matching helper and signed app unchanged. No app reinstall
  or native rebuild is needed.
* Follow-up: the Samsung temp-root collaborator reports test2 works. Record the
  exact configuration and evidence limits in `SAMSUNG-RECOVERY.md`; fresh native
  probe/frame telemetry was not supplied with that report.

### v6.6-beta-5-samsung-test (published experimental prerelease)

* Incorporate AIDL bindings, parcelables and the base effect implementation into
  the new v5 driver, with internal symbols hidden and protocol 3 unchanged.
* Validate the embedded runtime dependency profile without demanding versioned
  audio libraries that should now be inside the driver.
* Independently inspect matching stripped/unstripped artifacts before importing;
  preserve existing payloads if verification fails.
* Require v5-specific provenance and actual ELF checks before packaging, while
  retaining the signed root app and guarded capability-driven late-load bridge.
* Import the new driver and helper from native source `8c70215`, after local
  ELF inspection reproduced the compiler report. The driver has eight direct
  platform dependencies and no versioned audio AIDL DSOs.
* Samsung factory compatibility and audio processing remain unverified.

### v6.6-beta-4-samsung-test2 (published experimental prerelease)

* Replace the model-selected primary recovery with a common AIDL late-load path.
* Bind the driver and live vendor/ODM/system/product/SKU configs into init's
  mount namespace, preserving existing effect entries and configuration labels.
* Stop assuming Pixel stock library names when a vendor AIDL config is absent;
  use a dedicated LightningDSP AIDL config in that case. Stock-effect regressions
  remain a device-test requirement for this fallback.
* Discover the factory owner and audit the firmware stop/start handler rather
  than guessing process names or terminating audioserver.
* Enable one automatic firmware request after the existing ten-second delay on
  capable firmware, without the test1 opt-in requirement. Retry uses the same
  once-per-boot guard. Unsupported handlers fail closed; disable markers work.
* Track pending mount generations and observe mappings beyond the reported
  five-second failure. Mapping is not effect registration or processed audio.
* Keep the signed APK and native driver/helper unchanged; no hardware validation
  is claimed for this candidate.

### v6.6-beta-4-samsung-test1 (published experimental prerelease)

* Add a manual, opt-in recovery path for the reported h8q firmware using its
  audited multi-service stop/start handler, not a direct HAL restart.
* Validate factory ownership, executable identities, current-boot preparation,
  typed policy, namespace overlays, and the firmware handler before a request.
* Replace dependence on Samsung's empty factory dump with a bounded library-load
  check, leaving actual UUID discovery and attachment to the existing app.
* Keep automatic Samsung recovery disabled and limit opted-in recovery to one
  request per boot, including failed requests. No audio-processing claim is made.
* Preserve beta-4's signed APK, native driver and helper without recompilation.

### v6.6-beta-4

* Schedule one validated audio-HAL recovery 10 seconds after KernelSU
  late-load, after typed policy activation is ready.
* Allow one additional user-triggered recovery from the app's Retry screen.
* Keep normal boot unchanged, never restart `audioserver`, and fail closed on
  devices without a verified HAL service/process mapping.
* Bundle the updated root app as versionCode 62. The new automatic recovery
  path requires device validation; Samsung remains unverified.

### v6.6-beta-1

* Keep global ldsp.control primary and legacy control as fallback.
* Refresh dedicated service-label policy after the overlay is mounted, without
  generic service grants, SELinux permissive mode or audio restarts.
* Queue native app controls off the UI thread and preserve fallback on failure.
* Require a published protocol-3 service and one writable context for readiness.
* Bundle root app v1.6.17 code 60; retain the existing v4 library and ldspctl.

### native-control-v4 source candidate (not released)

* Retire the effect-bound parameter transport and v6.5.14 package.
* Restore global ldsp.control and add a root-only vendor-native client.
* Prepare typed policy/helper overlays without automatic audio restarts.
* Block ZIP creation pending newly compiled native artifacts and verified APK.

### v6.5.15-native-control-v4-test (source candidate)

* Carry the global-control-v4 source candidate forward on the Pixel AIDL branch.
* Install only the ThePBone root app; remove the classic-versus-ThePBone choice.
* Use Package Manager's actual update result to detect a signer mismatch, rather
  than pre-comparing certificate metadata.
* Require Volume Down to confirm signer migration; Volume Up or a 10-second
  timeout preserves the installed app. Attempt a temporary data archive before
  confirmed uninstall and restore it with updated ownership/SELinux labels.
* The native-control-v4 binaries are not imported yet; packaging remains gated
  until a matching build artifact and provenance are available.

### v6.5.11-pixel-native-control-v3-test

* Bundle the native-control-v3 library and a signed experimental RootLightningDSP
  AIDL-client APK from branch `pixel-test-new-aidl` (1.6.15, versionCode 57).
* Remove the module's SDK 36+ hard gate; try the systemless overlay on other
  Android/AIDL versions while logging linker mismatches. No ABI rewriting or
  compatibility claim is added; the binary still directly depends on AIDL V4.
* Keep the app on the legacy `AudioEffect` path unless `ldsp.control` reports
  direct app authorization; the provider remains root-authorized by default.
* Test candidate only: no on-device proof of service discovery, app write
  authorization, audio processing, or audible control changes.

### v6.5.10-pixel-builtin-aidl-beta.3

* Run APK update/migration during the module install instead of waiting until
  the next boot.
* For matching signers, install only when the bundled APK versionCode is newer;
  equal or newer installed app versions are left untouched.
* For different signers, ask in the installer. Volume Up confirms uninstall
  and replacement; Volume Down or 30-second timeout keeps the existing app and
  copies the selected APK to Downloads.
* Keep the boot service as a fallback and avoid reinstalling an equal/newer
  app version on subsequent boots.

### v6.5.10-pixel-builtin-aidl-beta.2

* Update an existing `com.lightning.dsp` installation in place when Android accepts
  the module APK's signing certificate, preserving the app data.
* If Android reports a signer mismatch, ask through a system notification and
  wait 30 seconds for Volume Up (remove and replace) or Volume Down (keep).
* Treat timeout as No by default; keep the existing app, copy the new APK to
  `/sdcard/Download/LightningDSP.apk`, and avoid repeating the prompt for
  the same module APK on every boot.
* Host-test both choices, the timeout default, matching-signature update, and
  the one-time decline behavior. Device validation is still pending.

### v6.5.10-pixel-builtin-aidl-beta.1

* Prepare the Android AIDL effect-factory config in the regular KernelSU boot
  path without requiring `KSU_LATE_LOAD`.
* Keep late-load preparation, locking, linker validation, and reload behavior
  unchanged.
* Stage the config and effect through systemless module overlays only.
* Bundle the Zahah-signed LightningDSP 1.6.15 integration APK (version code 56).
  The APK is built from the local 1.6.14 source snapshot with the Volume
  Manager integration, not from upstream 1.6.15 source.
* Host tests pass; this specific regular-boot package has not yet been flashed
  on a device.

### v6.5.9

* LightningDSP works through Android's default effect factory and does not require
  PIXAML. PIXAML remains an optional companion for setups that need AML-specific
  compatibility or other AML-based effects.
* Serialize repeated KernelSU late-load preparation callbacks and replace the
  generated effect XML atomically before Magic Mount-rs applies the overlay.
* Tested on a Pixel 10 Pro XL (`mustang`) running Android 17, KernelSU Next, and
  Magic Mount-rs 4.0.11; the late-load setup remained working through several
  soft reboots.

### v6.5.8

* Make PIXAML optional for late-load. LightningDSP uses `IFactory/default`; the
  guarded refresh no longer depends on PIXAML's standalone AML factory or
  process.
* Start the app installer from the late-load service path before the guarded
  audio refresh. It installs the selected APK only when the exact `com.lightning.dsp`
  package is missing; it never updates, uninstalls, or wipes the user's app
  data.
* Keep everything systemless: the built-in early-boot path stays separate, and
  late-load still uses one guarded Audio HAL refresh.

### v6.5.7

* Stable release for built-in and KernelSU late-load use on the maintainer's
  Pixel 10 Pro XL (`mustang`) with Android 17, KernelSU Next, and Magic
  Mount-rs. Please report device-specific defects through GitHub Issues.
* Require a live PIXAML factory process before the single guarded HAL refresh
  and wait boundedly for audioserver to return.
* Re-sign the Original and ThePBone APKs with the current maintainer
  certificate; app code and package IDs are unchanged.

* v6.5.6-mustang-late-load: correct the stock Volume UUID guard to the value
  observed from the device's AOC `IFactory/default` dump. The previous mismatch
  safely blocked before the one-time audio HAL refresh.

* v6.5.5-mustang-late-load: when the physical vendor AIDL effect XML is absent,
  translate the observed stock `/system/etc/audio_effects.xml` library paths to
  the Pixel's AIDL libraries before adding LightningDSP. The guarded refresh now
  requires the complete observed stock UUID set before and after it.
* v6.5.5-mustang-late-load: set script modes during installation and invoke the
  reload through `sh` so installers that normalize module files to `0644` do
  not suppress the guarded late-load action.

* v6.5.4-late-load-reload-exp: add an experimental KernelSU late-load path that
  requires PIXAML v0.9.5 private-config, mounts the systemless LightningDSP effect,
  patches AIDL NDK dependencies before Magic Mount-rs consumes the tree,
  validates linker resolution, then performs one guarded
  `ctl.restart vendor.audio-hal-aidl` from `service.sh` so `IFactory/default`
  can rediscover the effect. No `killall`, restart loops, audioserver fallback,
  native hooks, or physical partition writes are added.

* v6.5.3-owner-signed: mark KernelSU late-load as `skip_mount` during
  `post-fs-data`, before Magic Mount-rs consumes the module tree; the service
  status alone was too late to prevent a partial effect overlay.
* v6.5.3-owner-signed: Keep the system effect on the built-in early-boot path,
  but skip systemless audio mounts and live process restarts in KernelSU
  late-load. The ZIP contains only the Original and ThePBone root APKs.
* Re-sign both unchanged root APKs with the maintainer key. Existing APKs with
  another certificate cannot be updated in place and are never uninstalled by
  the module; back up app data before manual migration.
* Keep existing `com.lightning.dsp` installation and data when updating or removing
  the module. The ThePBone APK remains v1.6.15; only its signature changed.

### v6.5 RC- 12.29.2025

* Created post-fs-data.sh with apex mounting support if needed
* Service.sh will now seek inside AIDL lib dependency, and modify it to match files in system (not need to add additional dependency files which might break functions of phone)
* JDSP will now automatically launch itself, minimize, grant notification permissions, launch notif. service

### v6.4 - 04.28.2025

* Updated AIDL lib
* Updated PBone APK
* Updated patching script
* AML compatibility for non-pixel AIDL devices

### v6.3 - 03.18.2025

* Force mount if AML is not flashed
* Better compatibility with AML module

### v6.2 - 03.19.2025

* Updated AIDL lib
* Fix odm partition mount for KSU and KSU Next

### v6.1 fix + AIDL - 11.26.2024

* Added AIDL lib
* Changed installer to include devices with AIDL

### v6.1 fix - 10.12.2024

* mmtex fix for magisk 28

### v6.1 - 4.24.2024

* mmtex v3.7 update

### v6.0 - 2.16.2024

* mmtex v3.6 update
* Update pbone apk
* Update ldsp app/libs

### v5.8 - 9.11.2023

* Update pbone apk
* Update ldsp app/libs
* mmtex v3.5 update

### v5.7 - 9.3.2023

* Automatic 32/64 bit lib detection
* mmtex v3.4 update

### v5.6 - 8.24.2023

* Lib bug fix

### v5.5 - 8.21.2023

* Update official apk:

  * Introduce fully functional continuous wavelet transform to dynamic range compander as a experimental trial
  * Use custom implementation of libsamplerate, the file no longer bloat with coefficients

### v5.4 - 8.13.2023

* Update to mmtex v3.3
* Update the thepbone ldsp app

### v5.3 - 8.11.2023

* Update mmtex to v3.2

### v5.2 - 7.28.2023

* Bug fix with osp removal
* Add thepbone APK option

### v5.1 - 7.25.2023

* Bug fix for odm on KSU and magisk delta
* Updated to mmtex v3.1

  * Added support for odm in regular magisk (should fix oneplus device issues) - thanks to @ShadoV90 (https://t.me/ShadoV90) for the fix

### v5.0 - 7.15.2023

* JDSP app updated!:

  * LiveProg update: Clean up EEL RAM disk before new script being loaded
  * EEL engine update:

    * Unify string, thread pool, convolver in one virtual data type
    * Introduce efficient running min/max, median filter
    * Allow STFT window function to be specified
    * Correct STFT phase value(Yield no difference for any previous scripts that depends on relative phase / magnitude only spectral processing)

### v4.8 - 7.10.2023

* Update mmtex to v3.0 - adds support for ksu and magisk delta

### v4.7 - 5.22.2023

* Update mmtex v2.1 - fix for magisk v26+

### v4.6 - 8.4.2022

* Update ldsp libs

### v4.5 - 6.25.2022

* Update ldsp libs

### v4.4 - 1.31.2022

* Update to MMT-Ex v2.0 - support for magisk 24 module update method

### v4.3 - 11.21.2021

* MMT-EX v1.8 update - fix for magisk canary, minmagisk now 20.4

### v4.2 - 9.17.2021

* Always install as data app, no need for system app in older android versions

### v4.1 - 9.9.2021

* Only uninstall app if older than current
* Update mmtex to v1.7
* Fix app update process - uninstall app during zip flash, reboot to complete process

### v4.0 - 9.8.2021

* JDSP app updated!:

  * New app/drivers made open sourced
  * Frequency domain dynamic range compression, give you much crazier compression
  * New dynamic bass boost, proper implementation of signal power detection, proper sample delay apply to multirate analysis and deploy state space filter to achieve boosting filter parameters.
  * Greatly reduce power consumption for some cases, especially when Convolver and Equalizer is used
  * Add user manual to main app

* No more new/old options
* Removed old options

### v3.4 - 5.14.2021

* Update volkey addon

### v3.3 - 11.2.2020

* Update to MMT-Ex v1.6
* Update volkey addon

### v3.2 - 9.9.2020

* Added hidden\_api\_policy workaround for android 11

### v3.1 - 8.25.2020

* New JDSP app updated!:

  * Equalizer interface and actual frequency response mismatch
  * libsndfile replaced with much smaller dr\_libs for impulse response file loading
  * Uses Android 10 API as compiling
  * Additional features:

    * Shrinking impulse response according users thresholds
    * Uses minimum phase transform on impulse response if user needed
    * Customizable channel dependent sample delay at the impulse response beginning

### v3.0 - 4.9.2020

* Fix boot script
* Update to MMT-EX v1.5
* New JDSP app update!:

  * Reduce parameter commit
  * Junked Convolver benchmark system, improve device responsiveness when the device is booting
  * New Dynamic range compressor, full automatic internal parameter adjustment(BUT haven't fully adapt to level depend system(I mean audio framework)
  * New bass boost system, the system automatically detect "Interesting frequency", and adjust filter gain, bandwidth accordingly
  * New FIR Equalizer, enhance interpolator algorithms, more interpolation mode and faster filter generation
  * New convolution algorithm, much faster, much more power saving, remove impulse response cutting feature, however, algorithm not yet fully completed, there will still update that boost performance further.
  * New stereo widening algorithm
  * New BS2B Crossfeed system, with traditional BS2B and a few HRTF based crossfeed(Include the one provided by @Joe0Bloggs )
  * Remove computationally heavy load 7.1 surround simulation, if you still want one, go download Hiby music player!
  * More stable live programming virtual machine, more built-in features that allow user to build very complex audio effect.
  * Processing performance improvement for all effects
  * Arbitrary phase response
  * DDC, Reverb, Arbitrary magnitude response algorithm remain the same
  * Remove all GPL code, allow full close source implementation😂😂😂However live programming compiler/Virtual machine will still go open source, last but not least, all rewritten C API will still go open source for our reference implementation of processing system.

### v2.7 - 1.22.2020

* Update to MMT-Ex v1.3 (Fixes issues on Q)

### v2.6 - 1.17.2020

* Update to MMT-Ex v1.2

### v2.5 - 1.4.2020

* Switched from Unity to MMT-Ex

### v2.4 - 12.30.2019

* Unity v5.0 update

### v2.3 - 8.11.2019

* Unity v4.4 update

### v2.2 - 5.16.2019

* Update to Unity v4.2

### v2.1 - 5.3.2019

* Update to Unity v4.1

### v2.0 - 3.28.2019

* Don't prompt for lib workaround if device that needs it
* Update to unity v4.0

### v1.9.8 - 2.21.2019

* Added Samsung Galaxy S9 and Zuk Z2 Pro to lib workaround
* Made lib workaround a choice so I don't have to keep updating this
* Unity v3.3 update

### v1.9.7 - 1.16.2019

* Forgot to move apk back to priv-app (needed for unity 3.2)

### v1.9.6 - 1.15.2019

* Unity v3.2 update

### v1.9.5 - 1.11.2019

* Unity hotfix

### v1.9.4 - 1.10.2019

* Unity v3.1 update

### v1.9.3 - 1.5.2019

* Unity v3.0 update

### v1.9.2 - 12.23.2018

* Fixed hua/nhua zipname trigger for real this time
* Unity v2.2 update

### v1.9.1 - 12.20.2018

* Fixed hua/nhua zipname trigger
* Fix lib workaround
* Update to Unity v2.1

### v1.9 - 12.18.2018

* Unity v2.0 update
* Fixed limitation in zipname triggers - you can use spaces in the zipname now and trigger is case insensitive
* Improved boot script for user app install - should fix bootloop issues

### v1.8 - 11.21.2018

* Updated JDSP to 11.20.18 release (Change FFT to slower but a commercial friendly implementation, Improve TruCentre separation, Reduce TruCentre latency to 21 ms(from 32 ms), Fix arbitrary response equalizer memory leaks)

### v1.7.5 - 11.8.2018

* Add libstdc++ workaround for pixel 2's, 3's, and essential phone

### v1.7.4 - 10.29.2018

* Switch to manual huawei selection - too much variation with custom roms for consistent huawei device detection

### v1.7.3 - 10.24.2018

* Unity v1.7.2 update
* Bug fix for arm64 devices
* Bug fixes for huawei devices

### v1.7.2 - 10.23.2018

* Fixed awesome boot script for pie - magisk apk stuff is automated once again :)

### v1.7.1 - 10.22.2018

* Fix boot hanging on Pie roms

### v1.7 - 9.20.2018

* Update to unity 1.7.1
* Widen detection for huawei devices

### v1.6.9.1 - 9.16.2018

* Hotfix for Huawei devices

### v1.6.9 -9.13.2018

* Updated JDSP to 9.13 release (adds huawei support, adds auto DDC resampler for device running on 96k sample rate or above, fixes some device volume issue caused by bit depth)

### v1.6.8 - 9.3.2018

* Updated JDSP to 8.31 release

### v1.6.7 - 9.2.2018

* Unity v1.7 update
* Added auto-install/uninstall of apk for magisk only (works for disable/enabling mod in magisk manager as well)
* Add compression to save space/bandwidth

### v1.6.6 - 8.30.2018

* Unity v1.6.1 update

### v1.6.5 - 8.26.2018

* New LightningDSP build (Now supports HTC devices)
* Fixed bit depth problem from HTC and Android Pie
* Upgraded Fast Fourier Transform libraryand  Android NDK

### v1.6.4 - 8.24.2018

* Unity v1.6 update

### v1.6.3 - 7.17.2018

* Unity v1.5.5 update

### v1.6.2 - 5.7.2018

* Unity v1.5.4 update

### v1.6.1 - 4.26.2018

* Unity v1.5.3 update

### v1.6 - 4.16.2018

* Unity v1.5.2 update
* Add AML detection/notification
* Add auto install for apk if in bootmode

### v1.5.9 - 4.12.2018

* Reworking/fixing of audio file patching

### v1.5.8 - 4.12.2018

* Unity v1.5.1 update

### v1.5.7 - 4.12.2018

* Unity v1.5 update

### v1.5.6 - 4.9.2018

* Use dynamic effect removal

### v1.5.5 - 3.30.2018

* Fix effect removals

### v1.5.4 - 3.29.2018

* Unity v1.4.1 update

### v1.5.3 - 3.18.2018

* Unity v1.4 update

### v1.5.2 - 3.1.2018

* Real fix for vol key logic

### v1.5.1 - 2.26.2018

* Quick fix for vol key logic

### v1.5 - 2.25.2018

* Fixed vendor files in bootmode for devices with separate vendor partitions
* Bring back old keycheck method or devices that don't like the newer chainfire method
* Fix seg faults on system installs

### v1.4.2 - 2.17.2018

* Boot script not working, have user do it manually for oreo

### v1.4.1 - 2.16.2018

* Updated ldsp to new version

### v1.4 - 2.16.2018

* Add file backup on system installs
* Fine tune unity prop logic
* Update util\_functions with magisk 15.4 stuff
* Fix music\_helper/sa3d removal in xml files

### v1.3 - 2.12.2018

* Fix vendor cfg creation for devices that don't have it
* Fix sepolicy patching

### v1.2 - 2.10.2018

* Added sa3d removal for samsung devices

### v1.1 - 2.6.2018

* Fixes for xml cfg files

### v1.0 - 2.5.2018

* Initial rerelease

## Credits

* [James34602](https://forum.xda-developers.com/android/apps-games/app-reformed-dsp-manager-t3607970)

## Source Code

* Module [GitHub](https://github.com/therealahrion/LightningDSPManager)

App [GitHub](https://github.com/james34602/LightningDSPManager)
