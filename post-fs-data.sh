#!/system/bin/sh
MODPATH=${0%/*}
MODDIR="$MODPATH"
LOGDIR="$MODPATH/logs"
STATUS="$LOGDIR/late-load.status"
JDSP_UUID=f27317f4-c984-4de6-9a90-545759495bf2
JDSP_TYPE=f98765f4-c321-5de6-9a45-123459495ab2
XML_LIB_ANCHOR=libbundleaidl.so
XML_UUID_ANCHOR=ce772f20-847d-11df-bb17-0002a5d5c51b
PIXEL_DUMP_UUID_ANCHOR=50deaa30-4a83-4b1f-bfe3-dec6d605ede0
LINKER_BIN=${JDSP_LINKER_BIN:-/system/bin/linker64}
FLOCK_BIN=${JDSP_FLOCK_BIN:-/system/bin/flock}
SOURCE_VENDOR_CONFIG=${JDSP_SOURCE_VENDOR_CONFIG:-/vendor/etc/audio_effects_config.xml}
SOURCE_LEGACY_CONFIG=${JDSP_SOURCE_LEGACY_CONFIG:-/system/etc/audio_effects.xml}

mkdir -p "$LOGDIR"

late_block() {
	printf 'BLOCKED reason=%s\n' "$1" >"$STATUS"
	touch "$MODPATH/skip_mount"
	exit 0
}

late_ready() {
	printf 'READY late_load=1 vendor_config=%s lib=patched restart=service\n' "$1" \
		>"$STATUS"
	exit 0
}

patch_jdsp_vendor_xml() {
	xml="$1"
	grep -qi "$XML_LIB_ANCHOR" "$xml" || \
		late_block vendor_config_missing_xml_lib_anchor
	grep -qi "$XML_UUID_ANCHOR" "$xml" || \
		late_block vendor_config_missing_xml_uuid_anchor
	grep -q '<libraries>' "$xml" || late_block vendor_config_missing_libraries_tag
	grep -q '<effects>' "$xml" || late_block vendor_config_missing_effects_tag
	tmp="$xml.tmp.$$"
	awk \
		-v lib='        <library name="jdsp" path="libjamesdsp.so"/>' \
		-v effect="        <effect name=\"jamesdsp\" library=\"jdsp\" uuid=\"$JDSP_UUID\" type=\"$JDSP_TYPE\"/>" '
/jamesdsp/ || /name="jdsp"/ { next }
{ print }
/<libraries>/ && !lib_done { print lib; lib_done = 1 }
/<effects>/ && !effect_done { print effect; effect_done = 1 }
' "$xml" >"$tmp" || late_block vendor_config_patch_failed
	mv -f "$tmp" "$xml" || late_block vendor_config_patch_failed
	grep -qi "$JDSP_UUID" "$xml" || late_block vendor_config_patch_failed
	grep -qi "$XML_UUID_ANCHOR" "$xml" || \
		late_block vendor_config_xml_anchor_lost
}

legacy_xml_to_aidl_config() {
	src="$1"
	dst="$2"
	[ -f "$src" ] || late_block system_legacy_config_missing
	tmp="$dst.tmp.$$"
	awk '
	{
		gsub(/path="libbundlewrapper[.]so"/, "path=\"libbundleaidl.so\"")
		gsub(/path="libreverbwrapper[.]so"/, "path=\"libreverbaidl.so\"")
		gsub(/path="libvisualizer[.]so"/, "path=\"libvisualizeraidl.so\"")
		gsub(/path="libdownmix[.]so"/, "path=\"libdownmixaidl.so\"")
		gsub(/path="libldnhncr[.]so"/, "path=\"libloudnessenhanceraidl.so\"")
		gsub(/path="libdynproc[.]so"/, "path=\"libdynamicsprocessingaidl.so\"")
		gsub(/path="libhapticgenerator[.]so"/, "path=\"libhapticgeneratoraidl.so\"")
		# Mustang does not expose a separate AIDL preprocessing library.
		# The stock factory already provides AEC/NS descriptors, so the
		# legacy HIDL stanza would point the AIDL loader at the wrong ABI.
		if ($0 ~ /<library name="pre_processing"/) next
		if ($0 ~ /<effect name="(agc|aec|ns)"/) next
		print
	}' "$src" >"$tmp" || late_block system_legacy_config_translate_failed
	mv -f "$tmp" "$dst" || late_block system_legacy_config_translate_failed
}

if [ -d "$MODPATH/system/vendor" ] && [ ! -L "$MODPATH/system/vendor" ]; then
	MOD_VENDOR="$MODPATH/system/vendor"
	MOD_ODM="$MODPATH/system/odm"
else
	MOD_VENDOR="$MODPATH/vendor"
	MOD_ODM="$MODPATH/odm"
fi

if [ "${KSU_LATE_LOAD:-0}" = 1 ]; then
	# KernelSU Next reaches this stage before Magic Mount-rs consumes the
	# module tree. Prepare the systemless files here, then let the overlay
	# mount. Multiple KernelSU callbacks must not update shared module files
	# concurrently; the lock is released automatically when this script exits.
	[ -x "$FLOCK_BIN" ] || late_block late_load_lock_unavailable
	exec 9>"$LOGDIR/late-load-prepare.lock" || \
		late_block late_load_lock_open_failed
	"$FLOCK_BIN" -x 9 || late_block late_load_lock_failed

	rm -f "$MODPATH/skip_mount" "$MODPATH/.late-load-no-effect" \
		"$MODPATH/.late-load-rootless"
	touch "$MODPATH/.late-load-reload-experimental"

	[ -f "$MODPATH/.AIDL" ] || late_block aidl_marker_missing
	[ -f "$MOD_VENDOR/lib64/soundfx/libjamesdsp.so" ] || \
		late_block jamesdsp_lib_missing
	mkdir -p "$MOD_VENDOR/etc"
	if [ -f "$SOURCE_VENDOR_CONFIG" ]; then
		tmp="$MOD_VENDOR/etc/audio_effects_config.xml.tmp.$$"
		cp -f "$SOURCE_VENDOR_CONFIG" "$tmp" || \
			late_block vendor_config_copy_failed
		mv -f "$tmp" "$MOD_VENDOR/etc/audio_effects_config.xml" || \
			late_block vendor_config_copy_failed
		vendor_config_source=patched_from_live_vendor
	else
		legacy_xml_to_aidl_config "$SOURCE_LEGACY_CONFIG" \
			"$MOD_VENDOR/etc/audio_effects_config.xml"
		vendor_config_source=generated_from_system_legacy
	fi
	patch_jdsp_vendor_xml "$MOD_VENDOR/etc/audio_effects_config.xml"
	grep -q 'path="libaudiopreprocessing.so"' \
		"$MOD_VENDOR/etc/audio_effects_config.xml" && \
		late_block system_legacy_preprocessing_not_removed

	AIDL=true
	if [ -f "$MODPATH/patch.sh" ]; then
		# Patch AIDL NDK SONAMEs to the live firmware before the library is
		# mounted into /vendor/lib64/soundfx.
		. "$MODPATH/patch.sh" >"$LOGDIR/late-load-patch.log" 2>&1 || \
			late_block patchelf_failed
	fi

	if ! "$LINKER_BIN" --list \
		"$MOD_VENDOR/lib64/soundfx/libjamesdsp.so" \
		>"$LOGDIR/late-load-linker.txt" 2>&1; then
		late_block linker_dependency_resolution_failed
	fi

	late_ready "$vendor_config_source"
fi

# Clear only our late-load markers before the built-in early-boot mount.
# Keep support for the marker from the superseded rootless-bundled candidate.
if [ -f "$MODPATH/.late-load-no-effect" ] || [ -f "$MODPATH/.late-load-rootless" ] || [ -f "$MODPATH/.late-load-reload-experimental" ]; then
	rm -f "$MODPATH/skip_mount" "$MODPATH/.late-load-no-effect" \
		"$MODPATH/.late-load-rootless" \
		"$MODPATH/.late-load-reload-experimental"
fi
exec 2>"$MODPATH/logs/post-fs-debug.txt"
set -x

if [ -f $MODPATH/.AIDL ];then
	AIDL=true
else
	AIDL=false
fi
. "$MODPATH/aml.sh"
. "$MODPATH/patch.sh"
