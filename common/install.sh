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

copy_profile_backup() {
	APPLOC="/storage/emulated/0/Android/data/james.dsp"

	if [ -d "$APPLOC" ]; then
		mkdir -p "$MODPATH"/JamesDSP
		cp -rf "$APPLOC"/files/* "$MODPATH"/JamesDSP
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

# The v6 payload is already a single ARM64 ELF; lshal is not required for
# choosing it (and can crash on some temp-root firmware environments).
LIB=
LIB2=
if [ ! -f "$MODPATH/native-control/v6-candidate.json" ]; then
#Lib detection
LIB=$(lshal debug "$(lshal | grep -oE "android.hardware.audio.effect@[0-9]+\.[0-9]+::IEffectsFactory/default" | head -n 1)" | grep -E 'lib|lib64' | awk -F '/' 'NR==1{print $3}')

LIB2=$(file /*/bin/hw/android.hardware.audio.service* 2>/dev/null | grep -oE "32-bit|64-bit" | head -n 1)

fi

if service list | grep -Fq "android.hardware.audio.effect.IFactory"; then
AIDL=true
else
AIDL=false
fi

# Factory enumeration describes this installer's Binder view, not the payload
# ABI or what a late-started HAL will discover. V5 ships only ARM64 AIDL: select
# that candidate even when enumeration is inconclusive, never a missing legacy
# driver. Actual loading/registration remain separate runtime checks.
if [ -f "$MODPATH/native-control/v6-candidate.json" ]; then
    case ",$(getprop ro.product.cpu.abilist64)," in
        *,arm64-v8a,*) ;;
        *) abort "! LightningDSP v6 contains one ARM64 driver; no matching device ABI found." ;;
    esac
    mkdir -p "$MODPATH/logs" || abort "! Cannot create installer diagnostics."
    discovery=not_observed
    [ "$AIDL" != true ] || discovery=aidl_observed
    printf 'SELECTED payload=dual-entry-arm64 factory_discovery=%s compatibility=unverified processing=unverified\n' \
        "$discovery" >"$MODPATH/logs/install-transport.status" || abort "! Cannot record transport diagnostics."
    # .AIDL retains the existing embedded-profile overlay/dependency hooks. It
    # is not a claim of the device's transport. Both ABIs use the SAME payload.
    AIDL=true
    touch "$MODPATH/.DUAL_ENTRY"
fi
if [ -f "$MODPATH/native-control/v5-candidate.json" ] && [ ! -f "$MODPATH/native-control/v6-candidate.json" ]; then
    case ",$(getprop ro.product.cpu.abilist64)," in
        *,arm64-v8a,*) ;;
        *) abort "! Embedded v5 contains only the ARM64 driver; no matching device ABI found." ;;
    esac
    FACTORY_DISCOVERY=not_observed
    if [ "$AIDL" = true ]; then
        FACTORY_DISCOVERY=observed
    else
        ui_print "   ! AIDL effect factory was not visible to the installer."
        ui_print "   ! Staging the AIDL candidate; runtime compatibility is unverified."
        ui_print "   ! This ZIP contains no legacy/HIDL driver."
    fi
    AIDL=true
    mkdir -p "$MODPATH/logs" || abort "! Cannot create installer diagnostics."
    printf 'SELECTED payload=aidl-arm64 factory_discovery=%s compatibility=unverified processing=unverified\n' \
        "$FACTORY_DISCOVERY" >"$MODPATH/logs/install-transport.status" || abort "! Cannot record installer transport selection."
fi

ui_print " "
ui_print "- Lib bit detection -"

if [ "$AIDL" = "true" ]; then
	QARCH="aidl"
	if [ -f "$MODPATH/native-control/v6-candidate.json" ]; then
		ui_print "   Installing one ARM64 dual-entry AIDL/legacy driver"
	elif [ -f "$MODPATH/native-control/v5-candidate.json" ]; then
		ui_print "   Installing embedded ARM64 AIDL candidate"
	else
		ui_print "  AIDL libs detected "
	fi
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

