#!/system/bin/sh
# AIDL late-load bridge: stage first, then bind into init's mount namespace.
# No local-namespace fallback, service restarts, resetprop, or policy grants.
MODE=${1:-}
case "$MODE" in --check|--mount) ;; *) echo 'Usage: aidl-effect-mount.sh --check|--mount' >&2; exit 2 ;; esac
MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR" || exit 1
STATUS="$LOGDIR/aidl-effect-mount.status"
INIT_ROOT=${LDSP_INIT_ROOT:-/proc/1/root}
ID_BIN=${LDSP_ID_BIN:-/system/bin/id}
FLOCK_BIN=${LDSP_FLOCK_BIN:-/system/bin/flock}
NSENTER_BIN=${LDSP_NSENTER_BIN:-/system/bin/nsenter}
MOUNT_BIN=${LDSP_MOUNT_BIN:-/system/bin/mount}
CHCON_BIN=${LDSP_CHCON_BIN:-/system/bin/chcon}
LS_BIN=${LDSP_LS_BIN:-/system/bin/ls}
BOOT_ID_FILE=${LDSP_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}
UUID=f27317f4-c984-4de6-9a90-545759495bf2

finish() {
    printf '%s\n' "$1" | tee "$STATUS"
    exit "${2:-1}"
}

label_of() {
    "$LS_BIN" -Zd "$1" 2>/dev/null | awk '{
        for (i=1; i<=NF; i++) if ($i ~ /^u:object_r:/) { print $i; exit }
    }'
}

patch_config() {
    # Only replace our own standalone entries. Preserve vendor effects, routing,
    # comments and library paths; never translate vendor libraries to Pixel names.
    # Match a view without a terminal CR, but print the original record so
    # untouched vendor lines keep their CRLF/LF bytes. Mixed endings are valid
    # XML and occur when module-inserted LF entries join stock CRLF configs.
    awk -v uuid="$UUID" '
    { original_line=$0; sub(/\r$/, "") }
    /<!--/ { comment=1 }
    comment { print original_line; if (/-->/) comment=0; next }
    /name="(ldsp|lightningdsp)"/ || index($0, uuid) {
        if ($0 ~ /^[ \t]*<library[ \t]+name="ldsp"[ \t]+path="[^"]+"[ \t]*\/>[ \t]*$/ ||
            $0 ~ /^[ \t]*<effect[ \t]+name="lightningdsp"[ \t]+.*\/>[ \t]*$/) next
        bad=1; next
    }
    { print original_line }
    /^[ \t]*<audio_effects_conf[ \t>]/ { root++ }
    /^[ \t]*<\/audio_effects_conf>[ \t]*$/ { endroot++ }
    /^[ \t]*<libraries>[ \t]*$/ {
        libs++
        print "        <library name=\"ldsp\" path=\"lightningdsplib.so\"/>"
    }
    /^[ \t]*<\/libraries>[ \t]*$/ { endlibs++ }
    /^[ \t]*<effects>[ \t]*$/ {
        effects++
        print "        <effect name=\"lightningdsp\" library=\"ldsp\" uuid=\"" uuid "\" type=\"f98765f4-c321-5de6-9a45-123459495ab2\"/>"
    }
    /^[ \t]*<\/effects>[ \t]*$/ { endeffects++ }
    END { if (bad || comment || root != 1 || endroot != 1 || libs != 1 || endlibs != 1 || effects != 1 || endeffects != 1) exit 1 }
    ' "$1" >"$2"
}

[ "$("$ID_BIN" -u 2>/dev/null)" = 0 ] || finish 'BLOCKED reason=root_required'
[ -f "$MODPATH/.AIDL" ] && [ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/skip_mount" ] && \
    [ ! -f "$MODPATH/.samsung-firmware-recovery-disabled" ] && [ ! -f "$MODPATH/.aidl-recovery-disabled" ] || finish 'BLOCKED reason=module_disabled'
boot_id=$(cat "$BOOT_ID_FILE" 2>/dev/null)
case "$boot_id" in ''|*[!a-zA-Z0-9-]*) finish 'BLOCKED reason=boot_id_unavailable' ;; esac
grep -q "^READY late_load=1 boot_id=$boot_id " "$LOGDIR/late-load.status" 2>/dev/null || \
    finish 'BLOCKED reason=late_load_not_prepared_this_boot'
[ -x "$FLOCK_BIN" ] && [ -x "$NSENTER_BIN" ] && [ -x "$MOUNT_BIN" ] || \
    finish 'BLOCKED reason=namespace_tools_unavailable'
exec 0>"$LOGDIR/aidl-effect-mount.lock" || finish 'BLOCKED reason=lock_open_failed'
"$FLOCK_BIN" -n 0 || finish 'BLOCKED reason=mount_in_progress'
"$NSENTER_BIN" -t 1 -m -- /system/bin/true || finish 'BLOCKED reason=init_namespace_unavailable'

source_lib="$MODPATH/system/vendor/lib64/soundfx/lightningdsplib.so"
[ -s "$source_lib" ] || finish 'BLOCKED reason=source_library_missing'
[ -d "$INIT_ROOT/vendor/lib64/soundfx" ] || finish 'BLOCKED reason=vendor_soundfx_directory_missing'
# Do not replace all of /vendor/etc to invent a missing file. The manager must
# expose the prepared factory config first; directory overlays here hide mounts.
[ -f "$INIT_ROOT/vendor/etc/audio_effects_config.xml" ] || finish 'BLOCKED reason=factory_config_target_missing'
mkdir -p "$MODPATH/.aidl-mount" || finish 'BLOCKED reason=staging_directory_failed'
stage=$(mktemp -d "$MODPATH/.aidl-mount/$boot_id.XXXXXX") || finish 'BLOCKED reason=staging_directory_failed'
plan="$stage/plan"
: >"$plan"

