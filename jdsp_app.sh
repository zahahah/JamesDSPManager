#!/system/bin/sh
[ -z "$MODPATH" ] && MODPATH="${0%/*}"

# Constants/paths
PKG="james.dsp"
LOGFILE="$MODPATH/logs/jamesdsp_app_install.log"
INTERNAL_PATH="/storage/emulated/0/JamesDSPManager.apk"
TEMP_INSTALL_PATH="/cache/JamesDSPManager.apk"

# Method pick
if [ -x "/system/bin/cmd" ]; then
	PM_CMD="cmd package"
	METHOD_LOG="cmd package (Android 7+)"
else
	PM_CMD="pm"
	METHOD_LOG="pm (Android <7)"
fi

echo "--- JamesDSP Installer through $METHOD_LOG ---" > "$LOGFILE"

# Boot wait
until [ "$(getprop sys.boot_completed)" = "1" ]; do
	sleep 1
done

# Extra wait just to be sure
sleep 10

# Check if installed
if $PM_CMD list packages | grep -q "$PKG"; then
	echo " -- App is already installed. Exiting. -- " >> "$LOGFILE"
	exit 0
fi

# Installation Function
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

	# Install logic
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
	
	# Cleanup
	rm -f "$TEMP_INSTALL_PATH"

	if [ $success_count -gt 0 ]; then
		return 0
	else
		return 1
	fi
}

# MAIN LOGIC
INSTALL_STATUS=1

echo "App is not installed, attempt to install an app..." >> "$LOGFILE"

# First attempt: installing from module APK
if [ -f "$MODPATH/JamesDSPManager.apk" ]; then
	install_apk "$MODPATH/JamesDSPManager.apk"
	INSTALL_STATUS=$?

# Second attempt: installing from Internal Storage APK
elif [ -f "$INTERNAL_PATH" ]; then
	echo "No APK in module. Using APK from internal memory..." >> "$LOGFILE"
	install_apk "$INTERNAL_PATH"
	INSTALL_STATUS=$?

else
	echo " -- NO APK ANYWHERE! -- " >> "$LOGFILE"
fi

# conclusion/refreshing app
if [ $INSTALL_STATUS -eq 0 ]; then
	echo "Installation is complete. Refreshing package..." >> "$LOGFILE"

	USER_LIST=$($PM_CMD list users | grep -o '{[0-9]*' | grep -o '[0-9]*')
	for USER_ID in $USER_LIST; do
		$PM_CMD disable --user "$USER_ID" "$PKG" >/dev/null 2>&1
		$PM_CMD enable --user "$USER_ID" "$PKG" >/dev/null 2>&1
	done
	echo " -- DONE! --" >> "$LOGFILE"
else
	echo "Installation is NOT complete <sad panda.jpg>" >> "$LOGFILE"
fi