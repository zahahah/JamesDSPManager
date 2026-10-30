#!/system/bin/sh
# Stage only module-owned files. Never restart servicemanager/audio or disable SELinux.
MODE=${1:-diagnose}
MODPATH=${2:-${0%/*}}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR"
STATUS="$LOGDIR/native-control.status"
CONTEXT_SOURCE=${LDSP_SERVICE_CONTEXTS:-/vendor/etc/selinux/vendor_service_contexts}
VENDOR="$MODPATH/system/vendor"

apply_policy() {
    rules="$1"
    if [ -x /data/adb/ksu/bin/ksud ]; then
        /data/adb/ksu/bin/ksud sepolicy apply "$rules"
    elif command -v ksud >/dev/null 2>&1; then
        ksud sepolicy apply "$rules"
    elif command -v magiskpolicy >/dev/null 2>&1; then
        magiskpolicy --live --apply "$rules"
    elif [ -x /data/adb/magisk/magiskpolicy ]; then
        /data/adb/magisk/magiskpolicy --live --apply "$rules"
    elif [ -x /data/adb/ap/bin/apd ]; then
        /data/adb/ap/bin/apd sepolicy --live --apply "$rules"
    else
        return 1
    fi
}

case "$MODE" in
prepare)
    [ -f "$MODPATH/.AIDL" ] || exit 0
    source="$MODPATH/common/files/control/arm64-v8a/ldspctl"
    if [ -f "$source" ]; then
        mkdir -p "$VENDOR/bin"
        cp "$source" "$VENDOR/bin/ldspctl" || exit 1
        chmod 0755 "$VENDOR/bin/ldspctl" || exit 1
        chcon u:object_r:vendor_file:s0 "$VENDOR/bin/ldspctl" 2>/dev/null || true
    fi
    if [ -f "$CONTEXT_SOURCE" ]; then
        destination="$VENDOR/etc/selinux/vendor_service_contexts"
        mkdir -p "${destination%/*}"
        tmp="$destination.tmp.$$"
        awk '$1 != "ldsp.control" { print }' "$CONTEXT_SOURCE" >"$tmp" || exit 1
        printf '\nldsp.control    u:object_r:ldsp_control_service:s0\n' >>"$tmp"
        mv -f "$tmp" "$destination" || exit 1
        chcon u:object_r:vendor_service_contexts_file:s0 "$destination" 2>/dev/null || true
    else
        printf 'BLOCKED reason=vendor_service_contexts_missing restart=not_requested\n' >"$STATUS"
        exit 0
    fi
    policy=static_or_unverified
    if apply_policy "$MODPATH/native-control/global-service.rule" >"$LOGDIR/native-control-policy.log" 2>&1; then
        policy=typed_rules_applied
    fi
    # A late file overlay does not refresh an existing ServiceManager label
    # cache. Do not silently grant broad default-service permissions to fix it.
    if [ -f "$MODPATH/.ldsp-control-default-label-opt-in" ]; then
        if apply_policy "$MODPATH/native-control/default-label-opt-in.rule" >>"$LOGDIR/native-control-policy.log" 2>&1; then
            policy=explicit_default_label_opt_in
        else
            policy=default_label_opt_in_failed
        fi
    fi
    helper=missing
    [ -x "$VENDOR/bin/ldspctl" ] && helper=staged
    printf 'STAGED helper=%s policy=%s label_cache=unverified late_load=%s restart=not_requested processing=unverified\n' \
        "$helper" "$policy" "${KSU_LATE_LOAD:-0}" >"$STATUS"
    ;;
activate)
    [ -f "$MODPATH/.AIDL" ] || exit 0
    if [ -f "$MODPATH/disable" ] || [ -f "$MODPATH/skip_mount" ]; then
        printf 'BLOCKED reason=module_not_mounted restart=not_requested\n' >"$STATUS"
        exit 0
    fi
    helper=${LDSP_CONTROL_HELPER:-/vendor/bin/ldspctl}
    attempts=${LDSP_ACTIVATION_ATTEMPTS:-20}
    case "$attempts" in ''|*[!0-9]*) attempts=20 ;; esac
    [ "$attempts" -ge 1 ] && [ "$attempts" -le 20 ] || attempts=20
    count=0
    mounted=false
    while [ "$count" -lt "$attempts" ]; do
        contexts=${LDSP_MANAGER_CONTEXTS:-}
        if [ -z "$contexts" ]; then
            manager=$(pidof servicemanager 2>/dev/null | cut -d ' ' -f 1)
            contexts="/proc/${manager:-0}/root/vendor/etc/selinux/vendor_service_contexts"
        fi
        if awk '$1 == "ldsp.control" && $2 == "u:object_r:ldsp_control_service:s0" { found=1 }
                END { exit !found }' "$contexts" 2>/dev/null && [ -x "$helper" ]; then
            mounted=true
            break
        fi
        count=$((count + 1))
        [ "$count" -ge "$attempts" ] || sleep 1
    done
    if [ "$mounted" != true ]; then
        printf 'BLOCKED reason=service_label_not_mounted helper_or_manager_unavailable=1 restart=not_requested\n' >"$STATUS"
        exit 0
    fi
    # AOSP Access::getSehandle() reopens service_contexts when the SELinux
    # policy status changes. Refresh only our typed policy AFTER the mapping is
    # visible in ServiceManager's mount namespace, not just in post-fs-data.
    # Do not grant generic default_android_service permissions or restart it.
    if ! apply_policy "$MODPATH/native-control/global-service.rule" >>"$LOGDIR/native-control-policy.log" 2>&1; then
        printf 'BLOCKED reason=typed_policy_refresh_failed restart=not_requested\n' >"$STATUS"
        exit 0
    fi
    printf 'WAITING control=ldsp.control policy=typed_rules_refreshed publication=unverified restart=not_requested processing=unverified\n' >"$STATUS"
    count=0
    while [ "$count" -lt "$attempts" ]; do
        reply=$("$helper" probe 2>&1)
        result=$?
        printf '%s\n' "$reply" >"$LOGDIR/native-control-probe.log"
        if [ "$result" -eq 0 ] && printf '%s\n' "$reply" | grep -qx 'LDSPCTL:OK:ready=1:protocol=3:contexts=1:writable=1:publication=3'; then
            printf 'READY control=ldsp.control policy=typed_rules_refreshed protocol=3 contexts=1 writable=1 publication=3 restart=not_requested processing=unverified\n' >"$STATUS"
            exit 0
        fi
        count=$((count + 1))
        [ "$count" -ge "$attempts" ] || sleep 1
    done
    ;;
diagnose)
    printf '=== ldsp.control ===\n'
    service list 2>/dev/null | grep -F 'ldsp.control' || true
    if [ -x /vendor/bin/ldspctl ]; then
        /vendor/bin/ldspctl probe
        /vendor/bin/ldspctl status
    else
        printf 'LDSPCTL:ERR:helper-not-mounted\n'
        exit 1
    fi
    ;;
*) exit 2 ;;
esac
