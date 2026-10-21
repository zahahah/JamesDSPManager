#!/system/bin/sh
# One capability-driven AIDL late-load path. Model names are not authorization.
MODPATH=${0%/*}
case "${1:-}" in
    --auto-once|--retry|--check) exec sh "$MODPATH/aidl-audio-recovery.sh" "$1" ;;
    *) echo 'Usage: audio-hal-recovery.sh --auto-once|--retry|--check' >&2; exit 2 ;;
esac
