#!/system/bin/sh
# This candidate must preserve the AIDL ABI it was built against. Do not
# rewrite DT_NEEDED names or bypass a dependency failure. Validate the actual
# compiled AIDL versions so separate V3 and V4 builds can be tested honestly.
[ "${AIDL:-false}" = true ] || return 0

MY_LIB="$MOD_VENDOR/lib64/soundfx/lightningdsplib.so"
PATCHELF_BIN=${LDSP_PATCHELF_BIN:-$MODPATH/tools/patchelf}
LIB_ROOTS=${LDSP_SYSTEM_LIB_DIRS:-"/system/lib64 /system/lib64/bootstrap /apex/*/lib64 /apex/*/lib64/bionic /vendor/lib64"}

[ -f "$MY_LIB" ] || {
	echo "AIDL driver missing: $MY_LIB" >&2
	return 1
}
[ -x "$PATCHELF_BIN" ] || {
	echo "patchelf inspection tool missing" >&2
	return 1
}

NEEDED_LIST=$("$PATCHELF_BIN" --print-needed "$MY_LIB") || {
	echo "cannot inspect AIDL driver dependencies" >&2
	return 1
}

# An imported embedded profile must not demand the shared AIDL libraries it
# compiled into the driver. Keep a strict runtime allowlist and still check
# every direct system dependency; this is not an ABI or linker-namespace proof.
if [ -f "$MODPATH/native-control/v5-candidate.json" ] || [ -f "$MODPATH/native-control/ldsp-candidate.json" ]; then
    embedded_profile=v5
    [ ! -f "$MODPATH/native-control/ldsp-candidate.json" ] || embedded_profile=LightningDSP
    [ -n "$NEEDED_LIST" ] || { echo "embedded $embedded_profile driver has no runtime dependencies" >&2; return 1; }
    has_binder=false
    has_libc=false
    for REQUIRED in $NEEDED_LIST; do
        case "$REQUIRED" in
            libbinder_ndk.so) has_binder=true ;;
            libc.so) has_libc=true ;;
            liblog.so|libbase.so|libfmq.so|libcutils.so|libm.so|libdl.so) ;;
            *) echo "forbidden embedded $embedded_profile runtime dependency: $REQUIRED" >&2; return 1 ;;
        esac
        discovered=false
        for root in $LIB_ROOTS; do
            if [ -f "$root/$REQUIRED" ]; then discovered=true; break; fi
        done
        [ "$discovered" = true ] || {
            echo "device lacks exact embedded-driver dependency: $REQUIRED" >&2
            return 1
        }
    done
    [ "$has_binder" = true ] && [ "$has_libc" = true ] || {
        echo "embedded $embedded_profile driver lacks required Binder/libc dependencies" >&2
        return 1
    }
    echo "embedded $embedded_profile runtime dependencies validated without rewriting DT_NEEDED"
    return 0
fi

for FAMILY in android.hardware.audio.effect android.media.audio.common.types android.hardware.common android.hardware.common.fmq; do
    REQUIRED=$(printf '%s\n' "$NEEDED_LIST" | awk -v family="$FAMILY" '
        index($0, family "-V") == 1 && $0 ~ /-V[0-9]+-ndk[.]so$/ { print }
    ')
    [ -n "$REQUIRED" ] && [ "$(printf '%s\n' "$REQUIRED" | wc -l | tr -d ' ')" = 1 ] || {
        echo "unexpected AIDL driver ABI: required dependency family missing or ambiguous: $FAMILY" >&2
        return 1
    }
    discovered=false
    for root in $LIB_ROOTS; do
        if [ -f "$root/$REQUIRED" ]; then discovered=true; break; fi
    done
    if [ "$discovered" != true ]; then
        echo "device lacks exact AIDL dependency: $REQUIRED" >&2
        return 1
    fi
done

echo "AIDL dependency versions validated without rewriting DT_NEEDED"
return 0
