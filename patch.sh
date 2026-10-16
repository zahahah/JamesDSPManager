#!/system/bin/sh

patch_aidl_dependencies() {
	[ "$AIDL" = true ] || return 0
	# Preserve historical adaptation except for Samsung h8q late-load, where
	# exact SONAMEs are the safer default. The experimental Samsung test ZIP may
	# explicitly opt back in with its test-only marker; callers can always
	# override either default through JDSP_PATCH_AIDL_NDK.
	PATCH_DEFAULT=1
	if [ "${KSU_LATE_LOAD:-0}" = 1 ] &&
		[ "${JDSP_COMPAT_PROFILE:-}" = samsung_h8q ]; then
		PATCH_DEFAULT=0
		module_version=$(sed -n 's/^versionCode=//p' "$MODPATH/module.prop" 2>/dev/null | head -n 1)
		[ "$module_version" = 127 ] && \
			[ -f "$MODPATH/.test18-samsung-ndk-retarget" ] && PATCH_DEFAULT=1
	fi
	PATCH_AIDL_NDK=${JDSP_PATCH_AIDL_NDK:-$PATCH_DEFAULT}
	[ "$PATCH_AIDL_NDK" = 1 ] || {
		echo " -- AIDL NDK SONAME patch skipped for profile ${JDSP_COMPAT_PROFILE:-unknown} -- "
		return 0
	}
	MY_LIBS="$MOD_VENDOR/lib64/soundfx/libjamesdsp.so"
	if [ -f "$MOD_VENDOR/lib64/soundfx/libjamesdsp_real.so" ]; then
		MY_LIBS="$MY_LIBS $MOD_VENDOR/lib64/soundfx/libjamesdsp_real.so"
	fi
	PATCHELF="$MODPATH/tools/patchelf"
	chmod +x "$PATCHELF" || return 1
	for MY_LIB in $MY_LIBS; do
		needed=$("$PATCHELF" --print-needed "$MY_LIB") || {
			echo " -- AIDL NDK SONAME patch failed: print-needed $MY_LIB -- "
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
					echo " -- AIDL NDK SONAME patch failed: replace-needed $LIB_NAME in $MY_LIB -- "
					return 1
				}
				echo " -- Patched ${MY_LIB##*/} $LIB_NAME: $CURRENT_NEEDED -> $SYSTEM_AVAILABLE -- "
				sync
			fi
		done
	done
}

patch_aidl_dependencies
patch_result=$?
return "$patch_result" 2>/dev/null || exit "$patch_result"
