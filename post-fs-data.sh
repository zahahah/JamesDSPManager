#!/system/bin/sh
MODPATH=${0%/*}
MODDIR="$MODPATH"
LOGDIR="$MODPATH/logs"
STATUS="$LOGDIR/late-load.status"
NATIVE_CONTROL_PROVENANCE="$MODPATH/native-control/ldsp-build-provenance.json"
# Older artifacts are retained only in the source tree for historical tests;
# the distributable package contains the verified LightningDSP provenance.
[ -f "$NATIVE_CONTROL_PROVENANCE" ] || NATIVE_CONTROL_PROVENANCE="$MODPATH/native-control/v5-build-provenance.json"
[ -f "$NATIVE_CONTROL_PROVENANCE" ] || NATIVE_CONTROL_PROVENANCE="$MODPATH/native-control/v4-build-provenance.json"
[ -f "$NATIVE_CONTROL_PROVENANCE" ] || NATIVE_CONTROL_PROVENANCE="$MODPATH/native-control/provenance.json"
LDSP_UUID=f27317f4-c984-4de6-9a90-545759495bf2
LDSP_TYPE=f98765f4-c321-5de6-9a45-123459495ab2
PIXEL_DUMP_UUID_ANCHOR=50deaa30-4a83-4b1f-bfe3-dec6d605ede0
LINKER_BIN=${LDSP_LINKER_BIN:-/system/bin/linker64}
FLOCK_BIN=${LDSP_FLOCK_BIN:-/system/bin/flock}
SOURCE_VENDOR_CONFIG=${LDSP_SOURCE_VENDOR_CONFIG:-/vendor/etc/audio_effects_config.xml}
SOURCE_LEGACY_CONFIG=${LDSP_SOURCE_LEGACY_CONFIG:-/system/etc/audio_effects.xml}
GETPROP_BIN=${LDSP_GETPROP_BIN:-/system/bin/getprop}

mkdir -p "$LOGDIR"

# Prepare the global-control overlay before the mount manager consumes it.
[ ! -f "$MODPATH/native-control.sh" ] || sh "$MODPATH/native-control.sh" prepare "$MODPATH"

if [ -d "$MODPATH/system/vendor" ] && [ ! -L "$MODPATH/system/vendor" ]; then
	MOD_VENDOR="$MODPATH/system/vendor"
	MOD_ODM="$MODPATH/system/odm"
else
	MOD_VENDOR="$MODPATH/vendor"
	MOD_ODM="$MODPATH/odm"
fi

# No SDK/model gate: inspect the actual compiled ABI and fail closed on a
# missing dependency. Separate Effect V3/V4 builds are not interchangeable.

ABI_STATUS=validated

late_block() {
	printf 'BLOCKED reason=%s\n' "$1" >"$STATUS"
	touch "$MODPATH/skip_mount"
	exit 0
}

# The normal boot path uses the same strict ABI validation as late-load.
# Validate before preparing the config that makes the replacement discoverable.
if [ "${KSU_LATE_LOAD:-0}" != 1 ] && [ -f "$NATIVE_CONTROL_PROVENANCE" ]; then
	AIDL=true
	. "$MODPATH/patch.sh" >"$LOGDIR/native-control-dependency-check.log" 2>&1 || \
		late_block native_control_dependency_mismatch
fi

late_ready() {
	boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
	printf 'READY late_load=1 boot_id=%s vendor_config=%s lib=%s restart=not_requested processing=unverified\n' \
		"${boot_id:-unknown}" "$1" "$ABI_STATUS" \
		>"$STATUS"
	exit 0
}

patch_lightningdsp_vendor_xml() {
	xml="$1"
	grep -q '<libraries>' "$xml" || late_block vendor_config_missing_libraries_tag
	grep -q '<effects>' "$xml" || late_block vendor_config_missing_effects_tag
	tmp="$xml.tmp.$$"
	awk \
		-v lib='        <library name="ldsp" path="lightningdsplib.so"/>' \
		-v effect="        <effect name=\"lightningdsp\" library=\"ldsp\" uuid=\"$LDSP_UUID\" type=\"$LDSP_TYPE\"/>" '
/lightningdsp/ || /name="ldsp"/ { next }
{ print }
/<libraries>/ && !lib_done { print lib; lib_done = 1 }
/<effects>/ && !effect_done { print effect; effect_done = 1 }
' "$xml" >"$tmp" || late_block vendor_config_patch_failed
	mv -f "$tmp" "$xml" || late_block vendor_config_patch_failed
	grep -qi "$LDSP_UUID" "$xml" || late_block vendor_config_patch_failed
}

prepare_builtin_aidl_config() {
	[ -f "$MODPATH/.AIDL" ] || return 0
	config="$MOD_VENDOR/etc/audio_effects_config.xml"
	tmp="$config.tmp.$$"
	mkdir -p "${config%/*}" || {
		printf 'BLOCKED reason=vendor_config_directory_unavailable\n' \
			>"$LOGDIR/builtin-aidl-config.status"
		return 1
	}
	if [ -f "$SOURCE_VENDOR_CONFIG" ]; then
		cp -f "$SOURCE_VENDOR_CONFIG" "$tmp" || {
			rm -f "$tmp"
			printf 'BLOCKED reason=vendor_config_copy_failed\n' \
				>"$LOGDIR/builtin-aidl-config.status"
			return 1
		}
		config_source=vendor_native
	else
		# Some Pixel builds expose only the legacy system config. Translate it
		# into the AIDL factory's vendor config before Magic Mount consumes the
		# module tree. This is a systemless overlay, not a partition write.
		[ -f "$SOURCE_LEGACY_CONFIG" ] || {
			rm -f "$tmp"
			printf 'BLOCKED reason=system_legacy_config_missing\n' \
				>"$LOGDIR/builtin-aidl-config.status"
			return 1
		}
		awk '
		{
			gsub(/path="libbundlewrapper[.]so"/, "path=\"libbundleaidl.so\"")
			gsub(/path="libreverbwrapper[.]so"/, "path=\"libreverbaidl.so\"")
			gsub(/path="libvisualizer[.]so"/, "path=\"libvisualizeraidl.so\"")
			gsub(/path="libdownmix[.]so"/, "path=\"libdownmixaidl.so\"")
			gsub(/path="libldnhncr[.]so"/, "path=\"libloudnessenhanceraidl.so\"")
			gsub(/path="libdynproc[.]so"/, "path=\"libdynamicsprocessingaidl.so\"")
			gsub(/path="libhapticgenerator[.]so"/, "path=\"libhapticgeneratoraidl.so\"")
			if ($0 ~ /<library name="pre_processing"/) next
			if ($0 ~ /<effect name="(agc|aec|ns)"/) next
			print
		}' "$SOURCE_LEGACY_CONFIG" >"$tmp" || {
			rm -f "$tmp"
			printf 'BLOCKED reason=system_legacy_config_translate_failed\n' \
				>"$LOGDIR/builtin-aidl-config.status"
			return 1
		}
		config_source=system_legacy
	fi
	if ! grep -q '<libraries>' "$tmp" || ! grep -q '<effects>' "$tmp"; then
		rm -f "$tmp"
		printf 'BLOCKED reason=vendor_config_missing_sections\n' \
			>"$LOGDIR/builtin-aidl-config.status"
		return 1
	fi
	awk \
		-v lib='        <library name="ldsp" path="lightningdsplib.so"/>' \
		-v effect="        <effect name=\"lightningdsp\" library=\"ldsp\" uuid=\"$LDSP_UUID\" type=\"$LDSP_TYPE\"/>" '
	/<!--/ { comment=1 }
	comment { print; if (/-->/) comment=0; next }
	/^[[:space:]]*<library[[:space:]][^>]*name="ldsp"/ { next }
	/^[[:space:]]*<effect[[:space:]][^>]*name="lightningdsp"/ { next }
	{ print }
	/<libraries>/ && !lib_done { print lib; lib_done = 1 }
	/<effects>/ && !effect_done { print effect; effect_done = 1 }
	END { if (!lib_done || !effect_done) exit 2 }
	' "$tmp" >"$tmp.patched" || {
		rm -f "$tmp" "$tmp.patched"
		printf 'BLOCKED reason=vendor_config_patch_failed\n' \
			>"$LOGDIR/builtin-aidl-config.status"
		return 1
	}
	if ! grep -qi "$LDSP_UUID" "$tmp.patched" || ! grep -qi 'name="ldsp"' "$tmp.patched"; then
		rm -f "$tmp" "$tmp.patched"
		printf 'BLOCKED reason=vendor_config_validation_failed\n' \
			>"$LOGDIR/builtin-aidl-config.status"
		return 1
	fi
	mv -f "$tmp.patched" "$config" || {
		rm -f "$tmp" "$tmp.patched"
		printf 'BLOCKED reason=vendor_config_commit_failed\n' \
			>"$LOGDIR/builtin-aidl-config.status"
		return 1
	}
	rm -f "$tmp"
	printf 'READY mode=builtin source=%s config=%s systemless=1 reload=not_requested\n' \
		"$config_source" "$config" >"$LOGDIR/builtin-aidl-config.status"
}

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
	[ -f "$MODPATH/.AIDL" ] || late_block aidl_marker_missing
	[ -f "$MOD_VENDOR/lib64/soundfx/lightningdsplib.so" ] || \
		late_block lightningdsp_lib_missing
	mkdir -p "$MOD_VENDOR/etc"
	if [ -f "$SOURCE_VENDOR_CONFIG" ]; then
		tmp="$MOD_VENDOR/etc/audio_effects_config.xml.tmp.$$"
		cp -f "$SOURCE_VENDOR_CONFIG" "$tmp" || \
			late_block vendor_config_copy_failed
		mv -f "$tmp" "$MOD_VENDOR/etc/audio_effects_config.xml" || \
			late_block vendor_config_copy_failed
		vendor_config_source=patched_from_live_vendor
	else
		# Like the ViPER AIDL module, use a dedicated minimal AIDL config
		# when that file is absent. Do not invent vendor library names by
		# translating a legacy system XML using Pixel-specific aliases.
		tmp="$MOD_VENDOR/etc/audio_effects_config.xml.tmp.$$"
		cat >"$tmp" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<audio_effects_conf version="2.0" xmlns="http://schemas.android.com/audio/audio_effects_conf/v2_0">
    <libraries>
    </libraries>
    <effects>
    </effects>
</audio_effects_conf>
XML
		[ "$?" -eq 0 ] && mv -f "$tmp" "$MOD_VENDOR/etc/audio_effects_config.xml" || \
			late_block dedicated_aidl_config_write_failed
		vendor_config_source=dedicated_aidl_template
	fi
	patch_lightningdsp_vendor_xml "$MOD_VENDOR/etc/audio_effects_config.xml"
	grep -q 'path="libaudiopreprocessing.so"' \
		"$MOD_VENDOR/etc/audio_effects_config.xml" && \
		late_block system_legacy_preprocessing_not_removed

	AIDL=true
	if [ -f "$MODPATH/patch.sh" ]; then
		# Validate the compiled ABI without rewriting or skipping failed checks.
		. "$MODPATH/patch.sh" >"$LOGDIR/late-load-patch.log" 2>&1 || \
			late_block patchelf_failed
	fi

	if ! "$LINKER_BIN" --list \
		"$MOD_VENDOR/lib64/soundfx/lightningdsplib.so" \
		>"$LOGDIR/late-load-linker.txt" 2>&1; then
		late_block linker_dependency_resolution_failed
	fi

	late_ready "$vendor_config_source"
fi

# The regular KernelSU boot path still needs an AIDL factory config. Prepare
# it before the module overlay is mounted, without entering late-load's reload
# flow or changing its markers, locking, linker checks, or service behavior.
if [ "${KSU_LATE_LOAD:-0}" != 1 ] && [ -f "$MODPATH/.AIDL" ]; then
	prepare_builtin_aidl_config || :
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
if [ ! -f "$NATIVE_CONTROL_PROVENANCE" ]; then
	. "$MODPATH/patch.sh"
fi
