#!/system/bin/sh

patch_aidl_dependencies() {
	[ "$AIDL" = true ] || return 0
	# Preserve historical early-boot adaptation. Portable late-load may retarget
	# module-local versioned NDK SONAMEs to installed versions; the caller's
	# linker check remains the fail-closed compatibility gate.
	if [ "${KSU_LATE_LOAD:-0}" = 1 ] && [ "${JDSP_COMPAT_PROFILE:-}" != mustang ]; then
		PATCH_AIDL_NDK=${JDSP_PATCH_AIDL_NDK:-1}
	else
		PATCH_AIDL_NDK=${JDSP_PATCH_AIDL_NDK:-1}
	fi
	[ "$PATCH_AIDL_NDK" = 1 ] || {
		echo " -- AIDL NDK SONAME patch skipped for profile ${JDSP_COMPAT_PROFILE:-unknown} -- "
		return 0
	}
	MY_LIB="$MOD_VENDOR/lib64/soundfx/libjamesdsp.so"
	PATCHELF="$MODPATH/tools/patchelf"
	chmod +x "$PATCHELF" || return 1
	needed=$("$PATCHELF" --print-needed "$MY_LIB") || {
		echo " -- AIDL NDK SONAME patch failed: print-needed -- "
		return 1
	}
	for LIB_NAME in android.hardware.audio.effect android.media.audio.common.types android.hardware.common android.hardware.common.fmq; do
		CURRENT_NEEDED=$(printf '%s\n' "$needed" | grep -F "$LIB_NAME-V" | head -n 1)
		[ -n "$CURRENT_NEEDED" ] || continue
		SYSTEM_AVAILABLE=""
		SYSTEM_VERSION=-1
		for candidate in $(find /system/lib64 /apex/*/lib64 /vendor/lib64 -name "$LIB_NAME-V*-ndk.so" 2>/dev/null); do
			candidate_name=${candidate##*/}
			candidate_version=${candidate_name#"$LIB_NAME-V"}
			candidate_version=${candidate_version%-ndk.so}
			case "$candidate_version" in ''|*[!0-9]*) continue ;; esac
			if [ "$candidate_version" -gt "$SYSTEM_VERSION" ]; then
				SYSTEM_VERSION=$candidate_version
				SYSTEM_AVAILABLE=$candidate_name
			fi
		done
		[ -n "$SYSTEM_AVAILABLE" ] || continue
		if [ "$CURRENT_NEEDED" != "$SYSTEM_AVAILABLE" ]; then
			"$PATCHELF" --replace-needed "$CURRENT_NEEDED" "$SYSTEM_AVAILABLE" "$MY_LIB" || {
				echo " -- AIDL NDK SONAME patch failed: replace-needed $LIB_NAME -- "
				return 1
			}
			echo " -- Patched $LIB_NAME: $CURRENT_NEEDED -> $SYSTEM_AVAILABLE -- "
			sync
		fi
	done
}

patch_aidl_dependencies
patch_result=$?
return "$patch_result" 2>/dev/null || exit "$patch_result"
