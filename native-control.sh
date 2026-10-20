#!/system/bin/sh
# Stage only module-owned files. Never restart servicemanager/audio or disable SELinux.
MODE=${1:-diagnose}
MODPATH=${2:-${0%/*}}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR"
STATUS="$LOGDIR/native-control.status"
CONTEXT_SOURCE=${JDSP_SERVICE_CONTEXTS:-/vendor/etc/selinux/vendor_service_contexts}
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
    source="$MODPATH/common/files/control/arm64-v8a/jdspctl"
    if [ -f "$source" ]; then
        mkdir -p "$VENDOR/bin"
        cp "$source" "$VENDOR/bin/jdspctl" || exit 1
        chmod 0755 "$VENDOR/bin/jdspctl" || exit 1
        chcon u:object_r:vendor_file:s0 "$VENDOR/bin/jdspctl" 2>/dev/null || true
    fi
    if [ -f "$CONTEXT_SOURCE" ]; then
        destination="$VENDOR/etc/selinux/vendor_service_contexts"
        mkdir -p "${destination%/*}"
        tmp="$destination.tmp.$$"
        awk '$1 != "jdsp.control" { print }' "$CONTEXT_SOURCE" >"$tmp" || exit 1
        printf '\njdsp.control    u:object_r:jdsp_control_service:s0\n' >>"$tmp"
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
    if [ -f "$MODPATH/.jdsp-control-default-label-opt-in" ]; then
        if apply_policy "$MODPATH/native-control/default-label-opt-in.rule" >>"$LOGDIR/native-control-policy.log" 2>&1; then
            policy=explicit_default_label_opt_in
        else
            policy=default_label_opt_in_failed
        fi
    fi
    helper=missing
    [ -x "$VENDOR/bin/jdspctl" ] && helper=staged
    printf 'STAGED helper=%s policy=%s label_cache=unverified late_load=%s restart=not_requested processing=unverified\n' \
        "$helper" "$policy" "${KSU_LATE_LOAD:-0}" >"$STATUS"
    ;;
diagnose)
    printf '=== jdsp.control ===\n'
    service list 2>/dev/null | grep -F 'jdsp.control' || true
    if [ -x /vendor/bin/jdspctl ]; then
        /vendor/bin/jdspctl probe
        /vendor/bin/jdspctl status
    else
        printf 'JDSPCTL:ERR:helper-not-mounted\n'
        exit 1
    fi
    ;;
*) exit 2 ;;
esac
