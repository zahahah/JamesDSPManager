#!/system/bin/sh
SKIPUNZIP=1

# This file is sourced by a module installer, never run as a host setup script.
if [ -z "${MODPATH:-}" ] || [ "$MODPATH" = / ] || [ -z "${ZIPFILE:-}" ] ||
    ! command -v abort >/dev/null 2>&1 || ! command -v set_perm >/dev/null 2>&1; then
    printf 'Missing Android module installer context\n' >&2
    exit 1
fi

[ "${BOOTMODE:-false}" = true ] || abort 'Install from a running Android system only'
[ -n "${KSU:-}" ] || abort 'This candidate is scoped to KernelSU Samsung testing'
[ "$(getprop ro.product.manufacturer | tr '[:upper:]' '[:lower:]')" = samsung ] || abort 'Samsung-only candidate; keep the existing Pixel module'
case "$(getprop ro.product.cpu.abilist64)" in
    *arm64-v8a*) ;;
    *) abort 'An Android ARM64 audio process is required' ;;
esac
service check android.hardware.audio.effect.IFactory/default 2>/dev/null | grep -q ': found' || abort 'Default AIDL effect factory unavailable'

# Do not combine this runtime with files retained by a non-clean update path.
for legacy in audio-reload.sh patch.sh sepolicy.rule jdsp_app.sh; do
    [ ! -e "$MODPATH/$legacy" ] || abort "Mixed legacy install directory ($legacy); refusing extraction"
done

unzip -o "$ZIPFILE" -x 'META-INF/*' -d "$MODPATH" >&2 || abort 'Extraction failed'
touch "$MODPATH/skip_mount" "$MODPATH/skip_mountify"
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in runtime.sh late-load.sh post-fs-data.sh service.sh uninstall.sh; do
    set_perm "$MODPATH/$script" 0 0 0755
done
ui_print 'Direct-driver development candidate; late-load service activation only, no audio restart.'
ui_print 'Do not enable DFRoot automatic reboot for this candidate as a test procedure.'
ui_print 'Existing apps and data remain untouched. Read README.md before device testing.'
