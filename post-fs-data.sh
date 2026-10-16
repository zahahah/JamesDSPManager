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
GETPROP_BIN=${JDSP_GETPROP_BIN:-/system/bin/getprop}
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
	if [ "${JDSP_PROFILE:-}" != mustang ]; then
		printf 'READY late_load=1 vendor_config=%s profile=%s lib=exact restart=not_requested\n' "$1" "$JDSP_PROFILE" >"$STATUS"
		exit 0
	fi
	printf 'READY late_load=1 vendor_config=%s lib=patched restart=service\n' "$1" \
		>"$STATUS"
	exit 0
}

detect_jdsp_profile() {
	if [ -n "${JDSP_COMPAT_PROFILE:-}" ]; then
		printf '%s\n' "$JDSP_COMPAT_PROFILE"
		return
	fi
	device=''
	if [ -x "$GETPROP_BIN" ]; then
		device=$($GETPROP_BIN ro.product.device 2>/dev/null | tr '[:upper:]' '[:lower:]')
		[ -n "$device" ] || \
			device=$($GETPROP_BIN ro.build.product 2>/dev/null | tr '[:upper:]' '[:lower:]')
	fi
	case "$device" in
		mustang) printf 'mustang\n' ;;
		h8q) printf 'samsung_h8q\n' ;;
		*) printf 'portable\n' ;;
	esac
}

write_late_context() {
	context="$LOGDIR/late-load-context.txt"
	boot_id=$(cat "${JDSP_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}" 2>/dev/null || printf unknown)
	{
		printf 'timestamp=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || printf unknown)"
		printf 'boot_id=%s\n' "$boot_id"
		printf 'profile=%s\n' "$JDSP_PROFILE"
		printf 'module_vendor=%s\n' "$MOD_VENDOR"
		printf 'module_odm=%s\n' "$MOD_ODM"
		printf 'source_vendor_config=%s\n' "$SOURCE_VENDOR_CONFIG"
		printf 'source_legacy_config=%s\n' "$SOURCE_LEGACY_CONFIG"
		printf 'config_roots=%s\n' "${JDSP_CONFIG_ROOTS:-default}"
	} >"$context"
}

resolve_flock() {
	if [ -n "${JDSP_FLOCK_BIN:-}" ]; then
		[ -x "$JDSP_FLOCK_BIN" ] || return 1
		FLOCK_MODE=standalone
		FLOCK_BIN="$JDSP_FLOCK_BIN"
		return 0
	fi
	if [ -x /system/bin/flock ]; then
		FLOCK_MODE=standalone
		FLOCK_BIN=/system/bin/flock
		return 0
	fi
	for bb in /data/adb/ksu/bin/busybox /data/adb/ksu/bin/busybox64 /data/adb/magisk/busybox /system/bin/busybox; do
		if [ -x "$bb" ] && "$bb" flock --help >/dev/null 2>&1; then
			FLOCK_MODE=busybox
			FLOCK_BIN="$bb"
			return 0
		fi
	done
	return 1
}

jdsp_lock_fd9() {
	case "$FLOCK_MODE" in
		standalone) "$FLOCK_BIN" -x 9 ;;
		busybox) "$FLOCK_BIN" flock -x 9 ;;
		*) return 1 ;;
	esac
}

