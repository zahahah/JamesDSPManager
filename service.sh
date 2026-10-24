#!/system/bin/sh
MODPATH=${0%/*}
MODDIR=$MODPATH
mkdir -p "$MODPATH/logs"

# Module overlays are now mounted. Refresh typed service labels in a bounded
# background task before starting the app, including the late-load branch.
if [ -f "$MODPATH/native-control.sh" ]; then
	sh "$MODPATH/native-control.sh" activate "$MODPATH" >"$MODPATH/logs/native-control-activation.log" 2>&1 &
fi

# Some vendor task profiles map the DSP thread into a scheduler group that
# avoids the underruns observed on the Pixel. The helper validates the exact
# vendor profile before changing anything and exits harmlessly elsewhere.
if [ -x "$MODPATH/dsp-thread-profile.sh" ]; then
	sh "$MODPATH/dsp-thread-profile.sh" --watch "$MODPATH" \
		>>"$MODPATH/logs/dsp-thread-profile.log" 2>&1 </dev/null &
fi

start_lightningdsp_app_installer() {
	[ -f "$MODPATH/lightningdsp_app.sh" ] || return 0
	MODPATH="$MODPATH" sh "$MODPATH/lightningdsp_app.sh" >/dev/null 2>&1 &
}

CURRENT_BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
LATE_LOAD_READY_THIS_BOOT=false
if [ -n "$CURRENT_BOOT_ID" ] && grep -q "^READY late_load=1 boot_id=$CURRENT_BOOT_ID " \
	"$MODPATH/logs/late-load.status" 2>/dev/null; then
	LATE_LOAD_READY_THIS_BOOT=true
fi
if [ "${KSU_LATE_LOAD:-0}" = 1 ] || [ "$LATE_LOAD_READY_THIS_BOOT" = true ] || \
	[ -f "$MODPATH/.late-load-reload-experimental" ]; then
	mkdir -p "$MODPATH/logs"
	start_lightningdsp_app_installer
	if { [ "${KSU_LATE_LOAD:-0}" = 1 ] || [ "$LATE_LOAD_READY_THIS_BOOT" = true ]; } && \
		[ -x "$MODPATH/audio-hal-recovery.sh" ]; then
		(
			"${LDSP_SLEEP_BIN:-/system/bin/sleep}" 10
			sh "$MODPATH/audio-hal-recovery.sh" --auto-once \
				>>"$MODPATH/logs/audio-hal-recovery.log" 2>&1
		) </dev/null >/dev/null 2>&1 &
		printf 'SCHEDULED reason=late_load_recovery delay_seconds=10 restart=one_shot processing=unverified\n' \
			>"$MODPATH/logs/service.status"
	else
		printf 'SKIPPED reason=not_kernel_su_late_load restart=not_requested processing=unverified\n' \
		>"$MODPATH/logs/service.status"
	fi
	exit 0
fi
if [ -f "$MODPATH/.late-load-no-effect" ] || [ -f "$MODPATH/.late-load-rootless" ]; then
	mkdir -p "$MODPATH/logs"
	printf 'SKIPPED reason=legacy_late_load_no_effect_marker\n' \
		>"$MODPATH/logs/service.status"
	exit 0
fi
exec 2>"$MODPATH/logs/service_debug.txt"
set -x
if [ -d "$MODPATH/system/vendor" ] && [ ! -L "$MODPATH/system/vendor" ]; then
MOD_VENDOR="$MODPATH/system/vendor"
MOD_ODM="$MODPATH/system/odm"
else
MOD_VENDOR="$MODPATH/vendor"
MOD_ODM="$MODPATH/odm"
fi

# effect lib we're looking for existence in system and module
EFFECT_LIBS="lightningdsplib.so"

# function which is used by mount functions
# check and eventual mount logic
# this function will recognize lib and lib64 folders
# to be sure, selinux context will be based on reference taken from soundfx folder
# which in /vendor/lib(64)/soundfx it's in 99.9% u:object_r:vendor_file:s0
mount_effect_lib(){
	local SYS_TARGET="$1"
	local MOD_SOURCE_DIR="$2"
	local WORK_DIR="$MODPATH/system/effect_mount$SYS_TARGET"
	
	[ ! -d "$SYS_TARGET" ] && return
	
	local need_mount=false
	
	for lib in $EFFECT_LIBS; do
		if [ -f "$MOD_SOURCE_DIR/$lib" ]; then
			if [ ! -f "$SYS_TARGET/$lib" ]; then
				need_mount=true
				break
			fi
		fi
	done
	
	if [ "$need_mount" = false ]; then
		return
	fi
	
	[ -d "$WORK_DIR" ] && rm -rf "$WORK_DIR"
	mkdir -p "$WORK_DIR"
	
	cp -af "$SYS_TARGET"/* "$WORK_DIR/"
	
	local lib_found=false
	for lib in $EFFECT_LIBS; do
		if [ -f "$MOD_SOURCE_DIR/$lib" ]; then
			cp -f "$MOD_SOURCE_DIR/$lib" "$WORK_DIR/$lib"
			lib_found=true
		fi
	done
	
	if [ "$lib_found" = false ]; then
		rm -rf "$WORK_DIR"
		return
	fi
	
	chcon -R --reference="$SYS_TARGET" "$WORK_DIR"
	mount -o bind "$WORK_DIR" "$SYS_TARGET"	
	MOUNTED=true
}

# function for mounting lib in vendor
mount_vendor(){
	for libs in lib lib64; do
		local SYS_TARGET="/vendor/$libs/soundfx"
		local MOD_SOURCE_DIR="$MOD_VENDOR/$libs/soundfx"
		mount_effect_lib "$SYS_TARGET" "$MOD_SOURCE_DIR"
	done
}

# function for mounting lib in apex if needed
mount_apex(){
	local APEX_SFX_LIST=$(find /apex -type d -path "*/lib64/soundfx" 2>/dev/null)
	if [ -n "$APEX_SFX_LIST" ]; then
		for SFX in ${APEX_SFX_LIST}; do
			local MOD_SOURCE_DIR="$MOD_VENDOR/lib64/soundfx"
			mount_effect_lib "$SFX" "$MOD_SOURCE_DIR"
		done
	fi
}

