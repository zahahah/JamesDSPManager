#!/system/bin/sh
osp_detect() {
  case $1 in
    *.conf) SPACES=$(sed -n "/^output_session_processing {/,/^}/ {/^ *music {/p}" "$1" | sed -r "s/( *).*/\1/")
            EFFECTS=$(sed -n "/^output_session_processing {/,/^}/ {/^$SPACES\music {/,/^$SPACES}/p}" "$1" | grep -E "^$SPACES +[A-Za-z]+" | sed -r "s/( *.*) .*/\1/g")
            for EFFECT in ${EFFECTS}; do
              SPACES=$(sed -n "/^effects {/,/^}/ {/^ *$EFFECT {/p}" "$1" | sed -r "s/( *).*/\1/")
              [ "$EFFECT" != "atmos" ] && sed -i "/^effects {/,/^}/ {/^$SPACES$EFFECT {/,/^$SPACES}/ s/^/#/g}" "$1"
            done;;
     *.xml) EFFECTS=$(sed -n "/^ *<postprocess>$/,/^ *<\/postprocess>$/ {/^ *<stream type=\"music\">$/,/^ *<\/stream>$/ {/<stream type=\"music\">/d; /<\/stream>/d; s/<apply effect=\"//g; s/\"\/>//g; p}}" "$1")
            for EFFECT in ${EFFECTS}; do
              [ "$EFFECT" != "atmos" ] && sed -ri "/^( *)<apply effect=\"$EFFECT\"\/>/d" "$1"
            done;;
  esac
}

copy_before_uninstall() {
	APPLOC="/storage/emulated/0/Android/data/james.dsp"

	if [ -d "$APPLOC" ]; then
		mkdir -p "$MODPATH"/JamesDSP
		cp -rf "$APPLOC"/files/* "$MODPATH"/JamesDSP
	fi
}

uninstall_app() {
	set +x
	# shellcheck disable=SC3043
	local PKG="james.dsp"
	# shellcheck disable=SC3043
	local FILE=".apk$1" VER="$2"
	[ -z "$INSVER" ] && return 0
	if [ -f "$NVBASE/modules/$MODID/$FILE" ]; then
		[ "$INSVER" -lt "$VER" ] && pm uninstall "$PKG" 2>/dev/null
		find /data/app -type d -name "*$PKG*" -exec rm -rf {} +
		rm -rf /data/data/$PKG
		rm -rf /data/user_de/0/$PKG
		pm uninstall $PKG > /dev/null 2>&1
		pm uninstall --user 0 $PKG > /dev/null 2>&1
	else
		pm uninstall $PKG > /dev/null 2>&1
	fi
}

# Tell user aml is needed if applicable
FILES=$(find "$NVBASE/modules/*/system" "$MODULEROOT/*/system" -type f -name "*audio_effects*.conf" -o -name "*audio_effects*.xml" 2>/dev/null | sed "/$MODID/d" | sed "/sv_apixaml/d")
# shellcheck disable=SC2143
if [ ! -z "$FILES" ] && [ ! "$(echo "$FILES" | grep '/aml/')" ]; then
  ui_print " "
  ui_print "   ! Conflicting audio mod found!"
  ui_print "   ! You will need to install !"
  ui_print "   ! Audio Modification Library !"
  sleep 3
fi

#Lib detection
LIB=$(lshal debug "$(lshal | grep -oE "android.hardware.audio.effect@[0-9]+\.[0-9]+::IEffectsFactory/default" | head -n 1)" | grep -E 'lib|lib64' | awk -F '/' 'NR==1{print $3}')

LIB2=$(file /*/bin/hw/android.hardware.audio.service* 2>/dev/null | grep -oE "32-bit|64-bit" | head -n 1)

if service list | grep -q "android.hardware.audio.effect.IFactory"; then
AIDL=true
else
AIDL=false
fi

ui_print " "
ui_print "- Lib bit detection -"

if [ "$AIDL" = "true" ]; then
	QARCH="aidl"
	ui_print "  AIDL libs detected "
	touch "$MODPATH/.AIDL"
	cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib64/soundfx/libjamesdsp.so"
elif [ "$LIB" = "lib64" ] || [ "$LIB2" = "64-bit" ]; then
	QARCH="arm64"
	ui_print "   64 bit audio libs detected  "
	cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib64/soundfx/libjamesdsp.so"
elif [ "$LIB" = "lib" ] || [ "$LIB2" = "32-bit" ]; then
	QARCH=$ARCH32
	ui_print "   32 bit audio libs detected  "
	cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib/soundfx/libjamesdsp.so"
else
	ui_print "   Unable to detect audio lib bit...  "
	ui_print "   Is this a device with 64bit only audio libs?"
	ui_print "   If unsure, select 'No'"
	ui_print "   Vol Up = Yes, Vol Down = No"
  
  if chooseport; then
	if [ "$AIDL" = "true" ]; then
	ui_print "  AIDL libs detected "
	QARCH="aidl"
	touch "$MODPATH/.AIDL"
	cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib64/soundfx/libjamesdsp.so"
	else
    QARCH="arm64"
    cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib64/soundfx/libjamesdsp.so"
    ui_print "   64 bit libs selected"
	fi
  else
    QARCH=$ARCH32
    ui_print "   32 bit libs selected"
    cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib/soundfx/libjamesdsp.so"
  fi
  