patch_jdsp_vendor_xml() {
	xml="$1"
	profile="$2"
	grep -q '<libraries>' "$xml" || late_block vendor_config_missing_libraries_tag
	grep -q '<effects>' "$xml" || late_block vendor_config_missing_effects_tag
	if [ "$profile" = mustang ]; then
		grep -qi "$XML_LIB_ANCHOR" "$xml" || \
			late_block vendor_config_missing_xml_lib_anchor
		grep -qi "$XML_UUID_ANCHOR" "$xml" || \
			late_block vendor_config_missing_xml_uuid_anchor
	fi
	xml_tmp="$xml.tmp.$$"
	awk \
		-v lib='        <library name="jdsp" path="libjamesdsp.so"/>' \
		-v effect="        <effect name=\"jamesdsp\" library=\"jdsp\" uuid=\"$JDSP_UUID\" type=\"$JDSP_TYPE\"/>" '
	/<!--/ { comment=1 }
	comment { print; if (/-->/) comment=0; next }
	/^[[:space:]]*<library[[:space:]][^>]*name="jdsp"/ { next }
	/^[[:space:]]*<effect[[:space:]][^>]*name="jamesdsp"/ { next }
	{ print }
	/<libraries>/ && !lib_done { print lib; lib_done = 1 }
	/<effects>/ && !effect_done { print effect; effect_done = 1 }
	END { if (!lib_done || !effect_done) exit 2 }
	' "$xml" >"$xml_tmp" || late_block vendor_config_patch_failed
	mv -f "$xml_tmp" "$xml" || late_block vendor_config_patch_failed
	grep -qi "$JDSP_UUID" "$xml" || late_block vendor_config_patch_failed
	grep -qi 'name="jdsp"' "$xml" || late_block vendor_config_patch_failed
	if [ "$profile" = mustang ]; then
		grep -qi "$XML_UUID_ANCHOR" "$xml" || \
			late_block vendor_config_xml_anchor_lost
	fi
}

module_path_for_config() {
	logical="$1"
	if [ -n "${JDSP_FS_ROOT:-}" ]; then
		case "$logical" in
			"$JDSP_FS_ROOT"/*) logical="/${logical#"$JDSP_FS_ROOT"/}" ;;
		esac
	fi
	case "$logical" in
		/vendor/*) printf '%s/%s\n' "$MOD_VENDOR" "${logical#/vendor/}" ;;
		/odm/*) printf '%s/%s\n' "$MOD_ODM" "${logical#/odm/}" ;;
		/system_ext/*) printf '%s/system_ext/%s\n' "$MODPATH/system" "${logical#/system_ext/}" ;;
		/product/*) printf '%s/product/%s\n' "$MODPATH/system" "${logical#/product/}" ;;
		/system/*) printf '%s/%s\n' "$MODPATH/system" "${logical#/system/}" ;;
		*) return 1 ;;
	esac
}

logical_config_path() {
	logical="$1"
	if [ -n "${JDSP_FS_ROOT:-}" ]; then
		case "$logical" in
			"$JDSP_FS_ROOT"/*) logical="/${logical#"$JDSP_FS_ROOT"/}" ;;
		esac
	fi
	printf '%s\n' "$logical"
}

is_native_aidl_xml() {
	[ -f "$1" ] || return 1
	case "$1" in
		*audio_effects_config*.xml) ;;
		*audio_effects.xml|*audio_effects_sec.xml)
			# Some Samsung AIDL factories retain legacy-looking file names. Require
			# an AIDL-suffixed library so legacy wrapper configs stay untouched.
			grep -Eq 'path="[^"]*aidl[.]so"' "$1" || return 1 ;;
		*) return 1 ;;
	esac
	# Bounded line-oriented XML validation, not a general XML parser. Unsupported
	# constructs are rejected before touching the mountable destination.
	awk '
	function attr(t, key, v) {
		if (!match(t, "[[:space:]]" key "=\"[^\"]*\"")) return ""
		v=substr(t, RSTART, RLENGTH); sub(/^[^=]*="/, "", v); sub(/"$/, "", v); return v
	}
	{
		line=$0; sub(/^[[:space:]]*/, "", line); sub(/[[:space:]]*$/, "", line)
		if (comment) { if (line ~ /-->/) { if (line !~ /-->$/) exit 1; comment=0 }; next }
		if (line ~ /^<!--/) { if (line ~ /-->/) { if (line !~ /-->$/) exit 1 } else comment=1; next }
		if (!length(line)) next
		if (line ~ /^<\?xml[^<>]*\?>$/) { if (roots || depth) exit 1; next }
		if (line !~ /^<[^<>]*>$/) exit 1
		tag=line; closing=(tag ~ /^<\//); empty=(tag ~ /\/>$/)
		sub(/^<\/?/, "", tag); sub(/[[:space:]\/>].*$/, "", tag)
		if (tag !~ /^[A-Za-z_][A-Za-z0-9_.:-]*$/) exit 1
		if (closing) {
			if (line != "</" tag ">" || depth < 1 || stack[depth] != tag) exit 1
			depth--; if (!depth) closed=1; next
		}
		if (closed) exit 1
		if (!depth) { if (tag != "audio_effects_conf" || empty || ++roots != 1) exit 1 }
		if (tag == "libraries" || tag == "effects") {
			if (depth != 1 || empty || line != "<" tag ">") exit 1
			if (tag == "libraries") libraries++; else effects++
		}
		if (tag == "library") {
			if (stack[depth] != "libraries" || !empty) exit 1
			name=attr(line,"name"); path=attr(line,"path")
			if (!length(name) || !length(path) || libs[name]++) exit 1
		}
		if (tag == "effect") {
			if (stack[depth] != "effects" || !empty) exit 1
			name=attr(line,"name"); lib=attr(line,"library")
			if (!length(name) || !length(lib) || !length(attr(line,"uuid")) || !libs[lib] || fx[name]++) exit 1
		}
		if (!empty) stack[++depth]=tag
	}
	END { if (comment || depth || roots != 1 || !closed || libraries != 1 || effects != 1) exit 1 }
	' "$1"
}

