#!/system/bin/sh
[ -z "$MODPATH" ] && MODPATH="${0%/*}"

PKG="james.dsp"
LOGFILE="$MODPATH/logs/jamesdsp_app_install.log"
INTERNAL_PATH="/storage/emulated/0/JamesDSPManager.apk"
SDCARD_PATH=${JDSP_SDCARD_PATH:-/storage/emulated/0}
TEMP_INSTALL_PATH=${JDSP_TEMP_INSTALL_PATH:-/cache/JamesDSPManager.apk}
CMD_BIN=${JDSP_CMD_BIN:-/system/bin/cmd}
GETEVENT_BIN=${JDSP_GETEVENT_BIN:-/system/bin/getevent}
SIGNATURE_DECLINED_MARKER="$MODPATH/.jdsp_apk_signature_declined"
PROMPT_TIMEOUT=30

# Prefer cmd package when Android exposes it.
if [ -x "$CMD_BIN" ]; then
	PM_CMD="$CMD_BIN package"
	METHOD_LOG="cmd package (Android 7+)"
else
	PM_CMD="pm"
	METHOD_LOG="pm (Android <7)"
fi

mkdir -p "${LOGFILE%/*}"
echo "--- JamesDSP installer through $METHOD_LOG ---" > "$LOGFILE"

# Wait until package manager is ready.
until [ "$(getprop sys.boot_completed)" = "1" ]; do
	sleep 1
done

notify_user() {
	[ -x "$CMD_BIN" ] || return 1
	"$CMD_BIN" notification post -t "$1" "jamesdsp-apk-migration" "$2" \
		>>"$LOGFILE" 2>&1
}

copy_apk_to_sdcard() {
	local source_file="$1"
	local destination="$SDCARD_PATH/Download/JamesDSPManager.apk"

	if [ -f "$destination" ] && cmp -s "$source_file" "$destination"; then
		echo "The existing app was kept; the same APK is already staged at $destination" >> "$LOGFILE"
		return 0
	fi

	if mkdir -p "$SDCARD_PATH/Download" && cp -f "$source_file" "$destination"; then
		chmod 644 "$destination" 2>/dev/null
		echo "The existing app was kept. New APK copied to $destination" >> "$LOGFILE"
		notify_user "JamesDSP APK was not replaced" \
			"The existing app was kept. The new APK is at $destination and can be installed manually."
		return 0
	fi
	echo "ERROR: Could not copy new APK to $destination" >> "$LOGFILE"
	notify_user "JamesDSP APK was not replaced" \
		"The existing app was kept, but copying the new APK to $destination failed. Check the module install log."
	return 1
}

get_user_list() {
	local users
	users=$($PM_CMD list users 2>/dev/null | grep -o '{[0-9]*' | grep -o '[0-9]*')
	[ -n "$users" ] || users=0
	echo "$users"
}

is_package_installed() {
	$PM_CMD list packages 2>/dev/null | grep -Fqx "package:$PKG"
}

apk_fingerprint() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		cksum "$1" | awk '{print $1 ":" $2}'
	fi
}

installed_apk_matches() {
	local installed_path
	installed_path=$($PM_CMD path "$PKG" 2>/dev/null | sed -n 's/^package://p' | head -n 1)
	[ -n "$installed_path" ] && [ -f "$installed_path" ] && \
		[ "$(apk_fingerprint "$installed_path")" = "$(apk_fingerprint "$1")" ]
}

ask_to_replace_different_signature() {
	local remaining=$PROMPT_TIMEOUT
	local event

	echo "Different signing certificate detected. Waiting up to ${PROMPT_TIMEOUT}s for volume-key choice." >> "$LOGFILE"
	notify_user "JamesDSP signature changed" \
		"Volume Up: remove the old app and install the new one (app data will be removed). Volume Down or no response in ${PROMPT_TIMEOUT}s: keep the old app and copy the new APK to Downloads."

	while [ "$remaining" -gt 0 ]; do
		event=$(timeout 1 "$GETEVENT_BIN" -lqc 1 2>/dev/null)
		case "$event" in
			*KEY_VOLUMEUP*DOWN*)
				echo "Volume Up selected: user accepted removal of the existing app." >> "$LOGFILE"
				return 0
				;;
			*KEY_VOLUMEDOWN*DOWN*)
				echo "Volume Down selected: keeping the existing app." >> "$LOGFILE"
				return 1
				;;
		esac
		remaining=$((remaining - 1))
	done

	echo "No volume-key response; keeping the existing app by default." >> "$LOGFILE"
	return 1
}

uninstall_existing_app() {
	local user_id
	local output
	local result
	local removed=0
	local failed=0

	for user_id in $(get_user_list); do
		if ! $PM_CMD list packages --user "$user_id" 2>/dev/null | grep -Fqx "package:$PKG"; then
			continue
		fi
		output=$($PM_CMD uninstall --user "$user_id" "$PKG" 2>&1)
		result=$?
		echo "Uninstall result (User $user_id): $output (Code: $result)" >> "$LOGFILE"
		if [ "$result" -eq 0 ]; then
			removed=$((removed + 1))
		else
			failed=$((failed + 1))
		fi
	done
	[ "$removed" -gt 0 ] && [ "$failed" -eq 0 ]
}

