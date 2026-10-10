#!/system/bin/sh
[ -z "$MODPATH" ] && MODPATH="${0%/*}"

# Package and staging paths
PKG="james.dsp"
LOGFILE="$MODPATH/logs/jamesdsp_app_install.log"
INTERNAL_PATH="/storage/emulated/0/JamesDSPManager.apk"
TEMP_INSTALL_PATH=${JDSP_TEMP_INSTALL_PATH:-/cache/JamesDSPManager.apk}

# Prefer cmd package when Android exposes it
if [ -x "/system/bin/cmd" ]; then
	PM_CMD="cmd package"
	METHOD_LOG="cmd package (Android 7+)"
else
	PM_CMD="pm"
	METHOD_LOG="pm (Android <7)"
fi

echo "--- JamesDSP Installer through $METHOD_LOG ---" > "$LOGFILE"

# Wait until package manager is ready
until [ "$(getprop sys.boot_completed)" = "1" ]; do
	sleep 1
done

# Never replace an existing james.dsp package
if $PM_CMD list packages | grep -Fqx "package:$PKG"; then
	echo " -- App is already installed. Exiting. -- " >> "$LOGFILE"
	exit 0
fi

# Install the staged APK for every Android user
install_apk() {
	local source_file="$1"
	local success_count=0

	echo "--- Installing JDSP app from: $source_file ---" >> "$LOGFILE"

	echo " -- Copying $source_file to /cache -- " >> "$LOGFILE"
	cp "$source_file" "$TEMP_INSTALL_PATH"
	chmod 644 "$TEMP_INSTALL_PATH"
	chcon u:object_r:apk_data_file:s0 "$TEMP_INSTALL_PATH" 2>/dev/null

	if [ ! -f "$TEMP_INSTALL_PATH" ]; then
		echo "ERROR: Failed to copy APK to cache!" >> "$LOGFILE"
		return 1
	fi

	# Use the Android user list instead of assuming only user 0
	USER_LIST=$($PM_CMD list users | grep -o '{[0-9]*' | grep -o '[0-9]*')

	for USER_ID in $USER_LIST; do
		echo "Installing for User ID: $USER_ID..." >> "$LOGFILE"

		OUTPUT=$($PM_CMD install --user "$USER_ID" -r -g "$TEMP_INSTALL_PATH" 2>&1)
		RESULT=$?

		echo "Result (User $USER_ID): $OUTPUT (Code: $RESULT)" >> "$LOGFILE"

		if [ $RESULT -eq 0 ]; then
			success_count=$((success_count + 1))
		fi
	done
	
	# Remove only the temporary copy
	rm -f "$TEMP_INSTALL_PATH"

	if [ $success_count -gt 0 ]; then
		return 0
	else
		return 1
	fi
}

# Main flow
INSTALL_STATUS=1

echo "App is missing; installing the selected APK." >> "$LOGFILE"

# Prefer the APK shipped inside the module
if [ -f "$MODPATH/JamesDSPManager.apk" ]; then
	install_apk "$MODPATH/JamesDSPManager.apk"
	INSTALL_STATUS=$?

# Fallback to the copy staged on internal storage
elif [ -f "$INTERNAL_PATH" ]; then
	echo "No APK in module; using the staged internal-storage copy." >> "$LOGFILE"
	install_apk "$INTERNAL_PATH"
	INSTALL_STATUS=$?

else
	echo " -- No APK was found. -- " >> "$LOGFILE"
fi

# Refresh package state after a successful install
if [ $INSTALL_STATUS -eq 0 ]; then
	echo "Installation is complete. Refreshing package..." >> "$LOGFILE"

	USER_LIST=$($PM_CMD list users | grep -o '{[0-9]*' | grep -o '[0-9]*')
	for USER_ID in $USER_LIST; do
		$PM_CMD disable --user "$USER_ID" "$PKG" >/dev/null 2>&1
		$PM_CMD enable --user "$USER_ID" "$PKG" >/dev/null 2>&1
	done
	echo " -- DONE! --" >> "$LOGFILE"
else
	echo "Installation did not complete." >> "$LOGFILE"
fi
