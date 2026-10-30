#!/system/bin/sh
# Experimental h8q recovery. Only an explicit, opted-in Retry may request the
# firmware's stop/start sequence. Never call ctl.restart or parse a vendor dump
# as an effect descriptor API. LOADED is not native-control/audio readiness.
MODE=${1:-}
case "$MODE" in --check|--retry-once) ;; *) echo 'Usage: samsung-audio-recovery.sh --check|--retry-once' >&2; exit 2 ;; esac
MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR" || exit 1
STATUS="$LOGDIR/samsung-audio-recovery.status"
GUARD="$LOGDIR/audio-hal-reload-samsung.boot-id"
PROC_ROOT=${LDSP_PROC_ROOT:-/proc}
INIT_ROOT=${LDSP_INIT_ROOT:-/proc/1/root}
BOOT_ID_FILE=${LDSP_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}
ID_BIN=${LDSP_ID_BIN:-/system/bin/id}
FLOCK_BIN=${LDSP_FLOCK_BIN:-/system/bin/flock}
GETPROP_BIN=${LDSP_GETPROP_BIN:-/system/bin/getprop}
SETPROP_BIN=${LDSP_SETPROP_BIN:-/system/bin/setprop}
PIDOF_BIN=${LDSP_PIDOF_BIN:-/system/bin/pidof}
DUMPSYS_BIN=${LDSP_DUMPSYS_BIN:-/system/bin/dumpsys}
LINKER_BIN=${LDSP_LINKER_BIN:-/system/bin/linker64}
SLEEP_BIN=${LDSP_SLEEP_BIN:-/system/bin/sleep}
LOGCAT_BIN=${LDSP_LOGCAT_BIN:-/system/bin/logcat}
FACTORY=android.hardware.audio.effect.IFactory/default
UUID=f27317f4-c984-4de6-9a90-545759495bf2

finish() {
    printf '%s\n' "$1" >"$STATUS"
    echo "$1"
    exit "${2:-1}"
}

unique_pid() {
    ids=$("$PIDOF_BIN" "$1" 2>/dev/null) || return 1
    set -- $ids
    [ "$#" -eq 1 ] || return 1
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$1"
}

factory_pid() {
    pid=$("$DUMPSYS_BIN" -t 2 --pid "$FACTORY" 2>/dev/null) || return 1
    case "$pid" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$pid"
}

overlay_ok() {
    root="$PROC_ROOT/$1/root"
    cmp -s "$MODPATH/system/vendor/lib64/soundfx/lightningdsplib.so" \
        "$root/vendor/lib64/soundfx/lightningdsplib.so" && \
        grep -qi "$UUID" "$root/vendor/etc/audio_effects_config.xml" 2>/dev/null
}

library_mapped() {
    overlay_ok "$1" || return 1
    # Do not count another module's same-named library or a deleted mapping.
    paths=$(awk '$NF ~ /\/liblightningdsp[.]so$/ { print $NF }' "$PROC_ROOT/$1/maps" 2>/dev/null)
    for mapped in $paths; do
        case "$mapped" in
            /vendor/lib64/soundfx/lightningdsplib.so|/system/vendor/lib64/soundfx/lightningdsplib.so|"$MODPATH/system/vendor/lib64/soundfx/lightningdsplib.so")
                cmp -s "$MODPATH/system/vendor/lib64/soundfx/lightningdsplib.so" \
                    "$PROC_ROOT/$1/root$mapped" && return 0
                ;;
        esac
    done
    return 1
}

running() {
    [ "$("$GETPROP_BIN" "init.svc.$1" 2>/dev/null)" = running ]
}

snapshot() {
    {
        printf 'boot_id=%s\n' "$boot_id"
        for name in vendor.audio-hal-aidl vendor.secaudiohal-aidl audioserver \
            vendor.audio-hal vendor.audio-effect-hal-aidl vendor.audio-hal-4-0-msd \
            audio_proxy_service audio_parameter_parser_service; do
            printf '%s=%s\n' "$name" "$("$GETPROP_BIN" "init.svc.$name" 2>/dev/null)"
        done
        printf 'factory_pid=%s\n' "$(factory_pid)"
        printf 'qti_pid=%s sec_pid=%s audioserver_pid=%s\n' \
            "$(unique_pid audiohalservice.qti)" "$(unique_pid secaudiohalaidl)" "$(unique_pid audioserver)"
        for pid in "$before_qti" "${after_qti:-}"; do
            [ -n "$pid" ] || continue
            printf 'maps_pid=%s\n' "$pid"
            grep -F 'lightningdsplib.so' "$PROC_ROOT/$pid/maps" 2>/dev/null
        done
    } >"$LOGDIR/samsung-audio-recovery-$1.txt"
}

native_diagnostics() {
    # Probe/status are evidence, not success criteria for the LOADED state.
    helper=${LDSP_CONTROL_HELPER:-/vendor/bin/ldspctl}
    if [ -x "$helper" ] && cmp -s "$helper" "$MODPATH/common/files/control/arm64-v8a/ldspctl"; then
        "${LDSP_TIMEOUT_BIN:-/system/bin/timeout}" 3 "$helper" probe \
            >"$LOGDIR/samsung-audio-recovery-probe.txt" 2>&1
        "${LDSP_TIMEOUT_BIN:-/system/bin/timeout}" 3 "$helper" status \
            >"$LOGDIR/samsung-audio-recovery-native-status.txt" 2>&1
    fi
}

