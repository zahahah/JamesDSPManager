#!/system/bin/sh
# Resolve only HAL identities verified against a working device. Unknown models
# fail closed instead of guessing a vendor HAL process name.
MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
mkdir -p "$LOGDIR"
GETPROP_BIN=${JDSP_GETPROP_BIN:-/system/bin/getprop}
SLEEP_BIN=${JDSP_SLEEP_BIN:-/system/bin/sleep}

case "${1:-}" in
	--auto-once) MODE=--auto-once ;;
	--retry) MODE=--retry-once ;;
	*)
		echo 'Usage: audio-hal-recovery.sh --auto-once|--retry' >&2
		exit 2
		;;
esac

# native-control.sh runs independently during module activation. Give its typed
# policy refresh time to finish after the requested 10-second late-load delay.
if [ "$MODE" = --auto-once ]; then
	count=0
	while ! grep -q 'policy=typed_rules_refreshed' "$LOGDIR/native-control.status" 2>/dev/null; do
		if grep -q '^BLOCKED ' "$LOGDIR/native-control.status" 2>/dev/null || [ "$count" -ge 20 ]; then
			printf 'BLOCKED reason=typed_policy_not_ready mode=%s\n' "$MODE" \
				| tee "$LOGDIR/audio-hal-recovery.status"
			exit 1
		fi
		count=$((count + 1))
		"$SLEEP_BIN" 1
	done
fi

device=$("$GETPROP_BIN" ro.product.device 2>/dev/null)
case "$device" in
	mustang)
		JDSP_AUDIO_HAL_INIT_SERVICE=vendor.audio-hal-aidl
		JDSP_AUDIO_HAL_PROCESS=android.hardware.audio.service-aidl.aoc
		;;
	*)
		printf 'BLOCKED reason=unverified_audio_hal_target device=%s mode=%s\n' \
			"${device:-unknown}" "$MODE" | tee "$LOGDIR/audio-hal-recovery.status"
		exit 1
		;;
esac
export JDSP_AUDIO_HAL_INIT_SERVICE JDSP_AUDIO_HAL_PROCESS
exec sh "$MODPATH/manual-audio-reload.sh" "$MODE"
