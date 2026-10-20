#!/system/bin/sh
# This candidate must preserve the AIDL ABI it was built against. Do not
# rewrite DT_NEEDED names. The test module may explicitly bypass failed checks
# so an AIDL V3 device can be probed; that does not establish compatibility.
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
	if ! printf '%s\n' "$NEEDED_LIST" | grep -Fxq "$REQUIRED"; then
		if [ "${JDSP_EXPERIMENTAL_ALLOW_ABI_MISMATCH:-0}" = 1 ]; then
			echo "EXPERIMENTAL WARNING: driver lacks expected dependency: $REQUIRED"
			continue
		fi
		echo "unexpected AIDL driver ABI: required dependency missing: $REQUIRED" >&2
		return 1
	fi
	discovered=false
	for root in $LIB_ROOTS; do
		if [ -f "$root/$REQUIRED" ]; then
			discovered=true
			break
		fi
	done
	if [ "$discovered" != true ]; then
		if [ "${JDSP_EXPERIMENTAL_ALLOW_ABI_MISMATCH:-0}" = 1 ]; then
			echo "EXPERIMENTAL WARNING: device lacks dependency: $REQUIRED"
			continue
		fi
		echo "device lacks exact AIDL dependency: $REQUIRED" >&2
		return 1
	fi
done

if [ "${JDSP_EXPERIMENTAL_ALLOW_ABI_MISMATCH:-0}" = 1 ]; then
	echo "EXPERIMENTAL AIDL ABI probe enabled; DT_NEEDED was not rewritten"
else
	echo "AIDL dependency versions validated without rewriting DT_NEEDED"
fi
return 0