# The AIDL candidate is ELF64. Do not duplicate it into the 32-bit library tree.
if [ "$QARCH" != aidl ]; then
    cp_ch "$MODPATH/common/files/$QARCH/libjamesdsp.so" "$MODPATH/system/lib/soundfx/libjamesdsp.so"
fi

ui_print " "
ui_print "- UI installation -"
ui_print "   Installing ThePBone 1.6.17 root app"
ui_print "   APK uses the current maintainer signing key"
ui_print "   Same-signature apps are updated in place"
ui_print "   Different signatures require explicit volume-key confirmation"
copy_profile_backup
mv -f "$MODPATH/common/files/JamesDSPManagerThePBone.apk" "$MODPATH/JamesDSPManager.apk"
touch "$MODPATH/.apkpbone"

[ ! -f "$MODPATH/native-control.sh" ] || sh "$MODPATH/native-control.sh" prepare "$MODPATH"

set -x
# Audio effects patching 
ui_print " "
ui_print "   Patching existing audio_effects files..."
CONFIG_LIBDIR=lib
[ "$QARCH" != aidl ] || CONFIG_LIBDIR=lib64
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
				sed -i "s/^libraries {/libraries {\n  jdsp {\n    path $LIBPATCH\/$CONFIG_LIBDIR\/soundfx\/libjamesdsp.so\n  }/g" "$FILE";;
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
				sed -i "s/^libraries {/libraries {\n  jdsp {\n    path $LIBPATCH\/$CONFIG_LIBDIR\/soundfx\/libjamesdsp.so\n  }/g" "$FILE";;
		*.xml) sed -i "/jamesdsp/d" "$FILE"
			   sed -i "/jdsp/d" "$FILE"
			   sed -i "/<libraries>/ a\        <library name=\"jdsp\" path=\"libjamesdsp.so\"\/>" "$FILE"
			   sed -i "/<effects>/ a\        <effect name=\"jamesdsp\" library=\"jdsp\" uuid=\"f27317f4-c984-4de6-9a90-545759495bf2\"/>" "$FILE";;
	  esac
	fi
fi
done

# Keep the app helper executable after installer file normalization
chmod +x "$MODPATH/jdsp_app.sh"

# Kitsune has extra partitions in different location
if [ "$(echo "$MAGISK_VER" | awk -F- '{ print $NF}')" = "kitsune" ]; then
  mkdir "$MODPATH/root"
  for PART in $PARTITIONS; do
    mv -f "$MODPATH/system$PART" "$MODPATH/root"
  done
fi

sed -i "1a NVBASE=$NVBASE" "$MODPATH/service.sh"

ui_print "   Staging the selected APK to /sdcard as a manual-install fallback"
cp -rf "$MODPATH/common/files/JamesDSP" /storage/emulated/0/JamesDSP
cp -f "$MODPATH/JamesDSPManager.apk" /storage/emulated/0/JamesDSPManager.apk
# Handle upgrades while the installer UI can display the bounded confirmation.
# On recovery or when Package Manager is unavailable, service.sh retries safely.
chmod +x "$MODPATH/jdsp_app.sh"
if command -v cmd >/dev/null 2>&1; then
  APP_PACKAGE_LIST=$(cmd package list packages 2>/dev/null)
  APP_PM="cmd package"
else
  APP_PACKAGE_LIST=$(pm list packages 2>/dev/null)
  APP_PM="pm"
fi
if echo "$APP_PACKAGE_LIST" | grep -Fqx "package:james.dsp"; then
  ui_print "   Checking whether the installed app can be safely updated..."
  MODPATH="$MODPATH" JDSP_FLASH_INSTALL=1 JDSP_PM_CMD="$APP_PM" sh "$MODPATH/jdsp_app.sh"
else
  ui_print "   No installed app detected; first install will run after boot"
fi
[ "$API" -gt 29 ] && { ui_print "   Enabling hidden api policy"; settings put global hidden_api_policy 1 2>/dev/null; }
