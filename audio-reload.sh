#!/system/bin/sh

MODPATH=${0%/*}
LOGDIR="$MODPATH/logs"
STATUS="$LOGDIR/audio-reload.status"
BOOT_GUARD="$LOGDIR/audio-reload.boot-id"
DUMP_BEFORE="$LOGDIR/audio-reload-before.txt"
DUMP_AFTER="$LOGDIR/audio-reload-after.txt"
LDSP_UUID=f27317f4-c984-4de6-9a90-545759495bf2
DUMP_STOCK_UUID_ANCHOR=50deaa30-4a83-4b1f-bfe3-dec6d605ede0
XML_UUID_ANCHOR=ce772f20-847d-11df-bb17-0002a5d5c51b
XML_LIB_ANCHOR=libbundleaidl.so
EXPECTED_STOCK_EFFECT_COUNT=21
EXPECTED_EFFECT_COUNT_WITH_LDSP=22
STOCK_UUIDS='
ce772f20-847d-11df-bb17-0002a5d5c51b
8631f300-72e2-11df-b57e-0002a5d5c51b
1d4033c0-8557-11df-9f2d-0002a5d5c51b
119341a0-8469-11df-81f9-0002a5d5c51b
d069d9e0-8329-11df-9168-0002a5d5c51b
e0e6539b-1781-7261-676f-6d7573696340
4a387fc0-8ab3-11df-8bad-0002a5d5c51b
f29a1400-a3bb-11df-8ddc-0002a5d5c51b
c7a511a0-a3bb-11df-860e-0002a5d5c51b
172cdf00-a3bc-11df-a72f-0002a5d5c51b
93f04452-e4fe-41cc-91f9-e475b6d1d69f
fa415329-2034-4bea-b5dc-5b381c8d1e2c
97c4acd1-8b82-4f2f-832e-c2fe5d7a9931
50deaa30-4a83-4b1f-bfe3-dec6d605ede0
c7e3b29d-e797-4cf9-9912-17c1956510cc
f8f88a03-fdf8-4554-8e60-77fbf8f2d3b0
1bf15eb7-8f49-4fd8-8380-0767fd5680f3
99fb2ecb-3426-4a0e-8082-1a1da5604b7d
7b491460-8d4d-11e0-bd61-0002a5d5c51b
58b4b260-8e06-11e0-aa8e-0002a5d5c51b
6507a0e2-a9bd-44ca-9116-b740a284ee5f
'
DEFAULT_FACTORY=android.hardware.audio.effect.IFactory/default
AML_FACTORY=android.hardware.audio.effect.IFactory/aml
INIT_SERVICE=${LDSP_AUDIO_HAL_INIT_SERVICE:-vendor.audio-hal-aidl}
HAL_PROCESS=${LDSP_AUDIO_HAL_PROCESS:-android.hardware.audio.service-aidl.aoc}
PIXAML_PROCESS=${LDSP_PIXAML_PROCESS:-vendor.aml.effect-service}
GETPROP_BIN=${LDSP_GETPROP_BIN:-/system/bin/getprop}
SETPROP_BIN=${LDSP_SETPROP_BIN:-/system/bin/setprop}
DUMPSYS_BIN=${LDSP_DUMPSYS_BIN:-/system/bin/dumpsys}
SERVICE_BIN=${LDSP_SERVICE_BIN:-/system/bin/service}
LINKER_BIN=${LDSP_LINKER_BIN:-/system/bin/linker64}
PIDOF_BIN=${LDSP_PIDOF_BIN:-/system/bin/pidof}
SLEEP_BIN=${LDSP_SLEEP_BIN:-/system/bin/sleep}
BOOT_ID_FILE=${LDSP_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}
PROC_ROOT=${LDSP_PROC_ROOT:-/proc}
EFFECT_XML=${LDSP_EFFECT_XML:-/vendor/etc/audio_effects_config.xml}
EFFECT_LIB=${LDSP_EFFECT_LIB:-/vendor/lib64/soundfx/lightningdsplib.so}

mkdir -p "$LOGDIR"

status() {
	printf '%s\n' "$1" >"$STATUS"
	exit 0
}

contains_ldsp() {
	"$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>/dev/null | grep -qi "$LDSP_UUID"
}

factory_effect_count() {
	"$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>/dev/null |
		awk '/^Effects \([0-9][0-9]*\):/ { value=$2; gsub(/[():]/, "", value); print value; exit }'
}

has_all_stock_descriptors() {
	factory_dump=$("$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>/dev/null) || return 1
	for uuid in $STOCK_UUIDS; do
		printf '%s\n' "$factory_dump" | grep -qi "$uuid" || return 1
	done
}

service_found() {
	"$SERVICE_BIN" check "$1" 2>/dev/null | grep -q ': found'
}

hal_pid() {
	"$PIDOF_BIN" -s "$HAL_PROCESS" 2>/dev/null
}

alive() {
	[ -n "$1" ] && [ -d "$PROC_ROOT/$1" ]
}

[ "${KSU_LATE_LOAD:-0}" = 1 ] || status 'SKIPPED reason=not_late_load'
[ -f "$MODPATH/.late-load-reload-experimental" ] || \
	status 'SKIPPED reason=experimental_marker_missing'
[ -f "$EFFECT_XML" ] || status 'BLOCKED reason=mounted_audio_effects_xml_missing'
[ -f "$EFFECT_LIB" ] || status 'BLOCKED reason=mounted_lightningdsp_lib_missing'
grep -qi "$LDSP_UUID" "$EFFECT_XML" || \
	status 'BLOCKED reason=mounted_xml_missing_lightningdsp'
grep -qi "$XML_LIB_ANCHOR" "$EFFECT_XML" || \
	status 'BLOCKED reason=mounted_xml_missing_xml_lib_anchor'
grep -qi "$XML_UUID_ANCHOR" "$EFFECT_XML" || \
	status 'BLOCKED reason=mounted_xml_missing_xml_uuid_anchor'

if ! "$LINKER_BIN" --list "$EFFECT_LIB" >"$LOGDIR/audio-reload-linker.txt" 2>&1; then
	status 'BLOCKED reason=mounted_lib_linker_failed'
fi

boot_id=$(cat "$BOOT_ID_FILE" 2>/dev/null || printf unknown)
if ! service_found "$DEFAULT_FACTORY"; then
	status 'BLOCKED reason=default_factory_binder_missing'
fi
before_hal=$(hal_pid)
alive "$before_hal" || status 'BLOCKED reason=audio_hal_pid_missing_before_restart'

if contains_ldsp; then
	printf '%s\n%s\n' "$boot_id" "$before_hal" >"$BOOT_GUARD"
	status 'READY reason=target_already_loaded restart=not_needed'
fi

if [ -f "$BOOT_GUARD" ]; then
	guard_boot_id=$(sed -n '1p' "$BOOT_GUARD")
	guard_hal_pid=$(sed -n '2p' "$BOOT_GUARD")
	# A one-line guard is from the previous boot-only format. Permit one
	# migration attempt; the current HAL PID is written before the restart.
	if [ "$guard_boot_id" = "$boot_id" ] &&
		[ -n "$guard_hal_pid" ] && [ "$guard_hal_pid" = "$before_hal" ]; then
		status 'BLOCKED reason=reload_already_attempted_for_hal_instance'
	fi
fi

"$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>/dev/null | grep -qi "$DUMP_STOCK_UUID_ANCHOR" || \
	status 'BLOCKED reason=default_factory_missing_stock_anchor_before_restart'
has_all_stock_descriptors || \
	status 'BLOCKED reason=default_factory_stock_descriptor_set_changed_before_restart'
before_effect_count=$(factory_effect_count)
[ "$before_effect_count" = "$EXPECTED_STOCK_EFFECT_COUNT" ] || \
	status 'BLOCKED reason=default_factory_stock_effect_count_changed_before_restart'

before_audio=$("$PIDOF_BIN" audioserver 2>/dev/null | awk '{print $1}')
before_pixaml=''
pixaml_state=not_active
if service_found "$AML_FACTORY"; then
	candidate=$("$PIDOF_BIN" -s "$PIXAML_PROCESS" 2>/dev/null)
	if alive "$candidate"; then
		before_pixaml="$candidate"
		pixaml_state=active
	fi
fi
{
	printf 'boot_id=%s\n' "$boot_id"
	printf 'init_service=%s\n' "$INIT_SERVICE"
	printf 'hal_process=%s\n' "$HAL_PROCESS"
	printf 'before_hal_pid=%s\n' "${before_hal:-missing}"
	printf 'before_audioserver_pid=%s\n' "${before_audio:-missing}"
	printf 'before_pixaml_pid=%s\n' "${before_pixaml:-not_active}"
	"$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>&1 | grep -iE 'Effects \(|james|ldsp|f27317f4|50deaa30|UUID:' | head -120
} >"$DUMP_BEFORE" 2>&1

alive "$before_audio" || status 'BLOCKED reason=audioserver_pid_missing_before_restart'

printf '%s\n%s\n' "$boot_id" "$before_hal" >"$BOOT_GUARD"
"$SETPROP_BIN" ctl.restart "$INIT_SERVICE"

new_hal=''
waited=0
while [ "$waited" -lt 20 ]; do
	if service_found "$DEFAULT_FACTORY"; then
		candidate=$(hal_pid)
		if [ -n "$candidate" ] && [ "$candidate" != "$before_hal" ] && alive "$candidate"; then
			new_hal="$candidate"
			break
		fi
	fi
	waited=$((waited + 1))
	"$SLEEP_BIN" 1
done

[ -n "$new_hal" ] || status 'BLOCKED reason=audio_hal_restart_timeout'
printf '%s\n%s\n' "$boot_id" "$new_hal" >"$BOOT_GUARD"

waited=0
while [ "$waited" -lt 10 ]; do
	contains_ldsp && break
	waited=$((waited + 1))
	"$SLEEP_BIN" 1
done

new_audio=''
waited=0
while [ "$waited" -lt 20 ]; do
	candidate=$("$PIDOF_BIN" audioserver 2>/dev/null | awk '{print $1}')
	if alive "$candidate"; then
		new_audio="$candidate"
		break
	fi
	waited=$((waited + 1))
	"$SLEEP_BIN" 1
done
alive "$new_audio" || status 'BLOCKED reason=audioserver_pid_missing_after_restart'
[ "$new_audio" != "$before_audio" ] || status 'BLOCKED reason=audioserver_pid_did_not_change'
{
	printf 'after_hal_pid=%s\n' "${new_hal:-missing}"
	printf 'after_audioserver_pid=%s\n' "${new_audio:-missing}"
	"$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>&1 | grep -iE 'Effects \(|james|ldsp|f27317f4|50deaa30|UUID:' | head -160
} >"$DUMP_AFTER" 2>&1

contains_ldsp || status 'BLOCKED reason=default_factory_missing_lightningdsp_after_restart'
"$DUMPSYS_BIN" "$DEFAULT_FACTORY" 2>/dev/null | grep -qi "$DUMP_STOCK_UUID_ANCHOR" || \
	status 'BLOCKED reason=default_factory_missing_stock_anchor_after_restart'
has_all_stock_descriptors || \
	status 'BLOCKED reason=default_factory_stock_descriptor_set_changed_after_restart'
after_effect_count=$(factory_effect_count)
[ "$after_effect_count" = "$EXPECTED_EFFECT_COUNT_WITH_LDSP" ] || \
	status 'BLOCKED reason=default_factory_stock_effect_count_changed_after_restart'

# Short stability check: no loop and no fallback restart. Just confirm the
# restarted HAL and audioserver are still alive after two bounded seconds.
"$SLEEP_BIN" 2
alive "$new_hal" || status 'BLOCKED reason=audio_hal_unstable_after_restart'
current_audio=$("$PIDOF_BIN" audioserver 2>/dev/null | awk '{print $1}')
[ "$current_audio" = "$new_audio" ] || status 'BLOCKED reason=audioserver_unstable_after_restart'

if [ -n "$before_pixaml" ]; then
	service_found "$AML_FACTORY" || \
		status 'BLOCKED reason=pixaml_factory_lost_after_audio_restart'
	after_pixaml=$("$PIDOF_BIN" -s "$PIXAML_PROCESS" 2>/dev/null)
	[ "$after_pixaml" = "$before_pixaml" ] && alive "$after_pixaml" || \
		status 'BLOCKED reason=pixaml_process_changed_after_audio_restart'
	pixaml_state=preserved
fi

status "READY reason=target_loaded restart=once service=$INIT_SERVICE before_hal=$before_hal after_hal=$new_hal before_audioserver=$before_audio after_audioserver=$new_audio before_effects=$before_effect_count after_effects=$after_effect_count pixaml=$pixaml_state"
