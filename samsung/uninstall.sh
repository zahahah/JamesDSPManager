#!/system/bin/sh
# No cross-namespace unmount, reboot, or data cleanup during removal.
# Active mounts retain their work files until the temp-root session is recovered.
exit 0
