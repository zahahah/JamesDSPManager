#!/system/bin/sh
# Manual, single-attempt recovery for a late-mounted AIDL effect. Never call
# this from a boot hook: restarting an audio HAL can interrupt or destabilize
# audio, especially on temp-root devices.

[ "${1:-}" = --manual-once ] || {
    echo 'Usage: manual-audio-reload.sh --manual-once (requires explicit HAL service and process)' >&2
    exit 2
}

MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR" || exit 1
STATUS="$LOGDIR/manual-audio-reload.status"
GUARD="$LOGDIR/manual-audio-reload.boot-id"
FLOCK_BIN=${JDSP_FLOCK_BIN:-/system/bin/flock}
ID_BIN=${JDSP_ID_BIN:-/system/bin/id}
PIDOF_BIN=${JDSP_PIDOF_BIN:-/system/bin/pidof}
GETPROP_BIN=${JDSP_GETPROP_BIN:-/system/bin/getprop}
SETPROP_BIN=${JDSP_SETPROP_BIN:-/system/bin/setprop}
SERVICE_BIN=${JDSP_SERVICE_BIN:-/system/bin/service}
DUMPSYS_BIN=${JDSP_DUMPSYS_BIN:-/system/bin/dumpsys}
LINKER_BIN=${JDSP_LINKER_BIN:-/system/bin/linker64}
SLEEP_BIN=${JDSP_SLEEP_BIN:-/system/bin/sleep}
PROC_ROOT=${JDSP_PROC_ROOT:-/proc}
BOOT_ID_FILE=${JDSP_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}
FACTORY=android.hardware.audio.effect.IFactory/default
JDSP_UUID=f27317f4-c984-4de6-9a90-545759495bf2
HAL_SERVICE=${JDSP_AUDIO_HAL_INIT_SERVICE:-}
HAL_PROCESS=${JDSP_AUDIO_HAL_PROCESS:-}

finish() {
    printf '%s\n' "$1" >"$STATUS"
    echo "$1"
    exit "${2:-1}"
}

hal_pid() {
    ids=$("$PIDOF_BIN" "$HAL_PROCESS" 2>/dev/null) || return 1
    set -- $ids
    [ "$#" -eq 1 ] || return 1
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$1"
}

case "$HAL_SERVICE:$HAL_PROCESS" in
    :*|*:|*[!a-zA-Z0-9_.:-]*) finish 'BLOCKED reason=explicit_hal_identity_required' ;;
