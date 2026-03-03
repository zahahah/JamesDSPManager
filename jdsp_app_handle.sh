#!/system/bin/sh
(
	# Wait for the system to finish booting
	until [ "$(getprop sys.boot_completed)" = "1" ]; do
		sleep 1
	done

	# Extra buffer to be sure
	sleep 5

	MODID="ainur_jamesdsp"
	MODPATH="/data/adb/modules/$MODID"
	PKG="james.dsp"

	# If module is removed, uninstall app
	if [ ! -d "$MODPATH" ]; then
		# Clear app data (removes internal configs/cache but KEEPS /sdcard/ presets)
		# and uninstall the app package
		if [ -x "/system/bin/cmd" ]; then
			cmd package clear "$PKG" >/dev/null 2>&1
			cmd package uninstall "$PKG" >/dev/null 2>&1
		else
			pm clear "$PKG" >/dev/null 2>&1
			pm uninstall "$PKG" >/dev/null 2>&1
		fi
		# Self-destruct mechanism
		rm -f "$0"
		exit 0
	fi

	# If module is disabled, then app should also be disabled
	if [ -f "$MODPATH/disable" ]; then
		pm disable "$PKG" >/dev/null 2>&1
	else
		pm enable "$PKG" >/dev/null 2>&1
	fi

) & 