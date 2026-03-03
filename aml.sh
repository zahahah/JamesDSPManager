#!/system/bin/sh
API="$(getprop ro.build.version.sdk)"
[ "$API" -ge 26 ] && libdir="/vendor" || libdir="/system"

if [ -f /data/adb/modules/ainur_jamesdsp/.AIDL ]; then
AIDL=true
else
AIDL=false
fi

LIB=libjamesdsp.so
LIBNAME=jdsp
NAME=jamesdsp
UUID=f27317f4-c984-4de6-9a90-545759495bf2
TYPE=f98765f4-c321-5de6-9a45-123459495ab2

patchxml() {
if [ ! -z "$AUDEFXML" ]; then
	if [ $AIDL = "true" ]; then
		for XML in $AUDEFXML; do
			grep -q "$LIBNAME" "$XML" && continue
			sed -i "/<libraries>/a\        <library name=\"$LIBNAME\" path=\"$LIB\"\/>" "$XML"
			sed -i "/<effects>/a\        <effect name=\"$NAME\" library=\"$LIBNAME\" uuid=\"$UUID\"\ type=\"$TYPE\"\/>" "$XML"
		done
	else
		for XML in $AUDEFXML; do
			grep -q "$LIBNAME" "$XML" && continue
			sed -i "/<libraries>/a\        <library name=\"$LIBNAME\" path=\"$LIB\"\/>" "$XML"
			sed -i "/<effects>/a\        <effect name=\"$NAME\" library=\"$LIBNAME\" uuid=\"$UUID\"\/>" "$XML"
		done
	fi
fi
}

patchconf() {
if [ ! -z "$AUDEFCONF" ]; then
	for CONF in $AUDEFCONF; do
		grep -q "$LIBNAME" "$CONF" && continue
		sed -i "/^libraries {/a\  $LIBNAME {\n    path \\$libdir\/lib\/soundfx\/$LIB\n  }" "$CONF"
		sed -i "/^effects {/a\  $NAME {\n    library $LIBNAME\n    uuid $UUID\n  }" "$CONF"
	done
fi
}
AUDEFXML="$(find /data/adb/modules -type f -name "*audio*effects*.xml")"
AUDEFCONF="$(find /data/adb/modules -type f -name "*audio*effects*.conf")"

patchxml

if [ $AIDL = "false" ]; then
	patchconf
fi
