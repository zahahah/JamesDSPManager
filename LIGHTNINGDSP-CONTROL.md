# LightningDSP native control and module contract

## Shipped contract

- Effect library: `lightningdsplib.so` (`SONAME` matches the installed filename).
- Root helper: `ldspctl`, staged at `/vendor/bin/ldspctl`.
- Global service: `ldsp.control`.
- AIDL descriptor: `lightning.dsp.ILightningDspControl`.
- Control protocol: 3.
- Effect UUIDs stay unchanged so Android effect attachment and saved app settings
  continue to address the same effect.
- The one ARM64 driver includes both the AIDL Effect V4 entry point and legacy
  `AELI` entry point. This does not make a V4 AIDL dependency equivalent to a
  V3 ABI; it means the legacy loader path is also present in this binary.

The module ID is `ainur_lightningdsp`. During installation, the installer checks
that an existing `ainur_jamesdsp` directory has the expected module ID, writes
its disable marker, and removes that directory so its payload cannot compete
with LightningDSP. This is not a reversible disable-only migration; already
active mounts are replaced on the normal reboot after installation. The app
uses `com.lightning.dsp`; during an explicit module flash, the installer removes
the old `james.dsp` package for its Android users before installing the new app.
The old package's private data is not migrated. Same-package signature changes
continue to use the separate volume-key confirmation and best-effort backup
flow. The boot service does not silently uninstall an installed app.

## Data and control flow

The Android audio factory loads the library through the module's systemless
configuration overlay. The app attaches through `AudioEffect`; `ldspctl` only
transports root-authorized control requests over Binder. It never carries audio
samples. Library discovery, successful loading, effect registration, attachment,
service publication, applied controls and processed audio are separate checks.

The native service currently supports enable/power, post-gain up to +/-30 dB,
and prepared FIR EQ. Other effect parameters continue to use the existing
AudioEffect route. Native writes require root and the service validates caller,
context, handle, parameter and lifecycle state. SELinux stays enforcing; the
module installs only the typed `ldsp_control_service` policy. Its historical
default-service-label opt-in remains disabled.

## Late-load behavior

The late-load path stages the systemless library/configuration, validates the
ELF dependencies without rewriting `DT_NEEDED`, and uses guarded recovery only
for an identified audio service. It does not restart `servicemanager`, disable
SELinux, or blindly choose a HAL. AIDL configuration mount and Binder service
readiness do not prove successful effect processing. Recovery status is
diagnostic; no current physical-device test is claimed by the build report.

## Build evidence and limits

The module's `native-control/ldsp-candidate.json` and
`native-control/ldsp-build-provenance.json` pin the source and the exact driver,
helper, APK and redistribution notices. Host DSP/control tests passed. Nine of
ten requested Soong host tests passed; `ldsp_kernel_binder_test` was skipped
(exit 77) because the isolated host did not provide the dedicated Binder test
environment. ELF inspection confirmed AArch64, `lightningdsplib.so`, `DF_1_NODELETE`,
the expected factory exports and the allowed direct dependencies. No Android
device was used for this build validation.