target=/vendor/lib64/soundfx/lightningdsplib.so
if ! cmp -s "$source_lib" "$INIT_ROOT$target" || \
    [ "$(label_of "$INIT_ROOT$target")" != u:object_r:vendor_file:s0 ]; then
    cp -p "$source_lib" "$stage/lightningdsplib.so" || finish 'BLOCKED reason=library_stage_failed'
    chmod 0644 "$stage/lightningdsplib.so" || finish 'BLOCKED reason=library_stage_failed'
    "$CHCON_BIN" u:object_r:vendor_file:s0 "$stage/lightningdsplib.so" || finish 'BLOCKED reason=library_label_failed'
    if [ -e "$INIT_ROOT$target" ]; then
        printf '%s\t%s\t%s\n' "$stage/lightningdsplib.so" "$target" u:object_r:vendor_file:s0 >>"$plan"
    else
        # A bind mount cannot create a file on read-only vendor. Preserve every
        # existing soundfx entry and its labels, including other audio modules.
        mkdir "$stage/soundfx" && cp -a "$INIT_ROOT/vendor/lib64/soundfx/." "$stage/soundfx/" || \
            finish 'BLOCKED reason=library_directory_stage_failed'
        cp -p "$stage/lightningdsplib.so" "$stage/soundfx/lightningdsplib.so" || finish 'BLOCKED reason=library_stage_failed'
        "$CHCON_BIN" --reference="$INIT_ROOT/vendor/lib64/soundfx" "$stage/soundfx" && \
            "$CHCON_BIN" u:object_r:vendor_file:s0 "$stage/soundfx/lightningdsplib.so" || finish 'BLOCKED reason=library_label_failed'
        printf '%s\t%s\t%s\n' "$stage/soundfx" /vendor/lib64/soundfx u:object_r:vendor_file:s0 >>"$plan"
    fi
fi

# Patch the live init-visible configs, not stale module copies. Include the
# Qualcomm SKU locations that can differ from the canonical vendor XML.
: >"$stage/configs"
for dir in /vendor/etc /odm/etc /system/etc /product/etc /system_ext/etc; do
    [ ! -d "$INIT_ROOT$dir" ] || find "$INIT_ROOT$dir" -maxdepth 1 -type f -name 'audio_effects*.xml' >>"$stage/configs"
done
for dir in "$INIT_ROOT"/vendor/etc/audio/sku_*; do
    [ ! -d "$dir" ] || find "$dir" -maxdepth 1 -type f -name 'audio_effects*.xml' >>"$stage/configs"
done
sort -u "$stage/configs" >"$stage/configs.sorted"
index=0
while IFS= read -r original; do
    target=${original#"$INIT_ROOT"}
    index=$((index + 1))
    patched="$stage/config.$index.xml"
    patch_config "$original" "$patched" || finish "BLOCKED reason=config_structure_not_supported target=$target"
    config_label=$(label_of "$original")
    case "$config_label" in
        u:object_r:vendor_configs_file:s0|u:object_r:vendor_file:s0|u:object_r:system_file:s0|u:object_r:system_configs_file:s0|u:object_r:odm_configs_file:s0) ;;
        *) finish "BLOCKED reason=config_label_not_verified target=$target" ;;
    esac
    if ! cmp -s "$patched" "$original"; then
        chmod 0644 "$patched" || finish 'BLOCKED reason=config_stage_failed'
        "$CHCON_BIN" "$config_label" "$patched" || finish 'BLOCKED reason=config_label_failed'
        printf '%s\t%s\t%s\n' "$patched" "$target" "$config_label" >>"$plan"
    fi
done <"$stage/configs.sorted"

changes=$(wc -l <"$plan" | tr -d ' ')
cp "$plan" "$LOGDIR/aidl-effect-mount-plan.txt" || finish 'BLOCKED reason=plan_log_failed'
if [ "$MODE" = --check ]; then
    finish "PREFLIGHT namespace=init planned=$changes restart=not_requested registration=unverified" 0
fi
[ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/.samsung-firmware-recovery-disabled" ] && [ ! -f "$MODPATH/.aidl-recovery-disabled" ] || \
    finish 'BLOCKED reason=module_disabled_during_preflight'
if [ "$changes" -gt 0 ]; then
    # Keep a generation pending until a successful guarded HAL reload. Merely
    # seeing a mapped library does not mean the new XML has been consumed.
    printf '%s\n' "${stage##*/}" >"$LOGDIR/aidl-effect-mount.generation" || finish 'BLOCKED reason=generation_write_failed'
fi
mounted=0
tab=$(printf '\t')
while IFS="$tab" read -r source target expected_label; do
    "$NSENTER_BIN" -t 1 -m -- "$MOUNT_BIN" --bind "$source" "$target" || \
        finish "BLOCKED reason=init_bind_mount_failed mounted=$mounted target=$target restart=not_requested"
    cmp -s "$source" "$INIT_ROOT$target" || {
        [ -d "$source" ] && cmp -s "$source/lightningdsplib.so" "$INIT_ROOT$target/lightningdsplib.so"
    } || finish "BLOCKED reason=init_mount_verification_failed mounted=$mounted target=$target restart=not_requested"
    label_target="$INIT_ROOT$target"
    case "$target" in
        /vendor/lib64/soundfx) label_target="$label_target/lightningdsplib.so" ;;
    esac
    [ "$(label_of "$label_target")" = "$expected_label" ] || \
        finish "BLOCKED reason=init_mount_label_verification_failed target=$target restart=not_requested"
    mounted=$((mounted + 1))
done <"$plan"
finish "MOUNTED namespace=init changed=$mounted configs=$index restart=not_requested registration=unverified processing=unverified" 0
