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

	# The app belongs to the user, not to the module lifecycle. Removing the
	# module must never erase app data or uninstall the package.
	if [ ! -d "$MODPATH" ]; then
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