mount_vendor
mount_apex

# mounting audio_effects IF it's not already mounted and it's seeking for mounted lib before doing any action
AUD=$(find $MODPATH/system $MOD_VENDOR $MOD_ODM -type f -name "*audio_effects*.conf" -o -name "*audio_effects*.xml")
if [ -f /vendor/lib/soundfx/lightningdsplib.so ] || [ -f /vendor/lib64/soundfx/lightningdsplib.so ];then
	if [ ! -z "$AUD" ]; then
		MOUNTED=false
		for i in $AUD; do
		j="$(echo $i | sed "s|$MODPATH||")"
		j="$(echo $j | sed "s|/system||")"
		case "$j" in
			/etc/*) j="/system$j" ;;
			/lib/*) j="/system$j" ;;
			/lib64/*) j="/system$j" ;;
		esac
		if [ -f "$j" ] && ! cmp -s "$i" "$j"; then
		echo " -- Files $i and $j are different. Mounting modded file. -- "
			mount -o bind "$i" "$j"
			MOUNTED=true
		fi
		done
			if [ "$MOUNTED" = true ]; then
				printf "Audio config changed; automatic audio restart disabled\n"
		fi
	fi
fi

# attempt of disabling ignore effects prop
(
counter=0
while [ "$(getprop ro.audio.ignore_effects)" = "true" ] && [ $counter -le 20 ]; do
	resetprop ro.audio.ignore_effects false
	sleep 1
	counter=$(($counter+1))
done
) >/dev/null 2>&1 &
set +x

# launching lightningdsp_app.sh
start_lightningdsp_app_installer
