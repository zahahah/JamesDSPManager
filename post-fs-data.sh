#!/system/bin/sh
MODPATH=${0%/*}
MODDIR="$MODPATH"
exec 2>"$MODPATH/logs/post-fs-debug.txt"
set -x

if [ -d "$MODPATH/system/vendor" ] && [ ! -L "$MODPATH/system/vendor" ]; then
	MOD_VENDOR="$MODPATH/system/vendor"
	MOD_ODM="$MODPATH/system/odm"
else
	MOD_VENDOR="$MODPATH/vendor"
	MOD_ODM="$MODPATH/odm"
fi

if [ -f $MODPATH/.AIDL ];then
	AIDL=true
else
	AIDL=false
fi
. "$MODPATH/aml.sh"
. "$MODPATH/patch.sh"