[ "$("$ID_BIN" -u 2>/dev/null)" = 0 ] || finish 'BLOCKED reason=root_required'
[ "$("$GETPROP_BIN" ro.product.device 2>/dev/null)" = h8q ] || finish 'BLOCKED reason=unsupported_device'
[ -f "$MODPATH/.AIDL" ] && [ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/skip_mount" ] || \
    finish 'BLOCKED reason=module_not_mounted'
[ ! -f "$MODPATH/.samsung-firmware-recovery-disabled" ] || finish 'BLOCKED reason=samsung_recovery_disabled'
[ -x "$FLOCK_BIN" ] || finish 'BLOCKED reason=lock_unavailable'
# Share the lock with Pixel/legacy recovery; do not wait behind another reload.
exec 0>"$LOGDIR/manual-audio-reload.lock" || finish 'BLOCKED reason=lock_open_failed'
"$FLOCK_BIN" -n 0 || finish 'BLOCKED reason=recovery_in_progress'
boot_id=$(cat "$BOOT_ID_FILE" 2>/dev/null)
[ -n "$boot_id" ] || finish 'BLOCKED reason=boot_id_unavailable'
grep -q "^READY late_load=1 boot_id=$boot_id " "$LOGDIR/late-load.status" 2>/dev/null || \
    finish 'BLOCKED reason=late_load_not_prepared_this_boot'
grep -q 'policy=typed_rules_refreshed' "$LOGDIR/native-control.status" 2>/dev/null || \
    finish 'BLOCKED reason=typed_policy_not_refreshed'
running vendor.audio-hal-aidl && running vendor.secaudiohal-aidl && running audioserver || \
    finish 'BLOCKED reason=audio_services_not_running'
before_qti=$(unique_pid audiohalservice.qti) || finish 'BLOCKED reason=hal_process_not_unique'
before_sec=$(unique_pid secaudiohalaidl) || finish 'BLOCKED reason=secondary_hal_process_not_unique'
[ "$(readlink "$PROC_ROOT/$before_qti/exe")" = /vendor/bin/hw/audiohalservice.qti ] && \
    [ "$(readlink "$PROC_ROOT/$before_sec/exe")" = /vendor/bin/hw/secaudiohalaidl ] || \
    finish 'BLOCKED reason=hal_executable_mismatch'
[ "$(factory_pid)" = "$before_qti" ] || finish 'BLOCKED reason=factory_owner_mismatch'
overlay_ok "$before_qti" && overlay_ok "$before_sec" || finish 'BLOCKED reason=overlay_not_visible_to_hals'
"$LINKER_BIN" --list "$PROC_ROOT/$before_qti/root/vendor/lib64/soundfx/lightningdsplib.so" \
    >"$LOGDIR/samsung-audio-recovery-linker.txt" 2>&1 || finish 'BLOCKED reason=linker_dependency_resolution_failed'
# This is only a shell-linker preflight, not proof of the HAL linker namespace.

for pair in 'audiohalservice_qti.rc vendor.audio-hal-aidl audiohalservice.qti' \
            'secaudiohalaidl.rc vendor.secaudiohal-aidl secaudiohalaidl'; do
    set -- $pair
    awk -v svc="$2" -v exe="/vendor/bin/hw/$3" '
        $1 == "service" && $2 == svc { count++; if ($3 != exe) bad=1 }
        END { exit !(count == 1 && !bad) }
    ' "$INIT_ROOT/vendor/etc/init/$1" || finish 'BLOCKED reason=init_service_identity_not_verified'
done
trigger=$(awk '
    { sub(/#.*/, ""); sub(/[ \t\r]+$/, "") }
    $1 == "on" && $2 == "property:sys.audio.restart.hal=1" && NF == 2 { found++; active=1; next }
    active && /^[^ \t]/ { active=0 }
    active && NF { $1=$1; print }
    END { if (found != 1) exit 1 }
' "$INIT_ROOT/system/etc/init/audioserver.rc") || finish 'BLOCKED reason=firmware_trigger_not_verified'
expected='stop vendor.secaudiohal-aidl
stop vendor.audio-hal
stop vendor.audio-hal-aidl
stop vendor.audio-effect-hal-aidl
stop vendor.audio-hal-4-0-msd
stop audio_proxy_service
stop audio_parameter_parser_service
start vendor.secaudiohal-aidl
start vendor.audio-hal
start vendor.audio-hal-aidl
start vendor.audio-effect-hal-aidl
start vendor.audio-hal-4-0-msd
start audio_proxy_service
start audio_parameter_parser_service
setprop sys.audio.restart.hal 0'
[ "$trigger" = "$expected" ] || finish 'BLOCKED reason=firmware_trigger_not_verified'
case "$("$GETPROP_BIN" sys.audio.restart.hal 2>/dev/null)" in
    ''|0) ;; *) finish 'BLOCKED reason=firmware_reload_already_in_progress' ;;
esac
snapshot before
if [ "$MODE" = --check ]; then
    mapped=absent
    library_mapped "$before_qti" && mapped=mapped
    finish "PREFLIGHT reason=firmware_sequence_verified library=$mapped restart=not_requested registration=unverified processing=unverified" 0
fi
if library_mapped "$before_qti"; then
    native_diagnostics
    finish 'LOADED reason=library_already_mapped restart=not_needed registration=unverified processing=unverified' 0
fi
[ -f "$MODPATH/.samsung-firmware-recovery-opt-in" ] || finish 'BLOCKED reason=samsung_firmware_recovery_opt_in_required'
for guard in "$GUARD" "$LOGDIR/audio-hal-reload-retry.boot-id" \
    "$LOGDIR/audio-hal-reload-auto.boot-id" "$LOGDIR/manual-audio-reload.boot-id"; do
    if [ -f "$guard" ] && [ "$(cat "$guard")" = "$boot_id" ]; then
        finish 'BLOCKED reason=samsung_reload_already_attempted_this_boot'
    fi
done
# Preflight Binder/filesystem work takes time. Do not act on a stale PID or
# race another firmware reload, a module disable, or an opt-in revocation.
[ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/skip_mount" ] && \
    [ ! -f "$MODPATH/.samsung-firmware-recovery-disabled" ] && \
    [ -f "$MODPATH/.samsung-firmware-recovery-opt-in" ] || \
    finish 'BLOCKED reason=recovery_disabled_during_preflight'
[ "$(unique_pid audiohalservice.qti)" = "$before_qti" ] && \
    [ "$(unique_pid secaudiohalaidl)" = "$before_sec" ] && \
    [ "$(factory_pid)" = "$before_qti" ] && \
    running vendor.audio-hal-aidl && running vendor.secaudiohal-aidl && running audioserver || \
    finish 'BLOCKED reason=audio_state_changed_during_preflight'
case "$("$GETPROP_BIN" sys.audio.restart.hal 2>/dev/null)" in
    ''|0) ;; *) finish 'BLOCKED reason=firmware_reload_already_in_progress' ;;
esac
# Persist BEFORE requesting the sequence. Failed requests also consume it.
printf '%s\n' "$boot_id" >"$GUARD" || finish 'BLOCKED reason=guard_write_failed'
"$SETPROP_BIN" sys.audio.restart.hal 1 || finish 'BLOCKED reason=firmware_reload_request_failed'

count=0
after_qti=''
after_sec=''
reloaded=false
while [ "$count" -lt 20 ]; do
    reloaded=false
    after_qti=$(unique_pid audiohalservice.qti)
    after_sec=$(unique_pid secaudiohalaidl)
    if [ -n "$after_qti" ] && [ -n "$after_sec" ] && \
        [ "$after_qti" != "$before_qti" ] && [ "$after_sec" != "$before_sec" ] && \
        running vendor.audio-hal-aidl && running vendor.secaudiohal-aidl && running audioserver && \
        [ "$("$GETPROP_BIN" sys.audio.restart.hal 2>/dev/null)" = 0 ] && \
        [ "$(factory_pid)" = "$after_qti" ] && \
        [ "$(readlink "$PROC_ROOT/$after_qti/exe")" = /vendor/bin/hw/audiohalservice.qti ] && \
        [ "$(readlink "$PROC_ROOT/$after_sec/exe")" = /vendor/bin/hw/secaudiohalaidl ]; then
        reloaded=true
        library_mapped "$after_qti" && break
    fi
    count=$((count + 1))
    "$SLEEP_BIN" 1
done
snapshot after
native_diagnostics
if [ "$count" -ge 20 ]; then
    "$LOGCAT_BIN" -d -t 400 2>/dev/null | grep -iE 'lightningdsp|ldsp.control|EffectFactory|dlopen|CANNOT LINK' \
        >"$LOGDIR/samsung-audio-recovery-loader.txt"
    [ "$reloaded" = true ] || finish 'BLOCKED reason=firmware_reload_not_observed registration=unverified processing=unverified'
    finish 'BLOCKED reason=library_not_mapped_after_reload registration=unverified processing=unverified'
fi
count=0
while [ "$count" -lt 2 ]; do
    "$SLEEP_BIN" 1
    [ "$(unique_pid audiohalservice.qti)" = "$after_qti" ] && \
        [ "$(unique_pid secaudiohalaidl)" = "$after_sec" ] && \
        [ "$(factory_pid)" = "$after_qti" ] && \
        running vendor.audio-hal-aidl && running vendor.secaudiohal-aidl && \
        running audioserver && [ "$("$GETPROP_BIN" sys.audio.restart.hal 2>/dev/null)" = 0 ] && \
        library_mapped "$after_qti" || \
        finish 'BLOCKED reason=audio_services_unstable_after_reload'
    count=$((count + 1))
done
finish "LOADED reason=library_mapped restart=firmware_once before_hal=$before_qti after_hal=$after_qti registration=unverified processing=unverified" 0