install_for_all_users() {
	local source_file="$1"
	local user_id
	local output
	local result
	local installed=0
	local signature_mismatch=false

	echo "--- Installing JDSP app from: $source_file ---" >> "$LOGFILE"
	if ! cp "$source_file" "$TEMP_INSTALL_PATH"; then
		echo "ERROR: Failed to copy APK to $TEMP_INSTALL_PATH" >> "$LOGFILE"
		return 1
	fi
	chmod 644 "$TEMP_INSTALL_PATH"
	chcon u:object_r:apk_data_file:s0 "$TEMP_INSTALL_PATH" 2>/dev/null

	for user_id in $(get_user_list); do
		output=$($PM_CMD install --user "$user_id" -r -g "$TEMP_INSTALL_PATH" 2>&1)
		result=$?
		echo "Install result (User $user_id): $output (Code: $result)" >> "$LOGFILE"
		if [ "$result" -eq 0 ]; then
			installed=$((installed + 1))
		elif echo "$output" | grep -q 'INSTALL_FAILED_UPDATE_INCOMPATIBLE'; then
			signature_mismatch=true
			break
		fi
	done

	if [ "$signature_mismatch" = true ]; then
		local fingerprint
		fingerprint=$(apk_fingerprint "$source_file")
		if [ -f "$SIGNATURE_DECLINED_MARKER" ] && \
			grep -Fqx "$fingerprint" "$SIGNATURE_DECLINED_MARKER" && is_package_installed; then
			echo "This APK signature was already declined; keeping the installed app and restaging the APK." >> "$LOGFILE"
			rm -f "$TEMP_INSTALL_PATH"
			copy_apk_to_sdcard "$source_file"
			return 2
		fi

		if ask_to_replace_different_signature; then
			if ! uninstall_existing_app; then
				echo "ERROR: User accepted migration, but the existing app could not be removed." >> "$LOGFILE"
				rm -f "$TEMP_INSTALL_PATH"
				copy_apk_to_sdcard "$source_file"
				return 1
			fi
			installed=0
			for user_id in $(get_user_list); do
				output=$($PM_CMD install --user "$user_id" -r -g "$TEMP_INSTALL_PATH" 2>&1)
				result=$?
				echo "Install after approved removal (User $user_id): $output (Code: $result)" >> "$LOGFILE"
				[ "$result" -eq 0 ] && installed=$((installed + 1))
			done
			rm -f "$TEMP_INSTALL_PATH"
			rm -f "$SIGNATURE_DECLINED_MARKER"
			[ "$installed" -gt 0 ] && return 0
			echo "ERROR: New APK could not be installed after the old app was removed." >> "$LOGFILE"
			copy_apk_to_sdcard "$source_file"
			return 1
		fi

		echo "$fingerprint" > "$SIGNATURE_DECLINED_MARKER"
		rm -f "$TEMP_INSTALL_PATH"
		copy_apk_to_sdcard "$source_file"
		return 2
	fi

	rm -f "$TEMP_INSTALL_PATH"
	if [ "$installed" -gt 0 ]; then
		rm -f "$SIGNATURE_DECLINED_MARKER"
		return 0
	fi
	return 1
}

APK_SOURCE=""
if [ -f "$MODPATH/JamesDSPManager.apk" ]; then
	APK_SOURCE="$MODPATH/JamesDSPManager.apk"
elif [ -f "$INTERNAL_PATH" ]; then
	APK_SOURCE="$INTERNAL_PATH"
	cat <<'EOF' >> "$LOGFILE"
No APK in module; using the staged internal-storage copy.
EOF
else
	echo "ERROR: No JamesDSP APK was found." >> "$LOGFILE"
	exit 1
fi

# The service runs at every boot. Avoid reinstalling the exact APK after the
# module update has already succeeded.
if is_package_installed && installed_apk_matches "$APK_SOURCE"; then
	echo "The installed james.dsp APK already matches the module payload; no update needed." >> "$LOGFILE"
	exit 0
fi

# A declined signature migration should not interrupt every boot. If the
# module APK changes, its fingerprint changes and the user is asked again.
if is_package_installed && [ -f "$SIGNATURE_DECLINED_MARKER" ] && \
	grep -Fqx "$(apk_fingerprint "$APK_SOURCE")" "$SIGNATURE_DECLINED_MARKER"; then
	echo "A previous decision kept the installed app; refreshing the staged APK without prompting again." >> "$LOGFILE"
	copy_apk_to_sdcard "$APK_SOURCE"
	exit 0
fi

install_for_all_users "$APK_SOURCE"
INSTALL_STATUS=$?

if [ "$INSTALL_STATUS" -eq 0 ]; then
	echo "Installation is complete. Refreshing package..." >> "$LOGFILE"
	for USER_ID in $(get_user_list); do
		$PM_CMD disable --user "$USER_ID" "$PKG" >/dev/null 2>&1
		$PM_CMD enable --user "$USER_ID" "$PKG" >/dev/null 2>&1
	done
	echo " -- DONE! --" >> "$LOGFILE"
elif [ "$INSTALL_STATUS" -eq 2 ]; then
	echo "Existing app retained; new APK is available in Downloads." >> "$LOGFILE"
else
	echo "Installation did not complete; see the result above." >> "$LOGFILE"
fi
