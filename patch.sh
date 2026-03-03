#!/system/bin/sh
if [ "$AIDL" = true ];then
MY_LIB="$MOD_VENDOR/lib64/soundfx/libjamesdsp.so"
PATCHELF="$MODPATH/tools/patchelf"
chmod +x "$PATCHELF"

find_system_lib() {
find /system/lib64 /apex/*/lib64 /vendor/lib64 -name "$1-V*-ndk.so" 2>/dev/null | sort | tail -n 1 | xargs basename 2>/dev/null
}

LIB_LIST="android.hardware.audio.effect android.media.audio.common.types android.hardware.common android.hardware.common.fmq"
	for LIB_NAME in $LIB_LIST; do
		CURRENT_NEEDED=$("$PATCHELF" --print-needed "$MY_LIB" | grep "$LIB_NAME" | head -n 1)
		SYSTEM_AVAILABLE=$(find_system_lib "$LIB_NAME")
		if [ -n "$SYSTEM_AVAILABLE" ] && [ -n "$CURRENT_NEEDED" ]; then
			if [ "$CURRENT_NEEDED" != "$SYSTEM_AVAILABLE" ]; then
				"$PATCHELF" --replace-needed "$CURRENT_NEEDED" "$SYSTEM_AVAILABLE" "$MY_LIB"
				echo " -- Patched $LIB_NAME: $CURRENT_NEEDED -> $SYSTEM_AVAILABLE -- "
				sync
			fi
		fi
	done
fi
