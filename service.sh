#!/system/bin/sh
MODPATH=${0%/*}
MODDIR=$MODPATH
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
EFFECT_LIBS="libjamesdsp.so"

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
if [ -f /vendor/lib/soundfx/libjamesdsp.so ] || [ -f /vendor/lib64/soundfx/libjamesdsp.so ];then
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
		killall -q audioserver
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

# launching jdsp_app.sh
[ -f "$MODPATH/jdsp_app.sh" ] && . "$MODPATH/jdsp_app.sh" 2>/dev/null &
