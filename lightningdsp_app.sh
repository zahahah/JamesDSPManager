#!/system/bin/sh
[ -z "$MODPATH" ] && MODPATH="${0%/*}"

PKG="com.lightning.dsp"
LEGACY_PKG="james.dsp"
LOGFILE="$MODPATH/logs/lightningdsp_app_install.log"
INTERNAL_PATH="/storage/emulated/0/LightningDSP.apk"
TEMP_INSTALL_PATH=${LDSP_TEMP_INSTALL_PATH:-/cache/LightningDSP.apk}
KEY_TIMEOUT=${LDSP_KEY_TIMEOUT_SECONDS:-10}
GETEVENT_BIN=${LDSP_GETEVENT_BIN:-/system/bin/getevent}
DATA_ROOT=${LDSP_DATA_ROOT:-/data}
DATA_BACKUP_DIR=${LDSP_DATA_BACKUP_DIR:-"$MODPATH/.ldsp-appdata-migration"}
TAR_BIN=${LDSP_TAR_BIN:-tar}
CHOWN_BIN=${LDSP_CHOWN_BIN:-chown}
RESTORECON_BIN=${LDSP_RESTORECON_BIN:-restorecon}

# The flash installer invokes this helper from modules_update before the
# staged module is activated, and that tree may not contain a logs/ directory.
# Create it before any logfile redirection; otherwise the tar redirection also
# fails before tar runs, making every app-data backup fail.
if ! mkdir -p "${LOGFILE%/*}" 2>/dev/null; then
	LOGFILE=/dev/null
fi

if [ -n "${LDSP_PM_CMD:-}" ]; then
	PM_CMD="$LDSP_PM_CMD"
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

legacy_package_installed() {
	$PM_CMD list packages 2>/dev/null | grep -Fqx "package:$LEGACY_PKG"
}

get_users() {
	$PM_CMD list users 2>/dev/null | grep -o '{[0-9]*' | grep -o '[0-9]*'
}

install_for_users() {
	APK_SOURCE="$1"
	INSTALL_USERS="$2"
	[ -n "$INSTALL_USERS" ] || INSTALL_USERS="0"
	SUCCESS_COUNT=0

	log "--- Installing LightningDSP app from: $APK_SOURCE ---"
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
		if echo "$OUTPUT" | grep -qiE 'INSTALL_FAILED_UPDATE_INCOMPATIBLE|signatures do not match|signature.*match'; then
			log "SIGNATURE_MISMATCH user=$USER_ID"
			rm -f "$TEMP_INSTALL_PATH"
			return 2
		elif [ "$RESULT" -eq 0 ] && echo "$OUTPUT" | grep -qE '(^|[[:space:]])Success([[:space:]]|$)'; then
			SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
		else
			log "ERROR: Package Manager did not confirm installation success for user $USER_ID."
			rm -f "$TEMP_INSTALL_PATH"
			return 1
		fi
	done
	rm -f "$TEMP_INSTALL_PATH"
	[ "$SUCCESS_COUNT" -gt 0 ]
}

remove_legacy_app_for_users() {
	LEGACY_USERS=$(get_users)
	[ -n "$LEGACY_USERS" ] || LEGACY_USERS="0"
	REMOVED_USERS=0
	FAILED_USERS=0
	ui_print "   Removing the previous james.dsp app before installing LightningDSP"
	ui_print "   The old package's private app data will be removed and is not migrated"
	log "Legacy app package migration requested; removing $LEGACY_PKG for all users."
	for USER_ID in $LEGACY_USERS; do
		if ! $PM_CMD list packages --user "$USER_ID" 2>/dev/null | grep -Fqx "package:$LEGACY_PKG"; then
			continue
		fi
		OUTPUT=$($PM_CMD uninstall --user "$USER_ID" "$LEGACY_PKG" 2>&1)
		RESULT=$?
		log "Legacy uninstall user=$USER_ID result=$RESULT output=$OUTPUT"
		if [ "$RESULT" -eq 0 ]; then
			REMOVED_USERS=$((REMOVED_USERS + 1))
		else
			FAILED_USERS=$((FAILED_USERS + 1))
			ui_print "   WARNING: Could not remove james.dsp for user $USER_ID"
		fi
	done
	[ "$FAILED_USERS" -eq 0 ] && { [ "$REMOVED_USERS" -gt 0 ] || ! legacy_package_installed; }
}