prepare_one_portable_config() {
	src="$1"
	is_native_aidl_xml "$src" || late_block native_vendor_config_unsupported
	dst=$(module_path_for_config "$src") || late_block native_vendor_config_path_unsupported
	mkdir -p "${dst%/*}" || late_block vendor_config_copy_failed
	tmp="$dst.tmp.$$"
	cp -f "$src" "$tmp" || late_block vendor_config_copy_failed
	patch_jdsp_vendor_xml "$tmp" portable
	mv -f "$tmp" "$dst" || late_block vendor_config_copy_failed
	logical=$(logical_config_path "$src")
	printf 'native_config_candidate=%s not_proven_factory_path=1\nprepared_config=%s -> %s\n' "$logical" "$logical" "$dst" \
		>>"$LOGDIR/late-load-context.txt"
	JDSP_PREPARED_CONFIG_DSTS="${JDSP_PREPARED_CONFIG_DSTS}${JDSP_PREPARED_CONFIG_DSTS:+
}$dst"
	if [ -z "$JDSP_PREPARED_CONFIG_FIRST" ]; then
		JDSP_PREPARED_CONFIG_FIRST=1
		printf 'prepared_config_1=%s -> %s\n' "$logical" "$dst" \
			>>"$LOGDIR/late-load-context.txt"
	fi
	vendor_config_source="portable_native_aidl_config:$logical"
}

reject_unvalidated_portable_payloads() {
	unexpected=""
	for file in $(find "$MODPATH/system" "$MOD_VENDOR" "$MOD_ODM" -type f \( -name "*audio_effects*.xml" -o -name "*audio_effects*.conf" \) 2>/dev/null); do
		if printf '%s\n' "$JDSP_PREPARED_CONFIG_DSTS" | grep -Fqx "$file"; then
			continue
		fi
		case " $unexpected " in *" $file "*) continue ;; esac
		unexpected="$unexpected $file"
	done
	if [ -n "$unexpected" ]; then
		printf 'unvalidated_config_payloads=%s\n' "$unexpected" \
			>>"$LOGDIR/late-load-context.txt"
		late_block portable_unvalidated_config_payload
	fi
}

