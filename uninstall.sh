# Don't modify anything after this
if [ -f $INFO ]; then
  while read LINE; do
    if [ "$(echo -n $LINE | tail -c 1)" == "~" ]; then
      continue
    elif [ -f "$LINE~" ]; then
      mv -f $LINE~ $LINE
    else
      rm -f $LINE
      while true; do
        LINE=$(dirname $LINE)
        [ "$(ls -A $LINE 2>/dev/null)" ] && break 1 || rm -rf $LINE
      done
    fi
  done < $INFO
  rm -f $INFO
fi
(
until [ "$(getprop sys.boot_completed)" = "1" ]; do
	sleep 1
done
sleep 10
PKG="james.dsp"
APP=$(pm list packages -3 | grep "$PKG")
if [ ! -d "$MODPATH" ]; then
	pm uninstall "$PKG" 2>/dev/null
	sleep 2
	rm -f "$0"
	exit 0
fi
) &