fi

cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib/soundfx/libjamesdsp.so"

set +x
# App only works when installed normally to data in oreo+
INSVER=$(cmd package list packages -3 --show-versioncode  2>/dev/null | grep james.dsp | sed 's/.*versionCode://')
set -x
ui_print " "
ui_print "- UI installation -"
ui_print "   Which UI you want to install?"
ui_print "   Vol Up = Original, Vol Down = ThePBone"
copy_before_uninstall
if chooseport; then
	ui_print "   Original version was selected"
	mv -f "$MODPATH/common/files/JamesDSPManager.apk" "$MODPATH/JamesDSPManager.apk"
	touch "$MODPATH/.apkorig"
	uninstall_app "orig" "$APPVER"
else
	ui_print "   ThePBone version was selected"
	mv -f "$MODPATH/common/files/JamesDSPManagerThePBone.apk" "$MODPATH/JamesDSPManager.apk"
	touch "$MODPATH/.apkpbone"
	uninstall_app "pbone" "$PAPPVER"
fi
set -x
# Audio effects patching 
ui_print " "
ui_print "   Patching existing audio_effects files..."
PARTITIONS="/system /vendor $PARTITIONS"
# shellcheck disable=SC2086
CFGS="$(find $PARTITIONS -type f -name "*audio_effects*.conf" -o -name "*audio_effects*.xml")"
for OFILE in ${CFGS}; do
  FILE="$MODPATH$(echo "$OFILE" | sed "s|^/vendor|/system/vendor|g")"
  FILE="$(echo "$FILE" | sed "s|$MODPATH/odm|$MODPATH/system/odm|g")"
if [ -f "$ORIGDIR$OFILE" ];then
  cp_ch -n "$ORIGDIR$OFILE" "$FILE"
  osp_detect "$FILE"
	if [ "$AIDL" = "true" ];then
	  case $FILE in
		*.conf) sed -i "/jamesdsp {/,/}/d" "$FILE"
				sed -i "/jdsp {/,/}/d" "$FILE"
				sed -i "s/^effects {/effects {\n  jamesdsp {\n    library jdsp\n    uuid f27317f4-c984-4de6-9a90-545759495bf2\n    type f98765f4-c321-5de6-9a45-123459495ab2\n  }/g" "$FILE"
				sed -i "s/^libraries {/libraries {\n  jdsp {\n    path $LIBPATCH\/lib\/soundfx\/libjamesdsp.so\n  }/g" "$FILE";;
		*.xml) sed -i "/jamesdsp/d" "$FILE"
			   sed -i "/jdsp/d" "$FILE"
			   sed -i "/<libraries>/ a\        <library name=\"jdsp\" path=\"libjamesdsp.so\"\/>" "$FILE"
			   sed -i "/<effects>/ a\        <effect name=\"jamesdsp\" library=\"jdsp\" uuid=\"f27317f4-c984-4de6-9a90-545759495bf2\" type=\"f98765f4-c321-5de6-9a45-123459495ab2\"\/>" "$FILE";;
	  esac
	else
	  case $FILE in
		*.conf) sed -i "/jamesdsp {/,/}/d" "$FILE"
				sed -i "/jdsp {/,/}/d" "$FILE"
				sed -i "s/^effects {/effects {\n  jamesdsp {\n    library jdsp\n    uuid f27317f4-c984-4de6-9a90-545759495bf2\n  }/g" "$FILE"
				sed -i "s/^libraries {/libraries {\n  jdsp {\n    path $LIBPATCH\/lib\/soundfx\/libjamesdsp.so\n  }/g" "$FILE";;
		*.xml) sed -i "/jamesdsp/d" "$FILE"
			   sed -i "/jdsp/d" "$FILE"
			   sed -i "/<libraries>/ a\        <library name=\"jdsp\" path=\"libjamesdsp.so\"\/>" "$FILE"
			   sed -i "/<effects>/ a\        <effect name=\"jamesdsp\" library=\"jdsp\" uuid=\"f27317f4-c984-4de6-9a90-545759495bf2\"/>" "$FILE";;
	  esac
	fi
fi
done

# adding executive permissions to jdsp_app.sh
chmod +x "$MODPATH/jdsp_app.sh"

# Kitsune has extra partitions in different location
if [ "$(echo "$MAGISK_VER" | awk -F- '{ print $NF}')" = "kitsune" ]; then
  mkdir "$MODPATH/root"
  for PART in $PARTITIONS; do
    mv -f "$MODPATH/system$PART" "$MODPATH/root"
  done
fi

sed -i "1a NVBASE=$NVBASE" "$MODPATH/service.sh"

ui_print "   Copying apk to /sdcard. Install manually if not present on reboot"
cp -rf "$MODPATH/common/files/JamesDSP" /storage/emulated/0/JamesDSP
cp -f "$MODPATH/JamesDSPManager.apk" /storage/emulated/0/JamesDSPManager.apk
[ "$API" -gt 29 ] && { ui_print "   Enabling hidden api policy"; settings put global hidden_api_policy 1 2>/dev/null; }
