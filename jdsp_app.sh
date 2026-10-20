#!/system/bin/sh
[ -z "$MODPATH" ] && MODPATH="${0%/*}"

PKG="james.dsp"
LOGFILE="$MODPATH/logs/jamesdsp_app_install.log"
INTERNAL_PATH="/storage/emulated/0/JamesDSPManager.apk"
TEMP_INSTALL_PATH=${JDSP_TEMP_INSTALL_PATH:-/cache/JamesDSPManager.apk}
KEY_TIMEOUT=${JDSP_KEY_TIMEOUT_SECONDS:-10}
GETEVENT_BIN=${JDSP_GETEVENT_BIN:-/system/bin/getevent}

if [ -n "${JDSP_PM_CMD:-}" ]; then
	PM_CMD="$JDSP_PM_CMD"
	METHOD_LOG="configured package command"
elif [ -x "/system/bin/cmd" ]; then
	PM_CMD="cmd package"
	METHOD_LOG="cmd package (Android 7+)"
else
	PM_CMD="pm"
	METHOD_LOG="pm (Android <7)"
fi

ui_print() {
	# During a flash this is visible in the module installer. At boot it is
	# intentionally reduced to stdout, which service.sh redirects to /dev/null.
	echo "$1"
}

log() { echo "$1" >> "$LOGFILE"; }

package_installed() {
	$PM_CMD list packages 2>/dev/null | grep -Fqx "package:$PKG"
}

get_users() {
	$PM_CMD list users 2>/dev/null | grep -o '{[0-9]*' | grep -o '[0-9]*'
}

install_for_users() {
	APK_SOURCE="$1"
	INSTALL_USERS="$2"
	[ -n "$INSTALL_USERS" ] || INSTALL_USERS="0"
	SUCCESS_COUNT=0

	log "--- Installing JDSP app from: $APK_SOURCE ---"
	cp "$APK_SOURCE" "$TEMP_INSTALL_PATH" || {
		log "ERROR: Failed to copy APK to cache."
		return 1
	}
	chmod 644 "$TEMP_INSTALL_PATH"
	chcon u:object_r:apk_data_file:s0 "$TEMP_INSTALL_PATH" 2>/dev/null
	[ -f "$TEMP_INSTALL_PATH" ] || return 1

	for USER_ID in $INSTALL_USERS; do
		OUTPUT=$($PM_CMD install --user "$USER_ID" -r -g "$TEMP_INSTALL_PATH" 2>&1)
		RESULT=$?
		log "Install result (User $USER_ID): $OUTPUT (Code: $RESULT)"
		if [ "$RESULT" -eq 0 ]; then
			SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
		elif echo "$OUTPUT" | grep -qiE 'INSTALL_FAILED_UPDATE_INCOMPATIBLE|signatures do not match|signature.*match'; then
			log "SIGNATURE_MISMATCH user=$USER_ID"
			rm -f "$TEMP_INSTALL_PATH"
			return 2
		fi
	done
	rm -f "$TEMP_INSTALL_PATH"
	[ "$SUCCESS_COUNT" -gt 0 ]
}

wait_for_replacement_choice() {
	[ -x "$GETEVENT_BIN" ] || return 2
	command -v timeout >/dev/null 2>&1 || return 2
	ui_print "   Volume DOWN: uninstall the differently signed app and install ours"
	ui_print "   Volume UP: keep the existing app; no response in 10 seconds also keeps it"
	ui_print "   Warning: confirmed uninstall can erase private app data"
	log "Waiting up to ${KEY_TIMEOUT}s for volume-down confirmation; volume-up/no input keeps existing app."

	# Stop on the first volume-key DOWN event; unrelated input events are ignored.
	KEY_EVENT=$(timeout "$KEY_TIMEOUT" "$GETEVENT_BIN" -lq 2>&1 | grep -m 1 -E 'KEY_VOLUMEDOWN[[:space:]]+DOWN|KEY_VOLUMEUP[[:space:]]+DOWN')
	case "$KEY_EVENT" in
		*KEY_VOLUMEDOWN*DOWN*) return 0 ;;
		*KEY_VOLUMEUP*DOWN*) return 1 ;;
		*) return 2 ;;
	esac
}

echo "--- JamesDSP app installer through $METHOD_LOG ---" > "$LOGFILE"

# Wait until package manager is ready (service.sh path only; flash path is
# already running inside the live Android installer).
if [ "${JDSP_FLASH_INSTALL:-0}" != 1 ]; then
	until [ "$(getprop sys.boot_completed)" = "1" ]; do sleep 1; done
fi

if [ -f "$MODPATH/JamesDSPManager.apk" ]; then
	APK_SOURCE="$MODPATH/JamesDSPManager.apk"
elif [ -f "$INTERNAL_PATH" ]; then
	APK_SOURCE="$INTERNAL_PATH"
	log "No APK in module; using staged internal-storage copy."
else
	log "No APK was found."
	exit 1
fi

if package_installed; then
	if [ "${JDSP_FLASH_INSTALL:-0}" != 1 ]; then
		log "App already installed; boot service will not prompt or uninstall it."
		exit 0
	fi

	USERS=$(get_users)
	install_for_users "$APK_SOURCE" "$USERS"
	INSTALL_RESULT=$?
	if [ "$INSTALL_RESULT" -eq 0 ]; then
		log "Updated installed app in place (Package Manager accepted the existing signing identity)."
		ui_print "   Existing james.dsp app updated in place"
	elif [ "$INSTALL_RESULT" -eq 2 ]; then
		ui_print "   Installed app has a different signing certificate."
		if wait_for_replacement_choice; then
			ui_print "   Confirmed: removing existing james.dsp before installing ThePBone app"
			log "User confirmed uninstall with volume down."
			OUTPUT=$($PM_CMD uninstall "$PKG" 2>&1)
			RESULT=$?
			log "Uninstall result: $OUTPUT (Code: $RESULT)"
			if [ "$RESULT" -eq 0 ]; then
				install_for_users "$APK_SOURCE" "$(get_users)"
				RESULT=$?
				if [ "$RESULT" -eq 0 ]; then
					ui_print "   ThePBone app installed"
					log "Fresh install completed after explicit user confirmation."
				else
					ui_print "   ERROR: app install failed after uninstall; see module logs"
					log "ERROR: Fresh install failed after confirmed uninstall (result=$RESULT)."
				fi
			else
				ui_print "   ERROR: could not remove existing app; it was not replaced"
			fi
		else
			ui_print "   Keeping existing app; ThePBone APK was not installed"
			log "Replacement declined or timed out; existing app preserved."
		fi
	else
		log "In-place update failed for a reason other than signing mismatch; existing app preserved."
		ui_print "   App update failed; existing app was kept (see module logs)"
	fi
	exit 0
fi

# New installations are deferred to boot because package manager may not be
# available during recovery-based module installation.
if [ "${JDSP_FLASH_INSTALL:-0}" = 1 ]; then
	log "App is absent during module flash; first-install deferred until boot."
	exit 0
fi

log "App is missing; installing bundled APK."
if install_for_users "$APK_SOURCE" "$(get_users)"; then
	log "Installation completed. Refreshing package state."
	for USER_ID in $(get_users); do
		$PM_CMD disable --user "$USER_ID" "$PKG" >/dev/null 2>&1
		$PM_CMD enable --user "$USER_ID" "$PKG" >/dev/null 2>&1
	done
	log "DONE"
else
	log "Installation did not complete."
fi
