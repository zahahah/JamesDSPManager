#!/system/bin/sh
# This candidate must preserve the exact AIDL ABI it was built against.
# Do not rewrite DT_NEEDED names to a different interface version.
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

for REQUIRED in \
	android.hardware.audio.effect-V4-ndk.so \
	android.media.audio.common.types-V5-ndk.so \
	android.hardware.common-V2-ndk.so \
	android.hardware.common.fmq-V1-ndk.so; do
	printf '%s\n' "$NEEDED_LIST" | grep -Fxq "$REQUIRED" || {
		echo "unexpected AIDL driver ABI: required dependency missing: $REQUIRED" >&2
		return 1
	}
	discovered=false
	for root in $LIB_ROOTS; do
		if [ -f "$root/$REQUIRED" ]; then
			discovered=true
			break
		fi
	done
	[ "$discovered" = true ] || {
		echo "device lacks exact AIDL dependency: $REQUIRED" >&2
		return 1
	}
done

echo "AIDL dependency versions validated without rewriting DT_NEEDED"
return 0
