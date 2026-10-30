#!/system/bin/sh
# Mount first, then use only a validated firmware stop/start handler. Never kill
# guessed process names or broaden SELinux policy to manufacture readiness.
MODE=${1:-}
case "$MODE" in --auto-once|--retry|--check) ;; *) echo 'Usage: aidl-audio-recovery.sh --auto-once|--retry|--check' >&2; exit 2 ;; esac
MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR" || exit 1
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
GUARD="$LOGDIR/audio-hal-reload-aidl.boot-id"
LIFECYCLE_GUARD="$LOGDIR/audio-hal-reload-aidl.lifecycle"

finish() {
    printf '%s\n' "$1" | tee "$LOGDIR/aidl-audio-recovery.status" >"$LOGDIR/audio-hal-recovery.status"
    cat "$LOGDIR/aidl-audio-recovery.status"
    exit "${2:-1}"
}
factory_pid() {
    result=$("$DUMPSYS_BIN" -t 2 --pid "$FACTORY" 2>/dev/null)
    case "$result" in
        ''|*[!0-9]*)
            sh "$MODPATH/effect-host.sh" --hidl-pid 2>/dev/null ;;
        *) printf '%s\n' "$result" ;;
    esac
}
unique_pid() {
    ids=$("$PIDOF_BIN" "${1##*/}" 2>/dev/null) || return 1
    set -- $ids
    [ "$#" -eq 1 ] || return 1
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$1"
}
# PID alone can be reused. Read starttime (field 22) after the final comm
# delimiter, since /proc/stat names can contain spaces and parentheses.
process_identity() {
    line=$(cat "$PROC_ROOT/$1/stat" 2>/dev/null) || return 1
    case "$line" in "$1 ("*") "*) ;; *) return 1 ;; esac
    fields=${line##*) }
    printf '%s\n' "$fields" | awk '
        $2 ~ /^[0-9]+$/ && $20 ~ /^[0-9]+$/ && $20 > 0 { print $2, $20; ok=1 }
        END { if (!ok) exit 1 }
    '
}
framework_identity() {
    zpid=$(unique_pid /system/bin/zygote64) || return 1
    spid=$(unique_pid /system/bin/system_server) || return 1
    [ "$(readlink "$PROC_ROOT/$zpid/exe")" = /system/bin/app_process64 ] &&
        [ "$(readlink "$PROC_ROOT/$spid/exe")" = /system/bin/app_process64 ] || return 1
    zidentity=$(process_identity "$zpid") && sidentity=$(process_identity "$spid") || return 1
    set -- $zidentity $sidentity
    [ "$#" = 4 ] && [ "$3" = "$zpid" ] && [ "$4" -ge "$2" ] || return 1
    printf '%s %s %s %s\n' "$zpid" "$2" "$spid" "$4"
}
running() { [ "$("$GETPROP_BIN" "init.svc.$1" 2>/dev/null)" = running ]; }
overlay_ok() {
    cmp -s "$source_lib" "$1/vendor/lib64/soundfx/lightningdsplib.so" &&
        grep -qi "$UUID" "$1/vendor/etc/audio_effects_config.xml" 2>/dev/null
}
library_mapped() {
    overlay_ok "$PROC_ROOT/$1/root" || return 1
    paths=$(awk '$NF ~ /\/lightningdsplib[.]so$/ { print $NF }' "$PROC_ROOT/$1/maps" 2>/dev/null)
    for mapped in $paths; do
        case "$mapped" in
            /vendor/lib64/soundfx/lightningdsplib.so|/system/vendor/lib64/soundfx/lightningdsplib.so|"$MODPATH"/system/vendor/lib64/soundfx/lightningdsplib.so|"$MODPATH"/.aidl-mount/*/lightningdsplib.so)
                cmp -s "$source_lib" "$PROC_ROOT/$1/root$mapped" && return 0 ;;
        esac
    done
    return 1
}
native_diagnostics() {
    helper=${LDSP_CONTROL_HELPER:-/vendor/bin/ldspctl}
    if [ -x "$helper" ] && cmp -s "$helper" "$MODPATH/common/files/control/arm64-v8a/ldspctl"; then
        "${LDSP_TIMEOUT_BIN:-/system/bin/timeout}" 3 "$helper" probe >"$LOGDIR/aidl-recovery-probe.txt" 2>&1
        "${LDSP_TIMEOUT_BIN:-/system/bin/timeout}" 3 "$helper" status >"$LOGDIR/aidl-recovery-native-status.txt" 2>&1
        return
    fi
    printf 'helper=unavailable_or_mismatched\n' >"$LOGDIR/aidl-recovery-probe.txt"
}
snapshot() {
    {
        printf 'boot_id=%s factory_pid=%s property=%s\n' "$boot_id" "$(factory_pid)" "$("$GETPROP_BIN" sys.audio.restart.hal)"
        cat "$work/targets"
        while read -r service exe old_pid; do
            printf '%s=%s pid=%s\n' "$service" "$("$GETPROP_BIN" "init.svc.$service")" "$(unique_pid "$exe")"
        done <"$work/targets"
        current=$(factory_pid)
        [ -z "$current" ] || grep -F lightningdsplib.so "$PROC_ROOT/$current/maps" 2>/dev/null
    } >"$LOGDIR/aidl-recovery-$1.txt"
}
# Require every originally running handler target to come back with a new PID.
# audioserver is observed, not explicitly restarted or assumed to survive.
reloaded() {
    running audioserver && [ "$("$GETPROP_BIN" sys.audio.restart.hal)" = 0 ] || return 1
    while read -r service exe old_pid; do
        running "$service" || return 1
        new_pid=$(unique_pid "$exe") || return 1
        [ "$new_pid" != "$old_pid" ] && [ "$(readlink "$PROC_ROOT/$new_pid/exe")" = "$exe" ] || return 1
    done <"$work/targets"
    current=$(factory_pid) || return 1
    [ "$current" = "$(unique_pid "$owner_exe")" ] && [ "$current" != "$before_pid" ]
}

[ "$("$ID_BIN" -u 2>/dev/null)" = 0 ] || finish 'BLOCKED reason=root_required'
[ -f "$MODPATH/.AIDL" ] && [ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/skip_mount" ] &&
    [ ! -f "$MODPATH/.aidl-recovery-disabled" ] && [ ! -f "$MODPATH/.samsung-firmware-recovery-disabled" ] ||
    finish 'BLOCKED reason=module_or_recovery_disabled'
boot_id=$(cat "$BOOT_ID_FILE" 2>/dev/null)
case "$boot_id" in ''|*[!a-zA-Z0-9-]*) finish 'BLOCKED reason=boot_id_unavailable' ;; esac
grep -q "^READY late_load=1 boot_id=$boot_id " "$LOGDIR/late-load.status" 2>/dev/null || finish 'BLOCKED reason=late_load_not_prepared_this_boot'
[ -x "$FLOCK_BIN" ] || finish 'BLOCKED reason=lock_unavailable'
exec 0>"$LOGDIR/manual-audio-reload.lock" || finish 'BLOCKED reason=lock_open_failed'
"$FLOCK_BIN" -n 0 || finish 'BLOCKED reason=recovery_in_progress'
[ "$("$GETPROP_BIN" ro.audio.ignore_effects 2>/dev/null)" != true ] || finish 'BLOCKED reason=effects_disabled_by_firmware restart=not_requested'
source_lib="$MODPATH/system/vendor/lib64/soundfx/lightningdsplib.so"
[ -s "$source_lib" ] || finish 'BLOCKED reason=source_library_missing'
mount_mode=--mount
[ "$MODE" != --check ] || mount_mode=--check
sh "$MODPATH/aidl-effect-mount.sh" "$mount_mode" >"$LOGDIR/aidl-effect-mount.log" 2>&1 || finish 'BLOCKED reason=effect_mount_failed restart=not_requested'
# --check never alters namespaces; it may report a plan for currently absent files.
[ "$MODE" = --check ] || overlay_ok "$INIT_ROOT" || finish 'BLOCKED reason=init_overlay_verification_failed restart=not_requested'
"$LINKER_BIN" --list "$source_lib" >"$LOGDIR/aidl-recovery-linker.txt" 2>&1 || finish 'BLOCKED reason=linker_dependency_resolution_failed'
# Shell-linker success is not proof of the HAL linker namespace.
mount_generation=$(cat "$LOGDIR/aidl-effect-mount.generation" 2>/dev/null)
activated_generation=$(cat "$LOGDIR/aidl-effect-mount.activated" 2>/dev/null)
before_pid=$(factory_pid) || finish 'BLOCKED reason=factory_owner_unavailable'
owner_exe=$(readlink "$PROC_ROOT/$before_pid/exe")
case "$owner_exe" in /vendor/bin/*audio*|/odm/bin/*audio*|/system/bin/*audio*|/system_ext/bin/*audio*) ;; *) finish 'BLOCKED reason=factory_executable_not_verified' ;; esac
[ "$(unique_pid "$owner_exe")" = "$before_pid" ] || finish 'BLOCKED reason=factory_process_not_unique'
running audioserver || finish 'BLOCKED reason=audioserver_not_running'

work=$(mktemp -d "$LOGDIR/aidl-preflight.XXXXXX") || finish 'BLOCKED reason=preflight_directory_failed'
: >"$work/services"
: >"$work/handler"
for dir in /vendor/etc/init /odm/etc/init /system/etc/init /system_ext/etc/init /product/etc/init; do
    [ ! -d "$INIT_ROOT$dir" ] || find "$INIT_ROOT$dir" -maxdepth 2 -type f -name '*.rc'
done >"$work/rc-files"
while IFS= read -r rc; do
    # Data-only parsing. Do not source, eval, or execute firmware file contents.
    awk '
    function flush() { if (name != "") print name, exe, user, override; name="" }
    { sub(/#.*/, "") }
    $1 == "service" { flush(); name=$2; exe=$3; user="root"; override=0; next }
    name != "" && $1 == "user" { user=$2 }
    name != "" && $1 == "override" { override=1 }
    /^[^ \t]/ && $1 != "" { flush() }
    END { flush() }
    ' "$rc" >>"$work/services"
    awk '
    { sub(/#.*/, ""); sub(/[ \t\r]+$/, "") }
    $1 == "on" && $2 == "property:sys.audio.restart.hal=1" {
        print "@handler"; active=1; if (NF != 2) print "@unsupported_condition"; next
    }
    active && /^[^ \t]/ { active=0 }
    active && NF { $1=$1; print }
    ' "$rc" >>"$work/handler"
done <"$work/rc-files"
# Resolve only an unambiguous override declaration. Real init import order
# remains authoritative; the selected executable must match the live PID below.
# Multiple overrides and duplicate base declarations remain ambiguous.
awk '
    { count[$1]++; row[$1]=$0; if ($4 == 1) { overrides[$1]++; replacement[$1]=$0 } }
    END {
        for (name in count) {
            if (count[name] == 1) print row[name];
            else if (count[name] == 2 && overrides[name] == 1) print replacement[name];
            else print name, "AMBIGUOUS", "unknown", 0;
        }
    }
' "$work/services" >"$work/services.effective"
mv "$work/services.effective" "$work/services"
owner=$(awk -v exe="$owner_exe" '$2 == exe && $3 == "audioserver" { print $1 }' "$work/services")
case "$owner" in ''|*[!a-zA-Z0-9_.:-]*) finish 'BLOCKED reason=factory_init_service_not_unique' ;; esac
[ "$(awk -v svc="$owner" '$1 == svc { n++ } END { print n+0 }' "$work/services")" = 1 ] && running "$owner" || finish 'BLOCKED reason=factory_init_service_not_running'
[ "$(grep -c '^@handler$' "$work/handler")" = 1 ] || finish 'BLOCKED reason=firmware_handler_not_unique'
# Accept only a bounded, ordered stop/start pair list and the final property
# reset. Reject restart, exec, class_stop, unrelated services and extra actions.
awk -v owner="$owner" '
$0 == "@handler" { next }
NF == 2 && $1 == "stop" && $2 ~ /^[a-zA-Z0-9_.:-]*audio[a-zA-Z0-9_.:-]*$/ && $2 != "audioserver" {
    if (starting || reset || seen[$2]++ || n >= 16) bad=1
    stops[++n]=$2; if ($2 == owner) owns=1; next
}
NF == 2 && $1 == "start" { starting=1; if (reset || $2 != stops[++j]) bad=1; next }
NF == 3 && $1 == "setprop" && $2 == "sys.audio.restart.hal" && $3 == "0" {
    if (reset++ || n != j || !starting) bad=1; next
}
{ bad=1 }
END { if (bad || n == 0 || n != j || reset != 1 || !owns) exit 1; for (i=1; i<=n; i++) print stops[i] }
' "$work/handler" >"$work/handler-services" || finish 'BLOCKED reason=firmware_handler_not_verified'
: >"$work/targets"
while IFS= read -r service; do
    running "$service" || continue
    exe=$(awk -v svc="$service" '$1 == svc { print $2 }' "$work/services")
    case "$exe" in /vendor/bin/*audio*|/odm/bin/*audio*|/system/bin/*audio*|/system_ext/bin/*audio*) ;; *) finish "BLOCKED reason=handler_target_not_verified service=$service" ;; esac
    pid=$(unique_pid "$exe") || finish "BLOCKED reason=handler_target_not_unique service=$service"
    [ "$(readlink "$PROC_ROOT/$pid/exe")" = "$exe" ] || finish 'BLOCKED reason=handler_executable_mismatch'
    printf '%s %s %s\n' "$service" "$exe" "$pid" >>"$work/targets"
done <"$work/handler-services"
[ -s "$work/targets" ] || finish 'BLOCKED reason=handler_has_no_running_targets'
snapshot before
if [ "$MODE" = --check ]; then
    finish "PREFLIGHT factory_service=$owner sequence=firmware_stop_start restart=not_requested registration=unverified processing=unverified" 0
fi
native_diagnostics
if library_mapped "$before_pid" && [ "$mount_generation" = "$activated_generation" ] &&
    grep -q '^LDSPCTL:OK:ready=1:protocol=3:contexts=1:writable=1:' "$LOGDIR/aidl-recovery-probe.txt"; then
    # Upgrade an old guard only from a proven live, matching native context.
    # This consumes the current session without requesting another restart;
    # a later verified framework recreation can then recover normally.
    if [ ! -e "$LIFECYCLE_GUARD" ] && [ "$(cat "$GUARD" 2>/dev/null)" = "$boot_id" ]; then
        framework=$(framework_identity) || finish 'BLOCKED reason=framework_lifecycle_unavailable'
        printf '%s %s\n' "$boot_id" "$framework" >"$LIFECYCLE_GUARD" || finish 'BLOCKED reason=lifecycle_guard_write_failed'
    fi
    finish 'LOADED reason=native_context_already_ready restart=not_needed processing=unverified' 0
fi
# Allow policy activation to catch up with the existing ten-second scheduler.
count=0
while ! grep -q 'policy=typed_rules_refreshed' "$LOGDIR/native-control.status" 2>/dev/null; do
    [ "$MODE" = --auto-once ] && [ "$count" -lt 20 ] && ! grep -q '^BLOCKED ' "$LOGDIR/native-control.status" 2>/dev/null || finish 'BLOCKED reason=typed_policy_not_ready'
    count=$((count + 1)); "$SLEEP_BIN" 1
done
# HAL restarts must not re-arm recovery. Only a newer zygote AND its newer
# system_server qualify. There is no lifetime cap across verified soft reboots.
# Old guards without a trusted lifecycle record remain fail-closed on upgrade.
framework=$(framework_identity) || finish 'BLOCKED reason=framework_lifecycle_unavailable'
set -- $framework
zstart=$2; sstart=$4
recorded_boot=
if [ -f "$LIFECYCLE_GUARD" ]; then
    [ "$(wc -l <"$LIFECYCLE_GUARD" | tr -d ' ')" = 1 ] || finish 'BLOCKED reason=lifecycle_guard_invalid'
    read -r recorded_boot old_zpid old_zstart old_spid old_sstart extra <"$LIFECYCLE_GUARD"
    case "$recorded_boot" in ''|*[!a-zA-Z0-9-]*) finish 'BLOCKED reason=lifecycle_guard_invalid' ;; esac
    for number in "$old_zpid" "$old_zstart" "$old_spid" "$old_sstart"; do
        case "$number" in ''|*[!0-9]*) finish 'BLOCKED reason=lifecycle_guard_invalid' ;; esac
        [ "$number" -gt 0 ] 2>/dev/null || finish 'BLOCKED reason=lifecycle_guard_invalid'
    done
    [ -z "$extra" ] || finish 'BLOCKED reason=lifecycle_guard_invalid'
    if [ "$recorded_boot" = "$boot_id" ]; then
        awk -v z="$zstart" -v s="$sstart" -v oz="$old_zstart" -v os="$old_sstart" \
            'BEGIN { exit !(z > oz && s > os) }' || finish 'BLOCKED reason=reload_already_attempted_this_boot'
    fi
fi
if [ -f "$GUARD" ] && [ "$(cat "$GUARD")" = "$boot_id" ] && [ "$recorded_boot" != "$boot_id" ]; then
    finish 'BLOCKED reason=reload_already_attempted_this_boot'
fi
for guard in "$LOGDIR/audio-hal-reload-samsung.boot-id" "$LOGDIR/audio-hal-reload-retry.boot-id" "$LOGDIR/audio-hal-reload-auto.boot-id" "$LOGDIR/manual-audio-reload.boot-id"; do
    [ ! -f "$guard" ] || [ "$(cat "$guard")" != "$boot_id" ] || finish 'BLOCKED reason=reload_already_attempted_this_boot'
done
[ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/skip_mount" ] && [ ! -f "$MODPATH/.aidl-recovery-disabled" ] && [ ! -f "$MODPATH/.samsung-firmware-recovery-disabled" ] || finish 'BLOCKED reason=recovery_disabled_during_preflight'
[ "$(factory_pid)" = "$before_pid" ] && overlay_ok "$INIT_ROOT" || finish 'BLOCKED reason=audio_state_changed_during_preflight'
while read -r service exe old_pid; do
    running "$service" && [ "$(unique_pid "$exe")" = "$old_pid" ] || finish 'BLOCKED reason=audio_state_changed_during_preflight'
done <"$work/targets"
case "$("$GETPROP_BIN" sys.audio.restart.hal)" in ''|0) ;; *) finish 'BLOCKED reason=firmware_reload_already_in_progress' ;; esac
[ "$(framework_identity)" = "$framework" ] || finish 'BLOCKED reason=framework_changed_during_preflight'
# Persist the consumed lifecycle before the legacy boot marker and request. A
# partial/failed write blocks rather than silently enabling another restart.
printf '%s %s\n' "$boot_id" "$framework" >"$LIFECYCLE_GUARD" || finish 'BLOCKED reason=lifecycle_guard_write_failed'
printf '%s\n' "$boot_id" >"$GUARD" || finish 'BLOCKED reason=guard_write_failed'
"$SETPROP_BIN" sys.audio.restart.hal 1 || finish 'BLOCKED reason=firmware_reload_request_failed'
count=0
while [ "$count" -lt 20 ]; do
    if reloaded && library_mapped "$current"; then break; fi
    count=$((count + 1)); "$SLEEP_BIN" 1
done
snapshot after
native_diagnostics
if [ "$count" -ge 20 ]; then
    "$LOGCAT_BIN" -d -t 400 2>/dev/null | grep -iE 'lightningdsp|ldsp.control|EffectFactory|dlopen|CANNOT LINK|avc:.*denied' >"$LOGDIR/aidl-recovery-loader.txt"
    finish 'BLOCKED reason=reload_or_library_mapping_not_observed registration=unverified processing=unverified'
fi
stable_pid=$current
count=0
# Observe beyond the reported five-second failure, without another request.
while [ "$count" -lt 6 ]; do
    "$SLEEP_BIN" 1
    if ! reloaded || [ "$current" != "$stable_pid" ] || ! library_mapped "$current"; then
        snapshot unstable
        native_diagnostics
        "$LOGCAT_BIN" -d -t 400 2>/dev/null | grep -iE 'lightningdsp|ldsp.control|EffectFactory|dlopen|CANNOT LINK|avc:.*denied' >"$LOGDIR/aidl-recovery-loader.txt"
        finish 'BLOCKED reason=audio_services_unstable_after_reload'
    fi
    count=$((count + 1))
done
[ "$(cat "$LOGDIR/aidl-effect-mount.generation" 2>/dev/null)" = "$mount_generation" ] || finish 'BLOCKED reason=effect_mount_changed_during_reload'
printf '%s\n' "$mount_generation" >"$LOGDIR/aidl-effect-mount.activated" || finish 'BLOCKED reason=mount_activation_record_failed'
native_diagnostics
finish "LOADED factory_service=$owner restart=firmware_once before_hal=$before_pid after_hal=$current registration=unverified processing=unverified" 0