esac
[ "$("$ID_BIN" -u 2>/dev/null)" = 0 ] || finish 'BLOCKED reason=root_required'
[ -f "$MODPATH/.AIDL" ] || finish 'BLOCKED reason=aidl_marker_missing'
[ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/skip_mount" ] || \
    finish 'BLOCKED reason=module_not_mounted'
grep -q '^READY late_load=1 ' "$LOGDIR/late-load.status" 2>/dev/null || \
    finish 'BLOCKED reason=late_load_not_prepared'
grep -q 'policy=typed_rules_refreshed' "$LOGDIR/native-control.status" 2>/dev/null || \
    finish 'BLOCKED reason=typed_policy_not_refreshed'
[ -x "$FLOCK_BIN" ] || finish 'BLOCKED reason=lock_unavailable'
exec 9>"$LOGDIR/manual-audio-reload.lock" || finish 'BLOCKED reason=lock_open_failed'
"$FLOCK_BIN" -x 9 || finish 'BLOCKED reason=lock_failed'

boot_id=$(cat "$BOOT_ID_FILE" 2>/dev/null)
[ -n "$boot_id" ] || finish 'BLOCKED reason=boot_id_unavailable'
if [ -f "$GUARD" ] && [ "$(cat "$GUARD")" = "$boot_id" ]; then
    finish 'BLOCKED reason=reload_already_attempted_this_boot'
fi
[ "$("$GETPROP_BIN" "init.svc.$HAL_SERVICE" 2>/dev/null)" = running ] || \
    finish 'BLOCKED reason=selected_init_service_not_running'
before_pid=$(hal_pid) || finish 'BLOCKED reason=hal_process_not_unique'
[ -d "$PROC_ROOT/$before_pid" ] || finish 'BLOCKED reason=hal_process_missing'

hal_root="$PROC_ROOT/$before_pid/root"
effect_lib="$hal_root/vendor/lib64/soundfx/libjamesdsp.so"
effect_xml="$hal_root/vendor/etc/audio_effects_config.xml"
[ -f "$effect_lib" ] && [ -f "$effect_xml" ] || \
    finish 'BLOCKED reason=overlay_not_visible_to_hal'
cmp -s "$MODPATH/system/vendor/lib64/soundfx/libjamesdsp.so" "$effect_lib" || \
    finish 'BLOCKED reason=hal_sees_different_library'
grep -qi "$JDSP_UUID" "$effect_xml" || \
    finish 'BLOCKED reason=hal_config_missing_jamesdsp'
"$LINKER_BIN" --list "$effect_lib" >"$LOGDIR/manual-audio-reload-linker.txt" 2>&1 || \
    finish 'BLOCKED reason=linker_dependency_resolution_failed'
"$SERVICE_BIN" check "$FACTORY" 2>/dev/null | grep -q ': found' || \
    finish 'BLOCKED reason=default_factory_missing'
before_dump=$("$DUMPSYS_BIN" "$FACTORY" 2>/dev/null) || \
    finish 'BLOCKED reason=factory_dump_failed'
printf '%s\n' "$before_dump" >"$LOGDIR/manual-audio-reload-before.txt"
printf '%s\n' "$before_dump" | grep -q '^Effects ([0-9][0-9]*):' || \
    finish 'BLOCKED reason=factory_descriptor_list_unavailable'
if printf '%s\n' "$before_dump" | grep -qi "$JDSP_UUID"; then
    finish 'READY reason=effect_already_discovered restart=not_needed' 0
fi

# The guard is durable before ctl.restart so a failed or unstable restart never
# enters a retry loop during this boot. Do not restart audioserver here.
printf '%s\n' "$boot_id" >"$GUARD" || finish 'BLOCKED reason=guard_write_failed'
"$SETPROP_BIN" ctl.restart "$HAL_SERVICE" || \
    finish 'BLOCKED reason=init_restart_request_failed'

count=0
new_pid=''
while [ "$count" -lt 20 ]; do
    candidate=$(hal_pid)
    if [ -n "$candidate" ] && [ "$candidate" != "$before_pid" ] && \
        [ -d "$PROC_ROOT/$candidate" ] && \
        [ "$("$GETPROP_BIN" "init.svc.$HAL_SERVICE" 2>/dev/null)" = running ]; then
        new_pid=$candidate
        break
    fi
    count=$((count + 1))
    "$SLEEP_BIN" 1
done
[ -n "$new_pid" ] || finish 'BLOCKED reason=hal_restart_not_observed'

count=0
while [ "$count" -lt 10 ]; do
    after_dump=$("$DUMPSYS_BIN" "$FACTORY" 2>/dev/null) || after_dump=''
    if printf '%s\n' "$after_dump" | grep -qi "$JDSP_UUID"; then
        printf '%s\n' "$after_dump" >"$LOGDIR/manual-audio-reload-after.txt"
        "$SLEEP_BIN" 2
        [ "$(hal_pid)" = "$new_pid" ] || \
            finish 'BLOCKED reason=hal_unstable_after_restart'
        finish "DISCOVERED reason=effect_registered restart=once before_hal=$before_pid after_hal=$new_pid processing=unverified" 0
    fi
    count=$((count + 1))
    "$SLEEP_BIN" 1
done
finish 'BLOCKED reason=effect_not_discovered_after_restart'
