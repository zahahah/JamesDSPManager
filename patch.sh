#!/system/bin/sh
# This candidate must preserve the AIDL ABI it was built against. Do not
# rewrite DT_NEEDED names or bypass a dependency failure. Validate the actual
# compiled AIDL versions so separate V3 and V4 builds can be tested honestly.
[ "${AIDL:-false}" = true ] || return 0

MY_LIB="$MOD_VENDOR/lib64/soundfx/libjamesdsp.so"
PATCHELF_BIN=${JDSP_PATCHELF_BIN:-$MODPATH/tools/patchelf}
LIB_ROOTS=${JDSP_SYSTEM_LIB_DIRS:-"/system/lib64 /apex/*/lib64 /vendor/lib64"}

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
