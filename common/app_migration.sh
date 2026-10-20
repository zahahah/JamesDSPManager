#!/system/bin/sh

JDSP_MIGRATION_CMD=${JDSP_MIGRATION_CMD:-/system/bin/cmd}
JDSP_MIGRATION_PM=""
JDSP_MIGRATION_TIMEOUT=30
JDSP_MIGRATION_SDCARD=${JDSP_MIGRATION_SDCARD:-/storage/emulated/0}
JDSP_MIGRATION_TEMP=${JDSP_MIGRATION_TEMP:-/data/local/tmp/JamesDSPManager-install.apk}

if [ -x "$JDSP_MIGRATION_CMD" ]; then
	JDSP_MIGRATION_PM="$JDSP_MIGRATION_CMD package"
else
	JDSP_MIGRATION_PM="pm"
fi

jdsp_migration_ui_print() {
	if command -v ui_print >/dev/null 2>&1; then
		ui_print "$1"
	else
		echo "$1"
	fi
}

jdsp_migration_fingerprint() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		cksum "$1" | awk '{print $1 ":" $2}'
	fi
}

jdsp_migration_users() {
	local users
	users=$($JDSP_MIGRATION_PM list users 2>/dev/null | grep -o '{[0-9]*' | grep -o '[0-9]*')
	[ -n "$users" ] || users=0
	echo "$users"
}

jdsp_migration_installed_version() {
	$JDSP_MIGRATION_PM dump james.dsp 2>/dev/null |
		sed -n 's/.*versionCode=\([0-9][0-9]*\).*/\1/p' | head -n 1
}

jdsp_migration_installed_apk() {
	$JDSP_MIGRATION_PM path james.dsp 2>/dev/null |
		sed -n 's/^package://p' | head -n 1
}

jdsp_migration_is_installed() {
	$JDSP_MIGRATION_PM list packages 2>/dev/null | grep -Fqx 'package:james.dsp'
}

jdsp_migration_install_for_users() {
	local apk="$1"
	local user_id
	local output
	local result
	local installed=0
	JDSP_MIGRATION_SIGNATURE_MISMATCH=0

	if ! cp "$apk" "$JDSP_MIGRATION_TEMP"; then
		jdsp_migration_ui_print "! Could not stage the JamesDSP APK for Package Manager."
		return 1
	fi
	chmod 644 "$JDSP_MIGRATION_TEMP"
	chcon u:object_r:apk_data_file:s0 "$JDSP_MIGRATION_TEMP" 2>/dev/null

	for user_id in $(jdsp_migration_users); do
		output=$($JDSP_MIGRATION_PM install --user "$user_id" -r -g "$JDSP_MIGRATION_TEMP" 2>&1)
		result=$?
		jdsp_migration_ui_print "JamesDSP install result for user $user_id: $output"
		if [ "$result" -eq 0 ]; then
			installed=$((installed + 1))
		elif echo "$output" | grep -q 'INSTALL_FAILED_UPDATE_INCOMPATIBLE'; then
			JDSP_MIGRATION_SIGNATURE_MISMATCH=1
			break
		else
			rm -f "$JDSP_MIGRATION_TEMP"
			return 1
		fi
	done

	rm -f "$JDSP_MIGRATION_TEMP"
	[ "$installed" -gt 0 ]
}

jdsp_migration_remove_existing() {
	local user_id
	local output
	local result
	local removed=0
	local failed=0

	for user_id in $(jdsp_migration_users); do
		if ! $JDSP_MIGRATION_PM list packages --user "$user_id" 2>/dev/null |
			grep -Fqx 'package:james.dsp'; then
			continue
		fi
		output=$($JDSP_MIGRATION_PM uninstall --user "$user_id" james.dsp 2>&1)
		result=$?
		jdsp_migration_ui_print "JamesDSP removal result for user $user_id: $output"
		if [ "$result" -eq 0 ]; then
			removed=$((removed + 1))
		else
			failed=$((failed + 1))
		fi
	done
	[ "$removed" -gt 0 ] && [ "$failed" -eq 0 ]
}

jdsp_migration_copy_to_downloads() {
	local apk="$1"
	local destination="$JDSP_MIGRATION_SDCARD/Download/JamesDSPManager.apk"
	if mkdir -p "$JDSP_MIGRATION_SDCARD/Download" && cp -f "$apk" "$destination"; then
		chmod 644 "$destination" 2>/dev/null
		jdsp_migration_ui_print "The existing app was kept. New APK copied to $destination."
		return 0
	fi
	jdsp_migration_ui_print "! Could not copy the new APK to $destination. Check module logs."
	return 1
}

