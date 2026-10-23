#!/system/bin/sh
# Read-only owner discovery. Never starts a service or trusts a device model.
# HIDL fallback identifies a unique declared legacy loader, not RPC proof that
# every effect is registered. The recovery script separately verifies init.
[ "${1:-}" = --hidl-pid ] || exit 2
MODPATH=${0%/*}
[ -f "$MODPATH/native-control/v6-candidate.json" ] || exit 1
PROC_ROOT=${JDSP_PROC_ROOT:-/proc}
INIT_ROOT=${JDSP_INIT_ROOT:-/proc/1/root}
# Firmware files are parsed as data. System compatibility matrices are NOT
# manifests and must never be evidence of an implemented vendor interface.
manifest=false
for dir in "$INIT_ROOT/vendor/etc/vintf" "$INIT_ROOT/odm/etc/vintf"; do
    [ -d "$dir" ] || continue
    for file in $(find "$dir" -maxdepth 2 -type f -name '*.xml'); do
        if awk '
            /<hal[[:space:]][^>]*format="hidl"/ { inHal=1; effect=0; factory=0 }
            inHal && /<name>android.hardware.audio.effect<\/name>/ { effect=1 }
            inHal && /IEffectsFactory/ { factory=1 }
            /<\/hal>/ { if (inHal && effect && factory) found=1; inHal=0 }
            END { exit !found }
        ' "$file"; then manifest=true; break; fi
    done
    [ "$manifest" = false ] || break
done
[ "$manifest" = true ] || exit 1
found=
for path in "$PROC_ROOT"/[0-9]*; do
    [ -d "$path" ] || continue
    exe=$(readlink "$path/exe")
    case "$exe" in /vendor/bin/*audio*|/odm/bin/*audio*) ;; *) continue ;; esac
    [ "$(tr -d '\000\n' <"$path/attr/current" 2>/dev/null)" = u:r:hal_audio_default:s0 ] || continue
    grep -qE '/(vendor|odm)/lib64/libeffects[.]so$' "$path/maps" 2>/dev/null || continue
    header=$("${JDSP_OD_BIN:-/system/bin/od}" -An -tx1 -N20 "$path/exe" 2>/dev/null | tr -d ' \n')
    case "$header" in 7f454c460201*0300b700) ;; *) continue ;; esac
    hwbinder=false
    for fd in "$path"/fd/*; do
        case "$(readlink "$fd")" in /dev/hwbinder|/dev/binderfs/hwbinder) hwbinder=true; break ;; esac
    done
    [ "$hwbinder" = true ] || continue
    [ -z "$found" ] || exit 1
    found=${path##*/}
done
[ -n "$found" ] || exit 1
printf '%s\n' "$found"
