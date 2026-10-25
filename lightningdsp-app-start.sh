#!/system/bin/sh
# Background process/service initialization only. Never opens an Activity or changes app preferences.
MODPATH=${1:-${0%/*}}
STATUS="$MODPATH/logs/app-start.status"
DELAY=${2:-10}
case "$DELAY" in 0|10) ;; *) exit 2 ;; esac
SLEEP_BIN=${LDSP_SLEEP_BIN:-sleep}
AM_BIN=${LDSP_AM_BIN:-am}
PM_BIN=${LDSP_PM_BIN:-pm}
GETPROP_BIN=${LDSP_GETPROP_BIN:-getprop}
TIMEOUT_BIN=${LDSP_TIMEOUT_BIN:-timeout}
mkdir -p "$MODPATH/logs" || exit 1

status() { printf '%s\n' "$*" >"$STATUS"; }
[ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/remove" ] || {
    status 'SKIPPED reason=module_disabled_or_removed'
    exit 0
}
command -v "$TIMEOUT_BIN" >/dev/null 2>&1 || {
    status 'BLOCKED reason=timeout_tool_missing'
    exit 1
}

status "SCHEDULED delay_seconds=$DELAY ui=not_requested"
[ "$DELAY" = 0 ] || "$SLEEP_BIN" "$DELAY" || exit 1
# Install/package-manager readiness can lag activation: 30 bounded checks, two seconds apart.
attempt=0
while [ "$attempt" -lt 30 ]; do
    [ ! -f "$MODPATH/disable" ] && [ ! -f "$MODPATH/remove" ] || {
        status 'SKIPPED reason=module_disabled_or_removed'
        exit 0
    }
    USER_ID=$("$TIMEOUT_BIN" 3 "$AM_BIN" get-current-user 2>/dev/null)
    case "$USER_ID" in ''|*[!0-9]*) USER_ID= ;; esac
    if [ "$("$TIMEOUT_BIN" 3 "$GETPROP_BIN" sys.boot_completed 2>/dev/null)" = 1 ] && [ -n "$USER_ID" ] &&
        "$TIMEOUT_BIN" 3 "$PM_BIN" path --user "$USER_ID" com.lightning.dsp 2>/dev/null | grep -q '^package:'; then
        # The historical component is still the declared root DSP service. Reuse it,
        # rather than creating a second service or a second native DSP context.
        OUTPUT=$("$TIMEOUT_BIN" 15 "$AM_BIN" start-foreground-service --user "$USER_ID"             -n com.lightning.dsp/me.timschneeberger.rootlessjamesdsp.service.RootAudioProcessorService             -a com.lightning.dsp.root.service.START_BACKGROUND 2>&1)
        result=$?
        if [ "$result" = 0 ] && ! printf '%s\n' "$OUTPUT" | grep -qiE 'Error:|Exception|not allowed|not found'; then
            status "DISPATCHED user=$USER_ID ui=not_requested processing=unverified"
            exit 0
        fi
        status "FAILED reason=service_dispatch exit=$result ui=not_requested processing=unverified"
        exit 1
    fi
    attempt=$((attempt + 1))
    [ "$attempt" -ge 30 ] || "$SLEEP_BIN" 2
done
status 'DEFERRED reason=boot_or_package_not_ready ui=not_requested processing=unverified'
exit 1
