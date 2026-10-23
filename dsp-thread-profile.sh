#!/system/bin/sh
# Apply the vendor's explicitly-defined RealtimePerformance task profile only
# when it is the tested, single-action task-group mapping for the JamesDSP HAL
# thread. Unsupported vendor configurations are left untouched.

MODE=${1:---watch}
MODPATH=${2:-${0%/*}}
LOGDIR="$MODPATH/logs"
LOCK="$MODPATH/.dsp-thread-profile.lock"
APPLIED_TIDS=

if [ -n "${JDSP_PROFILE_TEST_ROOT:-}" ]; then
	PROC_ROOT="$JDSP_PROFILE_TEST_ROOT/proc"
	PROFILE_JSON="$JDSP_PROFILE_TEST_ROOT/vendor_task_profiles.json"
	SETTASKPROFILE="$JDSP_PROFILE_TEST_ROOT/settaskprofile"
	SLEEP_BIN="$JDSP_PROFILE_TEST_ROOT/sleep"
else
	PROC_ROOT=/proc
	PROFILE_JSON=/vendor/etc/task_profiles.json
	SETTASKPROFILE=/system/bin/settaskprofile
	SLEEP_BIN=/system/bin/sleep
fi

case "$MODE" in
	--watch|--once) ;;
	*) echo "Usage: $0 [--watch|--once] [module_path]" >&2; exit 2 ;;
esac

write_status() {
	mkdir -p "$LOGDIR" 2>/dev/null
	printf '%s\n' "$1" >"$LOGDIR/dsp-thread-profile.status" 2>/dev/null
}

log_event() {
	mkdir -p "$LOGDIR" 2>/dev/null
	printf '%s\n' "$1" >>"$LOGDIR/dsp-thread-profile.log" 2>/dev/null
}

# Fail closed unless the vendor's effective profile is a single WriteFile
# action to its own task-group interface. In particular, do not fall through
# to AOSP's generic RealtimePerformance (cpu/rt) profile on other devices.
profile_is_supported() {
	[ -x "$SETTASKPROFILE" ] || return 1
	[ -r "$PROFILE_JSON" ] || return 1
	[ -r "$PROC_ROOT/vendor_sched/dump_task" ] || return 1
	[ -e "$PROC_ROOT/vendor_sched/groups/ta/set_task_group" ] || return 1
	[ -e "$PROC_ROOT/vendor_sched/groups/fg/set_task_group" ] || return 1
	# A duplicate profile name makes the effective mapping parser-dependent.
	[ "$(grep -Ec '"Name"[[:space:]]*:[[:space:]]*"RealtimePerformance"' "$PROFILE_JSON" 2>/dev/null)" = 1 ] || return 1
	PROFILE_BLOCK=$(awk '
		function brace_delta(line, i, ch, quoted, escaped, delta) {
			delta = 0; quoted = 0; escaped = 0
			for (i = 1; i <= length(line); i++) {
				ch = substr(line, i, 1)
				if (quoted && ch == "\\" && !escaped) { escaped = 1; continue }
				if (ch == "\"" && !escaped) quoted = !quoted
				if (!quoted && ch == "{") delta++
				if (!quoted && ch == "}") delta--
				escaped = 0
			}
			return delta
		}
		!active && /"Name"[[:space:]]*:[[:space:]]*"RealtimePerformance"/ {
			active = 1; depth = 1; block = $0 "\n"; next
		}
		active {
			block = block $0 "\n"
			depth += brace_delta($0)
			if (depth == 0) { print block; found = 1; exit }
		}
		END { if (!found) exit 1 }
	' "$PROFILE_JSON" 2>/dev/null) || return 1
	[ -n "$PROFILE_BLOCK" ] || return 1
	name_count=$(printf '%s\n' "$PROFILE_BLOCK" | grep -Ec '"Name"[[:space:]]*:')
	file_count=$(printf '%s\n' "$PROFILE_BLOCK" | grep -Ec '"FilePath"[[:space:]]*:')
	proc_file_count=$(printf '%s\n' "$PROFILE_BLOCK" | grep -Ec '"ProcFilePath"[[:space:]]*:')
	value_count=$(printf '%s\n' "$PROFILE_BLOCK" | grep -Ec '"Value"[[:space:]]*:')
	[ "$name_count" = 2 ] && [ "$file_count" = 1 ] && \
		[ "$proc_file_count" = 1 ] && [ "$value_count" = 1 ] || return 1
	printf '%s\n' "$PROFILE_BLOCK" | grep -Eq '"Name"[[:space:]]*:[[:space:]]*"WriteFile"' || return 1
	printf '%s\n' "$PROFILE_BLOCK" | grep -Eq '"FilePath"[[:space:]]*:[[:space:]]*"/proc/vendor_sched/groups/ta/set_task_group"' || return 1
	printf '%s\n' "$PROFILE_BLOCK" | grep -Eq '"ProcFilePath"[[:space:]]*:[[:space:]]*"/proc/vendor_sched/groups/ta/set_proc_group"' || return 1
	printf '%s\n' "$PROFILE_BLOCK" | grep -Eq '"Value"[[:space:]]*:[[:space:]]*"<pid>"' || return 1
	return 0
}

task_group() {
	awk -v tid="$1" '$1 == tid && $2 == "James" && $3 == "Audio" && $4 == "DS" { print $5; exit }' \
		"$PROC_ROOT/vendor_sched/dump_task" 2>/dev/null
}

matching_tasks() {
	awk '$2 == "James" && $3 == "Audio" && $4 == "DS" && ($5 == "fg" || $5 == "ta") { print $1 ":" $5 }' \
		"$PROC_ROOT/vendor_sched/dump_task" 2>/dev/null
}

restore_applied() {
	for tid in $APPLIED_TIDS; do
		[ "$(task_group "$tid")" = ta ] || continue
		echo "$tid" >"$PROC_ROOT/vendor_sched/groups/fg/set_task_group" 2>/dev/null || continue
		log_event "RESTORED tid=$tid group=fg"
	done
}

release_lock() {
	if [ -f "$LOCK/pid" ] && [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ]; then
		rm -f "$LOCK/pid"
		rmdir "$LOCK" 2>/dev/null
	fi
}

cleanup() {
	restore_applied
	release_lock
}

trap cleanup EXIT
trap 'exit 0' HUP INT TERM

if ! profile_is_supported; then
	write_status 'SKIPPED reason=vendor_realtime_profile_not_supported'
	exit 0
fi

if [ "$MODE" = --watch ]; then
	if ! mkdir "$LOCK" 2>/dev/null; then
		old_pid=$(cat "$LOCK/pid" 2>/dev/null)
		old_cmd=
		[ -n "$old_pid" ] && [ -r "/proc/$old_pid/cmdline" ] && \
			old_cmd=$(tr '\000' ' ' <"/proc/$old_pid/cmdline" 2>/dev/null)
		case "$old_cmd" in
			*dsp-thread-profile.sh*) exit 0 ;;
		esac
		rm -f "$LOCK/pid" 2>/dev/null
		rmdir "$LOCK" 2>/dev/null
		mkdir "$LOCK" 2>/dev/null || exit 0
	fi
	printf '%s\n' "$$" >"$LOCK/pid"
fi

write_status 'WAITING reason=James_Audio_DS_thread_not_found'
while :; do
	[ -d "$MODPATH" ] || break
	[ ! -f "$MODPATH/disable" ] || break
	TASKS=$(matching_tasks)
	if [ -n "$TASKS" ]; then
		for item in $TASKS; do
			tid=${item%%:*}
			group=${item#*:}
			case "$tid" in ''|*[!0-9]*) continue ;; esac
			[ "$group" = fg ] || continue
			"$SETTASKPROFILE" "$tid" RealtimePerformance >/dev/null 2>&1 || {
				write_status "FAILED reason=task_profile_failed tid=$tid"
				continue
			}
			if [ "$(task_group "$tid")" = ta ]; then
				case " $APPLIED_TIDS " in *" $tid "*) ;; *) APPLIED_TIDS="$APPLIED_TIDS $tid" ;; esac
				write_status "APPLIED profile=RealtimePerformance tid=$tid group=ta"
				log_event "APPLIED tid=$tid original=fg target=ta"
			else
				write_status "FAILED reason=task_group_not_confirmed tid=$tid"
			fi
		done
	fi
	[ "$MODE" = --once ] && break
	"$SLEEP_BIN" 5
done

if [ ! -d "$MODPATH" ] || [ -f "$MODPATH/disable" ]; then
	write_status 'STOPPED reason=module_disabled_or_removed'
fi
exit 0
