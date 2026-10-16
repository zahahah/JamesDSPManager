#!/system/bin/sh
umask 077
# Boot callbacks deliberately do not mount, install apps, or restart audio.
MODDIR=${0%/*}
mkdir -p "$MODDIR/logs"
printf 'DEFERRED callback=post-fs-data activation=explicit_late_load_only\n' >>"$MODDIR/logs/samsung-callbacks.log"