jdsp_migration_prompt() {
	local remaining=$JDSP_MIGRATION_TIMEOUT
	local event
	local getevent_bin=${JDSP_MIGRATION_GETEVENT:-/system/bin/getevent}

	jdsp_migration_ui_print "Different JamesDSP signing certificates were detected."
	jdsp_migration_ui_print "Volume Up = remove the installed app and install the module APK (app data will be removed)."
	jdsp_migration_ui_print "Volume Down or no response in ${JDSP_MIGRATION_TIMEOUT}s = keep the installed app and copy the new APK to Downloads."

	while [ "$remaining" -gt 0 ]; do
		event=$(timeout 1 "$getevent_bin" -lqc 1 2>/dev/null)
		case "$event" in
			*KEY_VOLUMEUP*DOWN*)
				jdsp_migration_ui_print "Volume Up selected: replacing the installed JamesDSP app."
				return 0
				;;
			*KEY_VOLUMEDOWN*DOWN*)
				jdsp_migration_ui_print "Volume Down selected: keeping the installed app."
				return 1
				;;
		esac
		remaining=$((remaining - 1))
	done

	jdsp_migration_ui_print "No volume-key response. Keeping the installed app by default."
	return 1
}

jdsp_install_selected_apk() {
	local apk="$1"
	local metadata="$2"
	local module_path="$3"
	local new_version
	local new_signer
	local old_version
	local old_signer
	local installed_apk
	local current_fingerprint
	local install_result

	if [ ! -f "$metadata" ]; then
		jdsp_migration_ui_print "! APK version/signature metadata is missing; boot-time installer will handle the app."
		return 0
	fi
	new_version=$(sed -n 's/^versionCode=//p' "$metadata" | head -n 1)
	case "$new_version" in ''|*[!0-9]*)
		jdsp_migration_ui_print "! APK versionCode metadata is invalid; leaving the app unchanged."
		return 0
	;; esac
	printf '%s\n' "$new_version" > "$module_path/.jdsp_apk_target_version_code"
	if ! jdsp_migration_is_installed; then
		jdsp_migration_ui_print "No existing james.dsp app found. Installing the selected APK now."
		jdsp_migration_install_for_users "$apk"
		return $?
	fi

	old_version=$(jdsp_migration_installed_version)
	installed_apk=$(jdsp_migration_installed_apk)
	jdsp_migration_ui_print " "
	jdsp_migration_ui_print "Analysing installed and selected JamesDSP signing certificates"
	jdsp_migration_ui_print " "
	if ! command -v jdsp_apk_certificate_sha256 >/dev/null 2>&1; then
		. "$module_path/common/apk_certificate.sh"
	fi
	new_signer=$(jdsp_apk_certificate_sha256 "$apk")
	old_signer=$(jdsp_apk_certificate_sha256 "$installed_apk")
	if [ -z "$old_version" ] || [ -z "$new_signer" ] || [ -z "$old_signer" ]; then
		jdsp_migration_ui_print "! Could not read the installed app version/signature. Leaving it untouched; the APK will be staged for manual installation."
		jdsp_migration_copy_to_downloads "$apk"
		return 0
	fi

	if [ "$old_signer" = "$new_signer" ]; then
		if [ "$new_version" -le "$old_version" ]; then
			jdsp_migration_ui_print "Installed JamesDSP is already versionCode $old_version; selected APK versionCode $new_version is not newer. Keeping the installed app."
			return 0
		fi
		jdsp_migration_ui_print "The signing certificate matches and versionCode $new_version is newer than $old_version. Updating JamesDSP in place."
		jdsp_migration_install_for_users "$apk"
		install_result=$?
		if [ "$install_result" -eq 0 ]; then
			return 0
		fi
		[ "$JDSP_MIGRATION_SIGNATURE_MISMATCH" -eq 1 ] || return 1
		jdsp_migration_ui_print "Package Manager reported a signing mismatch despite the metadata match. Requesting confirmation before removal."
	else
		jdsp_migration_ui_print "Installed and selected JamesDSP APKs have different signing certificates."
	fi

	if jdsp_migration_prompt; then
		if ! jdsp_migration_remove_existing; then
			jdsp_migration_ui_print "! The installed app could not be removed. Keeping it and staging the new APK instead."
			jdsp_migration_copy_to_downloads "$apk"
			return 1
		fi
		jdsp_migration_ui_print "Installing the selected JamesDSP APK after the approved removal."
		jdsp_migration_install_for_users "$apk"
		install_result=$?
		if [ "$install_result" -eq 0 ]; then
			rm -f "$module_path/.jdsp_apk_signature_declined"
			return 0
		fi
		jdsp_migration_ui_print "! The new APK could not be installed after removal. Copying it to Downloads."
		jdsp_migration_copy_to_downloads "$apk"
		return 1
	fi

	current_fingerprint=$(jdsp_migration_fingerprint "$apk")
	printf '%s\n' "$current_fingerprint" > "$module_path/.jdsp_apk_signature_declined"
	jdsp_migration_copy_to_downloads "$apk"
	return 0
}
