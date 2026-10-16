#!/system/bin/sh
# Direct-driver Samsung runtime. No automatic audio/OS restart or ABI patching.
umask 077
MODDIR=${0%/*}
LOGDIR="$MODDIR/logs"
WORK="$MODDIR/work/samsung"
STATUS="$LOGDIR/samsung-runtime.status"
FS=${JDSP_SAMSUNG_FS_ROOT:-}
GETPROP=${JDSP_SAMSUNG_GETPROP:-/system/bin/getprop}
NSENTER=${JDSP_SAMSUNG_NSENTER:-}
SHELL_BIN=${JDSP_SAMSUNG_SH:-/system/bin/sh}
READLINK=${JDSP_SAMSUNG_READLINK:-/system/bin/readlink}
LINKER=${JDSP_SAMSUNG_LINKER:-/system/bin/linker64}
PIDOF=${JDSP_SAMSUNG_PIDOF:-/system/bin/pidof}
SERVICE=${JDSP_SAMSUNG_SERVICE:-/system/bin/service}
MOUNT=${JDSP_SAMSUNG_MOUNT:-/system/bin/mount}
UMOUNT=${JDSP_SAMSUNG_UMOUNT:-/system/bin/umount}
CHCON=${JDSP_SAMSUNG_CHCON:-/system/bin/chcon}
MOUNTINFO=${JDSP_SAMSUNG_MOUNTINFO:-/proc/self/mountinfo}
BOOT_ID=${JDSP_SAMSUNG_BOOT_ID:-/proc/sys/kernel/random/boot_id}
DRIVER="$MODDIR/driver/libjamesdsp.so"
UUID=f27317f4-c984-4de6-9a90-545759495bf2
TYPE=f98765f4-c321-5de6-9a45-123459495ab2
JOURNAL=''
ROLLBACK_FAILED=0

mkdir -p "$LOGDIR" || exit 1

write_status() {
    printf '%s restart=not_requested processing=unverified\n' "$1" >"$STATUS.tmp.$$"
    mv -f "$STATUS.tmp.$$" "$STATUS"
}

mount_id() {
    awk -v target="$1" '$5 == target { id=$1 } END { if (id != "") print id }' "$MOUNTINFO"
}

rollback() {
    [ -n "$JOURNAL" ] && [ -s "$JOURNAL" ] || return 0
    awk '{ row[NR]=$0 } END { for (i=NR; i>0; i--) print row[i] }' "$JOURNAL" >"$JOURNAL.reverse"
    while IFS='|' read -r id target source; do
        # Do not unmount a target whose top mount is no longer ours.
        if [ "$(mount_id "$target")" != "$id" ]; then
            ROLLBACK_FAILED=1
        elif ! "$UMOUNT" "$target" >>"$LOGDIR/samsung-mount.log" 2>&1; then
            ROLLBACK_FAILED=1
        fi
    done <"$JOURNAL.reverse"
}

block() {
    rollback
    suffix=''
    [ "$ROLLBACK_FAILED" = 0 ] || suffix=' rollback_failed=1'
    write_status "BLOCKED reason=$1$suffix"
    exit 0
}

check_request() {
    [ "${JDSP_SAMSUNG_ENTRYPOINT:-}" = service-late-load ] &&
        [ "${KSU_LATE_LOAD:-0}" = 1 ] && [ "${KSU_RUNTIME_MODE:-}" = late-load ] || block explicit_late_load_required
    [ "$("$GETPROP" sys.boot_completed 2>/dev/null)" = 1 ] || {
        write_status 'DEFERRED reason=android_not_ready'
        exit 0
    }
    manufacturer=$("$GETPROP" ro.product.manufacturer 2>/dev/null | tr '[:upper:]' '[:lower:]')
    [ "$manufacturer" = samsung ] || block unsupported_device
    case "$("$GETPROP" ro.product.cpu.abilist64 2>/dev/null)" in
        *arm64-v8a*) ;;
        *) block arm64_required ;;
    esac
    # Journals use | delimiters and mountinfo uses escaped whitespace.
    case "$MODDIR$FS" in *[[:space:]\|]*) block unsupported_path ;; esac
}

enter_init_namespace() {
    if [ -n "$NSENTER" ]; then
        "$NSENTER" -t 1 -m -- "$SHELL_BIN" "$0" namespace-activate
    elif command -v nsenter >/dev/null 2>&1; then
        nsenter -t 1 -m -- "$SHELL_BIN" "$0" namespace-activate
    elif [ -x /data/adb/ksu/bin/busybox ]; then
        /data/adb/ksu/bin/busybox nsenter -t 1 -m -- "$SHELL_BIN" "$0" namespace-activate
    else
        return 1
    fi
}

case "${1:-}" in
    activate)
        check_request
        # No shell-namespace fallback: it could report success invisible to HAL.
        enter_init_namespace || block init_namespace_unavailable
        exit 0
        ;;
    namespace-activate) check_request ;;
    *) block unsupported_action ;;
esac

init_ns=$("$READLINK" /proc/1/ns/mnt 2>/dev/null)
self_ns=$("$READLINK" /proc/self/ns/mnt 2>/dev/null)
[ -n "$init_ns" ] && [ "$init_ns" = "$self_ns" ] || block namespace_mismatch
factory_pid=$("$PIDOF" audiohalservice.qti 2>/dev/null | awk '{print $1}')
case "$factory_pid" in ''|*[!0-9]*) block qti_factory_process_missing ;; esac
factory_ns=$("$READLINK" "/proc/$factory_pid/ns/mnt" 2>/dev/null)
[ "$factory_ns" = "$init_ns" ] || block factory_namespace_mismatch
"$SERVICE" check android.hardware.audio.effect.IFactory/default 2>/dev/null | grep -q ': found' || block default_aidl_factory_missing

factory_unchanged() {
    [ "$("$GETPROP" sys.boot_completed 2>/dev/null)" = 1 ] &&
        [ "$("$PIDOF" audiohalservice.qti 2>/dev/null | awk '{print $1}')" = "$factory_pid" ] &&
        [ "$("$READLINK" "/proc/$factory_pid/ns/mnt" 2>/dev/null)" = "$init_ns" ]
}
boot_id=$(cat "$BOOT_ID" 2>/dev/null)
[ -n "$boot_id" ] || block boot_identity_unavailable
mkdir -p "$WORK" || block work_directory_failed
exec 9>"$WORK/activate.lock" || block lock_open_failed
if [ -n "${JDSP_SAMSUNG_FLOCK:-}" ]; then
    "$JDSP_SAMSUNG_FLOCK" -n 9 || block activation_locked
elif [ -x /system/bin/flock ]; then
    /system/bin/flock -n 9 || block activation_locked
elif [ -x /data/adb/ksu/bin/busybox ]; then
    /data/adb/ksu/bin/busybox flock -n 9 || block activation_locked
else
    block lock_tool_unavailable
fi

[ -f "$DRIVER" ] && [ -f "$MODDIR/driver.sha256" ] || block driver_missing
expected=$(cat "$MODDIR/driver.sha256")
case "$expected" in *[!0-9a-f]*) block invalid_driver_digest ;; esac
[ "${#expected}" = 64 ] || block invalid_driver_digest
actual=$(sha256sum "$DRIVER" 2>/dev/null | awk '{print $1}')
[ "$actual" = "$expected" ] || block driver_digest_mismatch

# Reuse only mounts from this boot whose IDs and visible contents still match.
if [ -f "$WORK/active.mounts" ] && [ -f "$WORK/active.boot-id" ] &&
    [ "$(cat "$WORK/active.boot-id")" = "$boot_id" ]; then
    total=0
    owned=0
    valid=0
    while IFS='|' read -r id target source; do
        total=$((total + 1))
        [ "$(mount_id "$target")" = "$id" ] || continue
        owned=$((owned + 1))
        if [ -d "$source" ]; then
            cmp -s "$DRIVER" "$target/libjamesdsp.so" && valid=$((valid + 1))
        else
            cmp -s "$source" "$target" && valid=$((valid + 1))
        fi
    done <"$WORK/active.mounts"
    if [ "$total" -gt 0 ] && [ "$valid" = "$total" ]; then
        write_status 'MOUNTED_UNVERIFIED reason=already_mounted'
        exit 0
    fi
    [ "$owned" = 0 ] || block partial_or_changed_existing_mounts
fi

library_dir="$FS/vendor/lib64/soundfx"
[ -d "$library_dir" ] || block vendor_soundfx_missing
[ ! -L "$library_dir" ] || block symlink_mount_target_unsupported
[ ! -e "$library_dir/libjamesdsp.so" ] && [ ! -L "$library_dir/libjamesdsp.so" ] || block existing_jdsp_payload
[ -z "$(mount_id "$library_dir")" ] || block existing_soundfx_overlay
"$LINKER" --list "$DRIVER" >"$LOGDIR/samsung-driver-linker.txt" 2>&1 || block driver_dependency_resolution_failed

session=$(mktemp -d "$WORK/session.XXXXXX") || block staging_directory_failed
JOURNAL="$session/mounted.list"
: >"$JOURNAL"
trap 'block interrupted' HUP INT TERM
cp -a "$library_dir" "$session/soundfx" || block stock_library_copy_failed
cp -p "$DRIVER" "$session/soundfx/libjamesdsp.so" || block driver_copy_failed
# Preserve stock labels individually, including subdirectories and hidden files.
find "$library_dir" -print >"$session/stock-paths" || block stock_library_list_failed
while IFS= read -r original; do
    relative=${original#"$library_dir"}
    copied="$session/soundfx$relative"
    [ -L "$original" ] && continue
    "$CHCON" --reference="$original" "$copied" >>"$LOGDIR/samsung-label.log" 2>&1 || block label_failed
done <"$session/stock-paths"
"$CHCON" --reference="$library_dir" "$session/soundfx/libjamesdsp.so" >>"$LOGDIR/samsung-label.log" 2>&1 || block label_failed
printf '%s|%s\n' "$session/soundfx" "$library_dir" >"$session/planned.list"

sku=$("$GETPROP" ro.boot.product.vendor.sku 2>/dev/null)
case "$sku" in *[!a-zA-Z0-9_-]*) block invalid_sku ;; esac
count=0
for config in "$FS/vendor/etc"/audio_effects_config*.xml "$FS/vendor/etc/audio/sku_$sku"/audio_effects_config*.xml; do
    [ -f "$config" ] || continue
    [ ! -L "$config" ] || block symlink_mount_target_unsupported
    [ -z "$(mount_id "$config")" ] || block existing_config_overlay
    if grep -qiE 'libjamesdsp|name="jdsp"|name="jamesdsp"|f27317f4-c984-4de6-9a90-545759495bf2' "$config"; then
        block existing_jdsp_config
    fi
    count=$((count + 1))
    patched="$session/config.$count.xml"
    # Preserve the stock mode/owner before truncating the staged copy with awk.
    # Private work files use umask 077, but HAL-visible files must stay readable.
    cp -p "$config" "$patched" || block config_copy_failed
    # Deliberately bounded line-oriented format. Never translate legacy configs,
    # remove stock effects, generate a canonical config, or alter deviceEffects.
    awk -v uuid="$UUID" -v type="$TYPE" '
        /<!DOCTYPE|<!ENTITY/ { exit 2 }
        /<!--/ { comment=1 }
        comment { print; if (/-->/) comment=0; next }
        /^[[:space:]]*<audio_effects_conf([[:space:]>])/ {
            if (root || endroot) bad=1; root++
        }
        /^[[:space:]]*<\/audio_effects_conf>[[:space:]]*$/ {
            if (root!=1 || endroot || endlibs!=1 || endeffects!=1) bad=1; endroot++
        }
        { print }
        /^[[:space:]]*<libraries>[[:space:]]*$/ {
            if (root!=1 || endroot || libs || effects) bad=1
            libs++; print "        <library name=\"jdsp\" path=\"libjamesdsp.so\"/>"
        }
        /^[[:space:]]*<\/libraries>[[:space:]]*$/ {
            if (libs!=1 || endlibs || endroot || effects) bad=1; endlibs++
        }
        /^[[:space:]]*<effects>[[:space:]]*$/ {
            if (root!=1 || endroot || endlibs!=1 || effects) bad=1
            effects++; print "        <effect name=\"jamesdsp\" library=\"jdsp\" uuid=\"" uuid "\" type=\"" type "\"/>"
        }
        /^[[:space:]]*<\/effects>[[:space:]]*$/ {
            if (effects!=1 || endeffects || endroot) bad=1; endeffects++
        }
        END { if (bad || comment || root!=1 || endroot!=1 || libs!=1 || endlibs!=1 || effects!=1 || endeffects!=1) exit 2 }
    ' "$config" >"$patched" || block unsupported_native_config
    "$CHCON" --reference="$config" "$patched" >>"$LOGDIR/samsung-label.log" 2>&1 || block label_failed
    printf '%s|%s\n' "$patched" "$config" >>"$session/planned.list"
done
[ "$count" -gt 0 ] || block native_config_missing

# Every dependency, XML and label is checked before the first live mount.
while IFS='|' read -r source target; do
    factory_unchanged || block factory_changed_during_activation
    [ -z "$(mount_id "$target")" ] || block target_changed_before_mount
    "$MOUNT" -o bind "$source" "$target" >>"$LOGDIR/samsung-mount.log" 2>&1 || block mount_failed
    id=$(mount_id "$target")
    if [ -z "$id" ]; then
        ROLLBACK_FAILED=1
        block mount_identity_missing
    fi
    printf '%s|%s|%s\n' "$id" "$target" "$source" >>"$JOURNAL"
done <"$session/planned.list"
factory_unchanged || block factory_changed_during_activation
cmp -s "$DRIVER" "$library_dir/libjamesdsp.so" || block mounted_driver_mismatch
while IFS='|' read -r source target; do
    [ -f "$source" ] || continue
    cmp -s "$source" "$target" || block mounted_config_mismatch
done <"$session/planned.list"
cp -f "$JOURNAL" "$WORK/active.mounts.tmp.$$" || block journal_write_failed
mv -f "$WORK/active.mounts.tmp.$$" "$WORK/active.mounts" || block journal_write_failed
printf '%s\n' "$boot_id" >"$WORK/active.boot-id" || block journal_write_failed
trap - HUP INT TERM
write_status "MOUNTED_UNVERIFIED reason=direct_driver_mounted configs=$count namespace=$init_ns factory_pid=$factory_pid"
exit 0
