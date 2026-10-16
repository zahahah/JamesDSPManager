#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${1:-${JDSP_EAGER_WRAPPER_OUT:-$ROOT/tools/libjamesdsp_eager_pinwrap.so}}
BUILD=${TMPDIR:-/tmp}/jdsp-aidl-eager-pinwrap.$$
CC=${CC:-clang}
STRIP=${STRIP:-llvm-strip}
TARGET=${TARGET:-aarch64-linux-android35}

mkdir -p "$BUILD" "$(dirname -- "$OUT")"
trap 'rm -rf "$BUILD"' EXIT HUP INT TERM

COMMON="--target=$TARGET -fPIC -ffreestanding -fvisibility=hidden -Os"
$CC --target="$TARGET" -fPIC -ffreestanding -Os \
    -c "$ROOT/native/jdsp_android_stubs.c" -o "$BUILD/libc-stubs.o"
$CC --target="$TARGET" -fuse-ld=lld -shared -nostdlib \
    -Wl,-soname,libc.so -Wl,--build-id=sha1 \
    "$BUILD/libc-stubs.o" -o "$BUILD/libc.so"
$CC --target="$TARGET" -fPIC -ffreestanding -Os -DBUILD_LIBLOG \
    -c "$ROOT/native/jdsp_android_stubs.c" -o "$BUILD/liblog-stubs.o"
$CC --target="$TARGET" -fuse-ld=lld -shared -nostdlib \
    -Wl,-soname,liblog.so -Wl,--build-id=sha1 \
    "$BUILD/liblog-stubs.o" -o "$BUILD/liblog.so"

$CC $COMMON -ffunction-sections -fdata-sections -DJDSP_EAGER_PRELOAD_REAL \
    -c "$ROOT/native/jdsp_aidl_pinwrap.c" -o "$BUILD/pinwrap.o"
$CC --target="$TARGET" -fuse-ld=lld -shared -nostdlib \
    -Wl,-soname,libjamesdsp.so -Wl,--build-id=sha1 -Wl,--gc-sections \
    -Wl,--no-undefined "$BUILD/pinwrap.o" -L"$BUILD" \
    -Wl,--no-as-needed -lc -llog -o "$OUT"
if command -v "$STRIP" >/dev/null 2>&1; then
    "$STRIP" --strip-unneeded "$OUT"
else
    echo "warning: $STRIP unavailable; leaving the valid wrapper unstripped" >&2
fi