prepare_portable_native_configs() {
	roots=${JDSP_CONFIG_ROOTS:-/vendor/etc /odm/etc /system/etc /product/etc /system_ext/etc}
	if [ -f "$SOURCE_VENDOR_CONFIG" ]; then
		prepare_one_portable_config "$SOURCE_VENDOR_CONFIG"
		return
	fi
	canonical=""
	candidates=""
	for root in $roots; do
		[ -d "$root" ] || continue
		if [ -f "$root/audio_effects_config.xml" ]; then
			logical=$(logical_config_path "$root/audio_effects_config.xml")
			if [ "$logical" = /vendor/etc/audio_effects_config.xml ]; then
				canonical="$root/audio_effects_config.xml"
			fi
			candidates="$candidates $root/audio_effects_config.xml"
		fi
		if [ "$JDSP_PROFILE" = samsung_h8q ]; then
			config_globs='audio_effects_config*.xml audio_effects.xml audio_effects_sec.xml'
		else
			config_globs='audio_effects_config.xml'
		fi
		for pattern in $config_globs; do
			for file in "$root"/$pattern "$root"/audio/*$pattern "$root"/audio/sku_*/*$pattern "$root"/sku_*/*$pattern; do
				[ -f "$file" ] || continue
				case " $candidates " in *" $file "*) continue ;; esac
				candidates="$candidates $file"
			done
		done
	done
	if [ -n "$canonical" ] && [ "$JDSP_PROFILE" != samsung_h8q ]; then
		prepare_one_portable_config "$canonical"
		return
	fi
	valid=""
	valid_sources=""
	count=0
	for src in $candidates; do
		if is_native_aidl_xml "$src"; then
			valid="$valid $(logical_config_path "$src")"
			valid_sources="$valid_sources $src"
			count=$((count + 1))
		else
			printf 'portable_candidate_unsupported=%s\n' \
				"$(logical_config_path "$src")" >>"$LOGDIR/late-load-context.txt"
			[ "$JDSP_PROFILE" = samsung_h8q ] || late_block native_vendor_config_unsupported
		fi
	done
	printf 'portable_candidate_count=%s%s\n' "$count" "$valid" \
		>>"$LOGDIR/late-load-context.txt"
	[ "$count" -gt 0 ] || late_block native_vendor_config_missing

	# SKU directories contain mutually exclusive device configs (Samsung
	# commonly ships several). Patch each validated variant within the highest
	# priority partition so the active SKU has the effect, without copying or
	# translating configs from unrelated partitions.
	selected_partition=""
	for src in $valid_sources; do
		logical=$(logical_config_path "$src")
		case "$logical" in
			/vendor/*) partition=vendor ;;
			/odm/*) partition=odm ;;
			/system/*) partition=system ;;
			/product/*) partition=product ;;
			/system_ext/*) partition=system_ext ;;
			*) continue ;;
		esac
		if [ -z "$selected_partition" ]; then selected_partition="$partition"; fi
		[ "$partition" = "$selected_partition" ] || continue
		prepare_one_portable_config "$src"
	done
	if [ "$JDSP_PROFILE" = samsung_h8q ] && [ ! -f "$SOURCE_VENDOR_CONFIG" ]; then
		# Standard AIDL effect factories resolve audio_effects_config.xml by its
		# canonical partition path. Samsung's SKU XMLs may be visible in the
		# mount namespace but never consulted by that factory. Only promote a
		# full SKU config when all discovered full SKU variants are identical;
		# do not guess across materially different device configurations.
		canonical_src=""
		canonical_staged=""
		for src in $valid_sources; do
			logical=$(logical_config_path "$src")
			case "$logical" in
				/vendor/etc/audio/sku_*/audio_effects_config.xml) ;;
				*) continue ;;
			esac
			staged=$(module_path_for_config "$src") || late_block vendor_config_copy_failed
			if [ -z "$canonical_src" ]; then
				canonical_src="$logical"
				canonical_staged="$staged"
			elif ! cmp -s "$canonical_staged" "$staged"; then
				printf 'samsung_canonical_config_variant_mismatch=%s,%s\n' \
					"$canonical_src" "$logical" >>"$LOGDIR/late-load-context.txt"
				late_block samsung_factory_canonical_config_ambiguous
			fi
		done
		[ -n "$canonical_staged" ] || late_block samsung_factory_canonical_config_missing
		canonical_dst="$MOD_VENDOR/etc/audio_effects_config.xml"
		mkdir -p "${canonical_dst%/*}" || late_block vendor_config_copy_failed
		canonical_tmp="$canonical_dst.tmp.$$"
		cp -f "$canonical_staged" "$canonical_tmp" || late_block vendor_config_copy_failed
		mv -f "$canonical_tmp" "$canonical_dst" || late_block vendor_config_copy_failed
		JDSP_PREPARED_CONFIG_DSTS="${JDSP_PREPARED_CONFIG_DSTS}${JDSP_PREPARED_CONFIG_DSTS:+
}$canonical_dst"
		printf 'samsung_factory_config=%s -> /vendor/etc/audio_effects_config.xml\n' \
			"$canonical_src" >>"$LOGDIR/late-load-context.txt"
		vendor_config_source="portable_native_aidl_config:/vendor/etc/audio_effects_config.xml"
	fi
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
	JDSP_PROFILE=$(detect_jdsp_profile)
	# Experimental Samsung builds may capture factory startup before the
	# descriptor cache is constructed. Stable packages omit this script.
	if [ "$JDSP_PROFILE" = samsung_h8q ] &&
		[ -f "$MODPATH/samsung-aidl-early-log.sh" ]; then
		sh "$MODPATH/samsung-aidl-early-log.sh" >/dev/null 2>&1 &
	fi
	resolve_flock || late_block late_load_lock_unavailable
	exec 9>"$LOGDIR/late-load-prepare.lock" || \
		late_block late_load_lock_open_failed
	jdsp_lock_fd9 || late_block late_load_lock_failed

	# Remove stale late-stage state only after the lock is held; service.sh and
	# audio-reload.sh will write fresh state for this exact preparation attempt.
	rm -f "$MODPATH/skip_mount" "$MODPATH/.late-load-no-effect" \
		"$MODPATH/.late-load-rootless" \
		"$LOGDIR/audio-reload.status" "$LOGDIR/service.status"
	touch "$MODPATH/.late-load-reload-experimental"
	write_late_context

	[ -f "$MODPATH/.AIDL" ] || late_block aidl_marker_missing
	[ -f "$MOD_VENDOR/lib64/soundfx/libjamesdsp.so" ] || \
		late_block jamesdsp_lib_missing
	if [ "$JDSP_PROFILE" = samsung_h8q ]; then
		wrapper="$MODPATH/tools/libjamesdsp_pinwrap.so"
		installed="$MOD_VENDOR/lib64/soundfx/libjamesdsp.so"
		real="$MOD_VENDOR/lib64/soundfx/libjamesdsp_real.so"
		[ -f "$wrapper" ] || late_block samsung_h8q_wrapper_missing
		if [ ! -f "$real" ]; then
			real_tmp="$real.tmp.$$"
			cp -f "$installed" "$real_tmp" || \
				late_block samsung_h8q_real_lib_copy_failed
			mv -f "$real_tmp" "$real" || \
				late_block samsung_h8q_real_lib_copy_failed
		fi
		wrapper_tmp="$installed.tmp.$$"
		cp -f "$wrapper" "$wrapper_tmp" || \
			late_block samsung_h8q_wrapper_copy_failed
		mv -f "$wrapper_tmp" "$installed" || \
			late_block samsung_h8q_wrapper_copy_failed
		printf 'samsung_h8q_aidl_wrapper=%s\nsamsung_h8q_aidl_real=%s\n' \
			"$installed" "$real" \
			>>"$LOGDIR/late-load-context.txt"
	fi
	mkdir -p "$MOD_VENDOR/etc"
	if [ "$JDSP_PROFILE" = mustang ]; then
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
		patch_jdsp_vendor_xml "$MOD_VENDOR/etc/audio_effects_config.xml" mustang
		grep -q 'path="libaudiopreprocessing.so"' \
			"$MOD_VENDOR/etc/audio_effects_config.xml" && \
			late_block system_legacy_preprocessing_not_removed
	else
		prepare_portable_native_configs
		reject_unvalidated_portable_payloads
	fi

	AIDL=true
	JDSP_COMPAT_PROFILE="$JDSP_PROFILE"
	export JDSP_COMPAT_PROFILE
	if [ -f "$MODPATH/patch.sh" ]; then
		# Mustang keeps the validated Android 17 SONAME adaptation. Portable
		# devices default to exact linker validation unless explicitly opted in.
		. "$MODPATH/patch.sh" >"$LOGDIR/late-load-patch.log" 2>&1 || \
			late_block patchelf_failed
	fi

	if ! "$LINKER_BIN" --list \
		"$MOD_VENDOR/lib64/soundfx/libjamesdsp.so" \
		>"$LOGDIR/late-load-linker.txt" 2>&1; then
		late_block linker_dependency_resolution_failed
	fi
	if [ "$JDSP_PROFILE" = samsung_h8q ]; then
		if ! "$LINKER_BIN" --list \
			"$MOD_VENDOR/lib64/soundfx/libjamesdsp_real.so" \
			>"$LOGDIR/late-load-linker-real.txt" 2>&1; then
			late_block linker_real_dependency_resolution_failed
		fi
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