backup_app_data() {
	# The backup is deliberately inside the module tree so it survives a
	# reboot/module update, but is removed immediately after a successful restore.
	# Never overwrite a previous incomplete migration backup.
	if [ -e "$DATA_BACKUP_DIR/restore-pending" ] || [ -e "$DATA_BACKUP_DIR/data.tar" ]; then
		log "ERROR: a previous app-data migration backup already exists at $DATA_BACKUP_DIR."
		ui_print "   ERROR: previous app-data backup is pending; refusing to overwrite it"
		return 1
	fi

	USERS=$(get_users)
	[ -n "$USERS" ] || USERS="0"
	set --
	for USER_ID in $USERS; do
		for RELATIVE_PATH in \
			"user/$USER_ID/$PKG" \
			"user_de/$USER_ID/$PKG" \
			"media/$USER_ID/Android/data/$PKG" \
			"media/$USER_ID/Android/obb/$PKG"; do
			if [ -e "$DATA_ROOT/$RELATIVE_PATH" ] || [ -L "$DATA_ROOT/$RELATIVE_PATH" ]; then
				set -- "$@" "$RELATIVE_PATH"
			fi
		done
	done

	if [ "$#" -eq 0 ]; then
		log "No app-private or package-specific external data directories found; continuing without a data archive."
		ui_print "   No app-data directories found to back up"
		return 0
	fi

	umask 077
	mkdir -p "$DATA_BACKUP_DIR" || {
		log "ERROR: could not create private app-data backup directory."
		return 1
	}
	chmod 700 "$DATA_BACKUP_DIR" 2>/dev/null || {
		log "ERROR: could not secure app-data backup directory."
		rm -rf "$DATA_BACKUP_DIR"
		return 1
	}
	printf '%s\n' "$USERS" > "$DATA_BACKUP_DIR/users.list" || return 1
	TMP_ARCHIVE="$DATA_BACKUP_DIR/data.tar.tmp"
	rm -f "$TMP_ARCHIVE"
	if ! "$TAR_BIN" -c -p -f "$TMP_ARCHIVE" -C "$DATA_ROOT" "$@" >>"$LOGFILE" 2>&1 ||
	   [ ! -s "$TMP_ARCHIVE" ] || ! "$TAR_BIN" -t -f "$TMP_ARCHIVE" >/dev/null 2>&1; then
		rm -f "$TMP_ARCHIVE"
		log "ERROR: app-data backup failed; existing app was not uninstalled."
		ui_print "   ERROR: app-data backup failed; existing app was kept"
		return 1
	fi
	mv -f "$TMP_ARCHIVE" "$DATA_BACKUP_DIR/data.tar" || return 1
	chmod 600 "$DATA_BACKUP_DIR/data.tar" "$DATA_BACKUP_DIR/users.list" 2>/dev/null
	log "App-data backup created before uninstall: $DATA_BACKUP_DIR/data.tar"
	ui_print "   App data backed up before uninstall"
	ui_print "   Some Android Keystore-protected secrets may not survive a signing-key migration"
	return 0
}

app_uid_for_user() {
	USER_ID="$1"
	UID_OUTPUT=$($PM_CMD list packages -U --user "$USER_ID" "$PKG" 2>/dev/null)
	printf '%s\n' "$UID_OUTPUT" | sed -n 's/.*uid:\([0-9][0-9]*\).*/\1/p' | head -n 1
}

