#!/system/bin/sh
# One-shot, read-only capture of Samsung AIDL effect factory startup.
# Launched only by an experimental Samsung late-load package.

MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
OUT="$LOGDIR/samsung-aidl-early-log.txt"
STATUS="$LOGDIR/samsung-aidl-early-log.status"
LOGCAT_BIN=${JDSP_LOGCAT_BIN:-/system/bin/logcat}
CAPTURE_SECONDS=${JDSP_CAPTURE_SECONDS:-75}

mkdir -p "$LOGDIR" || exit 1
case "$CAPTURE_SECONDS" in
	''|*[!0-9]*) CAPTURE_SECONDS=75 ;;
esac
[ "$CAPTURE_SECONDS" -gt 0 ] && [ "$CAPTURE_SECONDS" -le 120 ] || CAPTURE_SECONDS=75

boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
version=$(sed -n 's/^versionCode=//p' "$MODPATH/module.prop" | head -n 1)
guard="$LOGDIR/.samsung-aidl-early-log.${boot_id:-unknown}.${version:-unknown}"

if [ ! -x "$LOGCAT_BIN" ]; then
	printf 'BLOCKED reason=logcat_unavailable\n' >"$STATUS"
	exit 1
fi
mkdir "$guard" 2>/dev/null || exit 0

printf 'capture_begin=%s boot_id=%s hal_pid=%s\n' \
	"$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
	"$boot_id" \
	"$(pidof audiohalservice.qti 2>/dev/null | cut -d ' ' -f 1)" >"$OUT"
printf 'RUNNING seconds=%s\n' "$CAPTURE_SECONDS" >"$STATUS"

"$LOGCAT_BIN" -b all -v threadtime -s \
	'JDSPPinWrap:*' 'AHAL_EffectFactoryQti:*' 'AHAL_EffectConfigQti:*' \
	'EffectsFactoryHalAidl:*' 'linker:*' 'libc:*' \
	>>"$OUT" 2>&1 &
logcat_pid=$!
sleep "$CAPTURE_SECONDS"
if kill -0 "$logcat_pid" 2>/dev/null; then
	kill "$logcat_pid" 2>/dev/null || :
	logcat_state=stopped_after_window
else
	logcat_state=exited_early
fi
wait "$logcat_pid" 2>/dev/null || :
printf 'capture_end=%s hal_pid=%s logcat=%s\n' \
	"$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
	"$(pidof audiohalservice.qti 2>/dev/null | cut -d ' ' -f 1)" \
	"$logcat_state" >>"$OUT"
printf 'COMPLETE logcat=%s\n' "$logcat_state" >"$STATUS"
