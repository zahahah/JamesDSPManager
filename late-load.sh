#!/system/bin/sh

MODDIR=${0%/*}
LOGDIR="$MODDIR/logs"
STATUS="$LOGDIR/late-load.status"

mkdir -p "$LOGDIR"

# Legacy KernelSU entry point. Delegate to post-fs-data.sh so late-load keeps
# the same pre-Magic-Mount validation and fail-closed behavior.
if [ -x "$MODDIR/post-fs-data.sh" ]; then
	KSU_LATE_LOAD=1 sh "$MODDIR/post-fs-data.sh"
else
	touch "$MODDIR/skip_mount"
	printf 'BLOCKED reason=post_fs_data_missing\n' >"$STATUS"
fi
exit 0
