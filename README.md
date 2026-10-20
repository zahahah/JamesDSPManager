# JamesDSPManager

Root-only module for JamesDSPManager. Upstream project: [JamesDSPManager](https://github.com/therealahrion/JamesDSPManager). App source: [James34602/JamesDSPManager](https://github.com/james34602/JamesDSPManager).

## Stable release: v6.5.9

I've tested this release on a Pixel 10 Pro XL (`mustang`) running Android 17,
KernelSU Next, and Magic Mount-rs 4.0.11. The late-load setup stayed working
through several soft reboots. It is stable in this setup, but audio behavior
can vary with firmware and root stage. Please report defects with device/build
details, root mode, logs, and steps to reproduce.

JamesDSP does not depend on PIXAML. Its module provides `libjamesdsp.so` and
adds the effect to the XML used by Android's `IFactory/default`. On my Pixel,
that is enough for the JamesDSP app to load and use the effect on its own.
PIXAML provides a separate AML service (`IFactory/aml`); Android does not
automatically route JamesDSP through it. Some devices or setups may still need
PIXAML for AML-specific compatibility or other AML-based effects, but that is
separate from JamesDSP's basic effect path. Installing PIXAML alone does not
make JamesDSP available.

During KernelSU late-load, repeated preparation callbacks are serialized with a
lock, and the generated XML is replaced atomically before Magic Mount-rs applies
the overlay. The single late-load audio refresh is guarded by the default
factory, the expected stock descriptors, and a marker scoped to the current HAL
process instance. There is no restart loop, `killall`, native hook, or write to
the physical system/vendor partitions. The built-in early-boot path stays
separate.

The module includes and stages only the modified ThePBone root APK. At module
installation, it attempts a normal Package Manager update of an installed
`james.dsp`; Android validates the signing identity, and a compatible signature
updates in place without uninstalling or clearing data. If signatures differ,
the installer asks for a volume-key decision for 10 seconds: volume down
confirms uninstall-and-reinstall, volume up declines, and no response keeps the
existing app. Confirmed uninstall may erase private app data, so back up
presets/data first. If Package Manager is unavailable during flashing, a
missing app is installed after boot. The bundled app is the modified
ThePBone-based root build, version 1.6.15, version code 58, signed with the
maintainer certificate. The classic 9.5 APK is not offered or shipped.

## Build and test

Run the host tests and build the release ZIP with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/package_6910_beta2.py
```

For the previous release notes, see [changelog.md](changelog.md).
