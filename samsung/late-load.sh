#!/system/bin/sh
umask 077
MODDIR=${0%/*}
# KernelSU Samsung 2.2 runs this stage BEFORE its metamodule mount.
# Do not mount here: the later manager overlay could hide our binds.
mkdir -p "$MODDIR/logs"
printf 'DEFERRED callback=late-load activation=late_load_service_after_manager_mounts\n' >>"$MODDIR/logs/samsung-callbacks.log"
