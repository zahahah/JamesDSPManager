#!/system/bin/sh
# Read-only evidence for the Samsung AIDL factory. Safe to run after boot;
# it does not mount files, restart services or change app state.

MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
OUT="$LOGDIR/samsung-aidl-diagnostics.txt"
FACTORY=android.hardware.audio.effect.IFactory/default
UUID=f27317f4-c984-4de6-9a90-545759495bf2

mkdir -p "$LOGDIR" || exit 1
{
	printf 'boot_id='
	cat /proc/sys/kernel/random/boot_id 2>/dev/null || printf 'unavailable\n'
	for role in init zygote64 audiohalservice.qti audioserver; do
		case "$role" in
			init) pid=1 ;;
			*) pid=$(pidof -s "$role" 2>/dev/null) ;;
		esac
		printf '%s_pid=%s\n' "$role" "${pid:-unavailable}"
		[ -n "$pid" ] || continue
		printf '%s_mount_namespace=%s\n' "$role" \
			"$(readlink "/proc/$pid/ns/mnt" 2>/dev/null || printf unavailable)"
		printf '%s_jdsp_mounts=%s\n' "$role" \
			"$(grep -Ec 'libjamesdsp|audio_effects_config' "/proc/$pid/mountinfo" 2>/dev/null || :)"
		if [ "$role" = audiohalservice.qti ]; then
			for path in /vendor/lib64/soundfx/libjamesdsp.so \
				/vendor/lib64/soundfx/libjamesdsp_real.so \
				/vendor/etc/audio_effects_config.xml; do
				if [ -f "/proc/$pid/root$path" ]; then
					printf 'hal_sees=%s\n' "$path"
				else
					printf 'hal_cannot_stat=%s\n' "$path"
				fi
			done
			printf 'hal_loaded_jdsp_maps=%s\n' \
				"$(grep -ic 'libjamesdsp' "/proc/$pid/maps" 2>/dev/null || :)"
		fi
	done
	factory_dump=$(dumpsys "$FACTORY" 2>&1)
	printf 'factory_dump_bytes=%s\n' "${#factory_dump}"
	if printf '%s\n' "$factory_dump" | grep -qi "$UUID"; then
		printf 'factory_jdsp_descriptor=present\n'
	else
		printf 'factory_jdsp_descriptor=missing_or_dump_unavailable\n'
	fi
	printf '%s\n' "$factory_dump" | grep -iE \
		'Effects \(|error|fail|james|jdsp|f27317f4|f98765f4' | head -n 50
	printf '%s\n' 'recent_factory_log_begin'
	logcat -d -b all -v threadtime 2>/dev/null | grep -iE \
		'EffectConfig|EffectFactory|JDSPPinWrap|libjamesdsp|avc: denied.*(audio|jamesdsp|soundfx|effect)' | tail -n 100
	printf '%s\n' 'recent_factory_log_end'
} >"$OUT" 2>&1
