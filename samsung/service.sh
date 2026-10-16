#!/system/bin/sh
umask 077
# KernelSU Samsung 2.2 injects these from its current kernel runtime mode.
# Never manufacture them from a persistent marker or another boot's state.
MODDIR=${0%/*}
mkdir -p "$MODDIR/logs"
if [ "${KSU_LATE_LOAD:-0}" = 1 ] && [ "${KSU_RUNTIME_MODE:-}" = late-load ]; then
    export JDSP_SAMSUNG_ENTRYPOINT=service-late-load
    exec "${JDSP_SAMSUNG_SH:-/system/bin/sh}" "$MODDIR/runtime.sh" activate
fi
printf 'SKIPPED callback=service reason=not_explicit_late_load\n' >>"$MODDIR/logs/samsung-callbacks.log"
printf 'SKIPPED reason=not_explicit_late_load restart=not_requested processing=unverified\n' >"$MODDIR/logs/samsung-runtime.status"