restore_app_data() {
	ARCHIVE="$DATA_BACKUP_DIR/data.tar"
	if [ ! -s "$ARCHIVE" ]; then
		if [ -e "$DATA_BACKUP_DIR/restore-pending" ]; then
			rm -rf "$DATA_BACKUP_DIR"
			log "No app-data archive was needed; signer migration completed."
		fi
		return 0
	fi
	if ! package_installed; then
		log "App-data restore deferred because $PKG is not installed yet."
		return 1
	fi
	log "Restoring app data from $ARCHIVE"
	if ! "$TAR_BIN" -x -p -f "$ARCHIVE" -C "$DATA_ROOT" >>"$LOGFILE" 2>&1; then
		log "ERROR: app-data archive extraction failed; backup retained."
		ui_print "   WARNING: app data could not be restored; backup retained at $DATA_BACKUP_DIR"
		return 1
	fi

	RESTORE_FAILED=0
	if [ -f "$DATA_BACKUP_DIR/users.list" ]; then
		RESTORE_USERS=$(cat "$DATA_BACKUP_DIR/users.list")
	else
		RESTORE_USERS=$(get_users)
	fi
	[ -n "$RESTORE_USERS" ] || RESTORE_USERS="0"
	for USER_ID in $RESTORE_USERS; do
		APP_UID=$(app_uid_for_user "$USER_ID")
		for DOMAIN in user user_de; do
			RESTORE_PATH="$DATA_ROOT/$DOMAIN/$USER_ID/$PKG"
			[ -e "$RESTORE_PATH" ] || continue
			if [ -z "$APP_UID" ]; then
				log "ERROR: could not resolve installed package UID for user $USER_ID; backup retained."
				RESTORE_FAILED=1
				continue
			fi
			if ! "$CHOWN_BIN" -R "$APP_UID:$APP_UID" "$RESTORE_PATH" >>"$LOGFILE" 2>&1; then
				log "ERROR: could not set app ownership on $RESTORE_PATH; backup retained."
				RESTORE_FAILED=1
				continue
			fi
			if ! command -v "$RESTORECON_BIN" >/dev/null 2>&1; then
				log "ERROR: restorecon is unavailable for $RESTORE_PATH; backup retained."
				RESTORE_FAILED=1
			elif ! "$RESTORECON_BIN" -RF "$RESTORE_PATH" >>"$LOGFILE" 2>&1; then
				log "ERROR: restorecon failed for $RESTORE_PATH; backup retained."
				RESTORE_FAILED=1
			fi
		done
		for DOMAIN in data obb; do
			RESTORE_PATH="$DATA_ROOT/media/$USER_ID/Android/$DOMAIN/$PKG"
			if [ -e "$RESTORE_PATH" ]; then
				if ! command -v "$RESTORECON_BIN" >/dev/null 2>&1; then
					log "ERROR: restorecon is unavailable for $RESTORE_PATH; backup retained."
					RESTORE_FAILED=1
				elif ! "$RESTORECON_BIN" -RF "$RESTORE_PATH" >>"$LOGFILE" 2>&1; then
					log "ERROR: restorecon failed for $RESTORE_PATH; backup retained."
					RESTORE_FAILED=1
				fi
			fi
		done
	done
	if [ "$RESTORE_FAILED" -ne 0 ]; then
		ui_print "   WARNING: app-data restore needs attention; backup retained at $DATA_BACKUP_DIR"
		return 1
	fi
	rm -rf "$DATA_BACKUP_DIR"
	log "App-data restore completed; temporary backup removed."
	ui_print "   App data restored after installing ThePBone app"
	return 0
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

echo "--- LightningDSP app installer through $METHOD_LOG ---" > "$LOGFILE"

# Wait until package manager is ready (service.sh path only; flash path is
# already running inside the live Android installer).
if [ "${LDSP_FLASH_INSTALL:-0}" != 1 ]; then
	until [ "$(getprop sys.boot_completed)" = "1" ]; do sleep 1; done
fi

if [ -f "$MODPATH/LightningDSP.apk" ]; then
	APK_SOURCE="$MODPATH/LightningDSP.apk"
elif [ -f "$INTERNAL_PATH" ]; then
	APK_SOURCE="$INTERNAL_PATH"
	log "No APK in module; using staged internal-storage copy."
else
	log "No APK was found."
	exit 1
fi

# The package ID changed from james.dsp to com.lightning.dsp. Migrate only
# during the explicit module-flash installer, never from the boot service.
if [ "${LDSP_FLASH_INSTALL:-0}" = 1 ] && legacy_package_installed; then
	if remove_legacy_app_for_users; then
		if install_for_users "$APK_SOURCE" "$(get_users)"; then
			log "Legacy package removed and LightningDSP installed."
		else
			ui_print "   ERROR: LightningDSP install failed after legacy app removal; APK remains staged for manual install"
			log "ERROR: LightningDSP install failed after legacy package removal."
		fi
	else
		ui_print "   WARNING: The previous app could not be fully removed; installing LightningDSP anyway"
		install_for_users "$APK_SOURCE" "$(get_users)" || log "ERROR: LightningDSP install failed during legacy app migration."
	fi
	exit 0
fi

if package_installed; then
	if [ "${LDSP_FLASH_INSTALL:-0}" != 1 ]; then
		if [ -e "$DATA_BACKUP_DIR/restore-pending" ]; then
			restore_app_data || log "Pending app-data restore remains available for retry."
			exit 0
		fi
		log "App already installed; boot service will not prompt or uninstall it."
		exit 0
	fi

	USERS=$(get_users)
	install_for_users "$APK_SOURCE" "$USERS"
	INSTALL_RESULT=$?
	if [ "$INSTALL_RESULT" -eq 0 ]; then
		log "Updated installed app in place (Package Manager accepted the existing signing identity)."
		ui_print "   Existing com.lightning.dsp app updated in place"
	elif [ "$INSTALL_RESULT" -eq 2 ]; then
		ui_print "   Installed app has a different signing certificate."
		if wait_for_replacement_choice; then
			ui_print "   Confirmed: removing existing com.lightning.dsp before installing ThePBone app"
			log "User confirmed uninstall with volume down."
			BACKUP_READY=0
			if backup_app_data; then
				BACKUP_READY=1
			else
				ui_print "   WARNING: data backup failed; continuing as confirmed (app data may be lost)"
				log "WARNING: data backup failed; continuing with user-confirmed uninstall."
			fi
			OUTPUT=$($PM_CMD uninstall "$PKG" 2>&1)
			RESULT=$?
			log "Uninstall result: $OUTPUT (Code: $RESULT)"
			if [ "$RESULT" -eq 0 ]; then
				if [ "$BACKUP_READY" -eq 1 ]; then
					mkdir -p "$DATA_BACKUP_DIR" 2>/dev/null
					touch "$DATA_BACKUP_DIR/restore-pending"
					chmod 600 "$DATA_BACKUP_DIR/restore-pending" 2>/dev/null
				fi
				install_for_users "$APK_SOURCE" "$(get_users)"
				RESULT=$?
				if [ "$RESULT" -eq 0 ]; then
					if [ "$BACKUP_READY" -eq 1 ]; then
						restore_app_data || log "App installed; data backup retained for a boot-time restore retry."
					else
						ui_print "   App installed without restored data"
					fi
					ui_print "   ThePBone app installed"
					log "Fresh install completed after explicit user confirmation."
				else
					ui_print "   ERROR: app install failed after uninstall; see module logs"
					if [ "$BACKUP_READY" -eq 1 ]; then
						log "ERROR: Fresh install failed after confirmed uninstall (result=$RESULT); migration backup retained."
					else
						log "ERROR: Fresh install failed after confirmed uninstall (result=$RESULT); no backup was available."
					fi
				fi
			else
				ui_print "   ERROR: could not remove existing app; it was not replaced"
				[ "$BACKUP_READY" -eq 1 ] && [ -d "$DATA_BACKUP_DIR" ] && rm -rf "$DATA_BACKUP_DIR"
				log "Uninstall failed; existing app remains installed."
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
if [ "${LDSP_FLASH_INSTALL:-0}" = 1 ]; then
	log "App is absent during module flash; first-install deferred until boot."
	exit 0
fi

log "App is missing; installing bundled APK."
if install_for_users "$APK_SOURCE" "$(get_users)"; then
	if [ -e "$DATA_BACKUP_DIR/restore-pending" ]; then
		restore_app_data || log "App installed, but pending app-data restore was not completed."
	fi
	log "Installation completed. Refreshing package state."
	for USER_ID in $(get_users); do
		$PM_CMD disable --user "$USER_ID" "$PKG" >/dev/null 2>&1
		$PM_CMD enable --user "$USER_ID" "$PKG" >/dev/null 2>&1
	done
	log "DONE"
else
	log "Installation did not complete."
fi
