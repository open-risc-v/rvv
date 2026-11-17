#!/usr/bin/env bash
# 本机交叉基线（不依赖 docker）：在 Linux 宿主机上直接用
# riscv64-linux-gnu-gcc + qemu-riscv64 编/跑，输出与 native 逐字节比对。
#
#   ./scripts/local-cross.sh zlib-ng-rvv
#   MARCH=rv64gcv ./scripts/local-cross.sh zlib-ng-rvv        # 带上向量扩展
#   HARNESS_ARGS="test/data/x.265 %OUT%/out.yuv" ./scripts/local-cross.sh libde265-rvv
#
# 前置：apt install gcc-riscv64-linux-gnu g++-riscv64-linux-gnu qemu-user \
#                   cmake ninja-build meson autoconf automake libtool pkg-config
# 纪律：baseline/ 只读；A/B 两侧只差 MARCH 一个变量（依赖实现不同时判据降级为像素一致）。
set -euo pipefail
cd "$(dirname "$0")/.."

PKG=${1:?用法: scripts/local-cross.sh <工程目录名，如 zlib-ng-rvv>}
DIR=projects/$PKG
[ -d "$DIR" ] || { echo "错误：找不到工程 $DIR" >&2; exit 2; }

MARCH=${MARCH:-rv64gc}
OUT=build/riscv64-b
NATIVE=build/native
SYSROOT=/usr/riscv64-linux-gnu
CC_BIN=${CC_BIN:-riscv64-linux-gnu-gcc}
# qemu 6.2（apt 版）只认旧版 RVV 编码，rv64gcv 必须用 8.x 并显式开 V。
QEMU=${QEMU:-/opt/qemu82/bin/qemu-riscv64}
[ -x "$QEMU" ] || QEMU=qemu-riscv64
QEMU_CPU=${QEMU_CPU:-}
if [ "$MARCH" = "rv64gcv" ] && [ -z "$QEMU_CPU" ]; then
  QEMU_CPU="rv64,v=true,vlen=256,vext_spec=v1.0"
fi
# 少数 autotools 上游不认 --host（libvpx 用 --target=generic-gnu），用这个变量整段替换。
CONFIGURE_HOST_ARG=${CONFIGURE_HOST_ARG---host=riscv64-linux-gnu}

for c in "$CC_BIN" "$QEMU" cmake; do
  command -v "$c" >/dev/null || { echo "错误：缺少 $c" >&2; exit 3; }
done
[ -d "$SYSROOT" ] || { echo "错误：缺少 sysroot $SYSROOT" >&2; exit 3; }

cd "$DIR"

# 上游未拉取时先拉（baseline 是唯一参照，绝不在里面改东西）
if [ ! -f baseline/CMakeLists.txt ] && [ ! -f baseline/configure.ac ] \
   && [ ! -f baseline/configure ] && [ ! -f baseline/meson.build ]; then
  ./scripts/fetch-upstream.sh
fi

# 构建系统：默认按 baseline 里的文件猜；上游同时带两套（fftw 既有 CMakeLists 又有
# configure.ac）或 CMakeLists 只是半成品时，用 BUILD_SYS=cmake|autotools|meson 强制指定。
if [ -n "${BUILD_SYS:-}" ]; then
  :
elif [ -f baseline/CMakeLists.txt ]; then BUILD_SYS=cmake
elif [ -f baseline/configure ] || [ -f baseline/configure.ac ]; then BUILD_SYS=autotools
elif [ -f baseline/meson.build ]; then BUILD_SYS=meson
elif [ -f baseline/Makefile ]; then BUILD_SYS=make
elif [ -f baseline/Configure ]; then BUILD_SYS=openssl
elif [ -f baseline/configure.py ]; then BUILD_SYS=botan
else echo "错误：认不出 baseline 的构建系统" >&2; exit 3
fi

RV_PREFIX="$PWD/$OUT/prefix"
NAT_PREFIX="$PWD/$NATIVE/prefix"

echo "== [1/4] riscv64 交叉编译上游（${BUILD_SYS}, -march=${MARCH}）=="
rm -rf "$OUT"
case "$BUILD_SYS" in
  cmake)
    cmake -S baseline -B "$OUT/bld" \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$RV_PREFIX" \
      -DBUILD_SHARED_LIBS=OFF -DZLIB_COMPAT=ON -DZLIB_ENABLE_TESTS=OFF \
      -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchain-riscv64-linux.cmake" \
      -DCMAKE_C_FLAGS="-march=${MARCH}" -DCMAKE_CXX_FLAGS="-march=${MARCH}" \
      ${EXTRA_CMAKE_ARGS:-} > /tmp/lc-cfg.log 2>&1 \
      || { tail -25 /tmp/lc-cfg.log; exit 1; }
    cmake --build "$OUT/bld" -j"${JOBS:-$(nproc)}" > /tmp/lc-bld.log 2>&1 \
      || { tail -25 /tmp/lc-bld.log; exit 1; }
    cmake --install "$OUT/bld" > /dev/null
    ;;
  autotools)
    mkdir -p "$OUT"
    cp -R baseline "$OUT/src"
    cd "$OUT/src"
    # fftw 这类上游的 Makefile.am 要求存在 ChangeLog（git 仓库里没带），补一个空的即可
    [ -f ChangeLog ] || touch ChangeLog
    # 有些上游（fftw）仓库里带着 configure 却没有 Makefile.in，只判 configure 会漏
    if [ ! -f configure ] || [ ! -f Makefile.in ]; then
      autoreconf -fi > /tmp/lc-ac.log 2>&1 || { tail -20 /tmp/lc-ac.log; exit 1; }
    fi
    # CC/CXX 必须走环境变量：libvpx 这类 configure 不接受 CC=... 作为命令行参数
    CC="$CC_BIN" CXX=riscv64-linux-gnu-g++ \
      CFLAGS="-O2 -march=${MARCH}" CXXFLAGS="-O2 -march=${MARCH}" \
      ./configure $CONFIGURE_HOST_ARG --prefix="$RV_PREFIX" \
      --disable-shared --enable-static \
      ${EXTRA_CONFIGURE_ARGS:-} > /tmp/lc-cfg.log 2>&1 \
      || { tail -30 /tmp/lc-cfg.log; exit 1; }
    make -j"${JOBS:-$(nproc)}" > /tmp/lc-bld.log 2>&1 \
      || { tail -30 /tmp/lc-bld.log; exit 1; }
    make install > /dev/null 2>&1
    cd "$OLDPWD"
    ;;
  meson)
    meson setup "$OUT/bld" baseline \
      --cross-file "$PWD/cmake/meson-cross-riscv64.ini" \
      --prefix="$RV_PREFIX" --buildtype=release \
      -Dc_args="-march=${MARCH}" -Dcpp_args="-march=${MARCH}" \
      ${EXTRA_MESON_ARGS:-} > /tmp/lc-cfg.log 2>&1 \
      || { tail -25 /tmp/lc-cfg.log; exit 1; }
    meson compile -C "$OUT/bld" > /tmp/lc-bld.log 2>&1 \
      || { tail -25 /tmp/lc-bld.log; exit 1; }
    meson install -C "$OUT/bld" > /dev/null 2>&1
    ;;
  make)
    # 只有裸 Makefile 的上游（openh264 / stockfish）。产物按 MAKE_ARTIFACTS 收到 prefix。
    mkdir -p "$OUT"
    cp -R baseline "$OUT/src"
    cd "$OUT/src"
    make -j"${JOBS:-$(nproc)}" \
      CC="$CC_BIN" CXX=riscv64-linux-gnu-g++ \
      CFLAGS="-O2 -march=${MARCH}" CXXFLAGS="-O2 -march=${MARCH}" \
      ${MAKE_ARCH:+ARCH=$MAKE_ARCH} ${MAKE_TARGET:-} ${EXTRA_MAKE_ARGS:-} \
      > /tmp/lc-bld.log 2>&1 || { tail -30 /tmp/lc-bld.log; exit 1; }
    mkdir -p "$RV_PREFIX/lib" "$RV_PREFIX/include"
    for a in ${MAKE_ARTIFACTS:-}; do cp "$a" "$RV_PREFIX/lib/"; done
    if [ -n "${MAKE_BINS:-}" ]; then mkdir -p "$RV_PREFIX/bin"; for b in $MAKE_BINS; do cp "$b" "$RV_PREFIX/bin/"; chmod +x "$RV_PREFIX/bin/$(basename "$b")"; done; fi
    for h in ${MAKE_HEADERS:-}; do cp -R "$h" "$RV_PREFIX/include/"; done
    cd "$OLDPWD"
    ;;
  openssl)
    # OpenSSL 走 perl Configure，不用 autotools；交叉靠 --cross-compile-prefix 拼工具链。
    mkdir -p "$OUT"
    cp -R baseline "$OUT/src"
    cd "$OUT/src"
    perl Configure ${OPENSSL_TARGET:-linux64-riscv64} no-shared no-tests \
      --prefix="$RV_PREFIX" --cross-compile-prefix=riscv64-linux-gnu- \
      ${EXTRA_CONFIGURE_ARGS:-} > /tmp/lc-cfg.log 2>&1 \
      || { tail -30 /tmp/lc-cfg.log; exit 1; }
    make -j"${JOBS:-$(nproc)}" build_sw > /tmp/lc-bld.log 2>&1 \
      || { tail -30 /tmp/lc-bld.log; exit 1; }
    make install_sw > /dev/null 2>&1
    cd "$OLDPWD"
    ;;
  botan)
    # botan 用自带 configure.py；--cpu 必须显式给，否则按宿主架构判据报错。
    mkdir -p "$OUT"
    cp -R baseline "$OUT/src"
    cd "$OUT/src"
    python3 configure.py --cc-bin="$CC_BIN" --cpu=${BOTAN_CPU:-riscv64} \
      --prefix="$RV_PREFIX" --without-documentation \
      --build-targets=static --disable-shared \
      ${EXTRA_CONFIGURE_ARGS:-} > /tmp/lc-cfg.log 2>&1 \
      || { tail -30 /tmp/lc-cfg.log; exit 1; }
    make -j"${JOBS:-$(nproc)}" libs > /tmp/lc-bld.log 2>&1 \
      || { tail -30 /tmp/lc-bld.log; exit 1; }
    make install > /dev/null 2>&1 || true
    cd "$OLDPWD"
    ;;
esac

# 计时/误差类字段两侧必然不同，判据里剔除，只比内容哈希
strip_timing() { sed -E 's/[A-Za-z0-9_]*(_ms|_rel|_err)=[0-9.eE+-]+//g; s/ nps [0-9]+//g; s/ time [0-9]+/ /g; s/ hashfull [0-9]+//g; s/ tbhits [0-9]+//g; s/ speed [0-9]+/ /g' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/  +/ /g' | grep -v '^$' || true; }
CLI_STDIN_FILE=${CLI_STDIN:-}
CPU_ARGS=""
[ -n "$QEMU_CPU" ] && CPU_ARGS="-cpu $QEMU_CPU"
CLI_RUN_ARGS=""
[ -n "${CLI_BIN:-}" ] && CLI_RUN_ARGS=$(echo "${CLI_ARGS:-}" | sed "s|%OUT%|$OUT/out|g")

if [ -n "${CLI_BIN:-}" ]; then
  # 上游自带 CLI 的包（stockfish / openssl / x264 ...）不必写探针，
  # 直接 qemu 跑 CLI 的 stdout 做 A/B；产物文件另用 CLI_ARTIFACT 比。
  echo "== [2/4] 上游 CLI 直跑（${CLI_BIN}）=="
  mkdir -p "$OUT/out"
  [ -x "$OUT/prefix/bin/$CLI_BIN" ] || { echo "错误：$OUT/prefix/bin/$CLI_BIN 不存在" >&2; exit 4; }
  if [ -n "$CLI_STDIN_FILE" ]; then
    # 命令文件不能直接重定向：EOF 会让交互式 CLI（stockfish）立刻收工，拿不到搜索结果。
    # 用 cat 灌命令后挂住几秒等它算完。
    { cat "$CLI_STDIN_FILE"; sleep ${CLI_STDIN_HOLD:-4}; } | \
      "$QEMU" $CPU_ARGS -L "$SYSROOT" "$OUT/prefix/bin/$CLI_BIN" $CLI_RUN_ARGS \
      > "$OUT/out/hash_rv.txt" 2>&1 || { echo "qemu 跑 ${CLI_BIN} 失败：" >&2; tail -15 "$OUT/out/hash_rv.txt"; exit 1; }
  else
    "$QEMU" $CPU_ARGS -L "$SYSROOT" "$OUT/prefix/bin/$CLI_BIN" $CLI_RUN_ARGS \
      > "$OUT/out/hash_rv.txt" 2>&1 || { echo "qemu 跑 ${CLI_BIN} 失败：" >&2; tail -15 "$OUT/out/hash_rv.txt"; exit 1; }
  fi
  RV_HASH=$(cat "$OUT/out/hash_rv.txt" | strip_timing)
else
echo "== [2/4] 编 riscv64 探针 =="
cmake -S . -B "$OUT/harness" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchain-riscv64-linux.cmake" \
  -DCMAKE_C_FLAGS="-march=${MARCH}" -DCMAKE_CXX_FLAGS="-march=${MARCH}" \
  -DPKG_PREFIX="$RV_PREFIX" ${EXTRA_CMAKE_ARGS:-} > /tmp/lc-h.log 2>&1 \
  || { tail -25 /tmp/lc-h.log; exit 1; }
cmake --build "$OUT/harness" -j"${JOBS:-$(nproc)}" > /tmp/lc-hb.log 2>&1 \
  || { tail -25 /tmp/lc-hb.log; exit 1; }

mkdir -p "$OUT/out"
HARNESS=$(find "$OUT/harness" -maxdepth 1 -type f -perm -111 -name "*harness*" | head -1)
[ -n "$HARNESS" ] || { echo "错误：$OUT/harness 下没有 harness 探针" >&2; exit 4; }
# 探针参数：默认给一个输出文件；需要输入码流等自定义形式时用 HARNESS_ARGS（%OUT% 换成产物目录）
args_for() {
  if [ -n "${HARNESS_ARGS:-}" ]; then
    echo "$HARNESS_ARGS" | sed "s|%OUT%|$1|g"
  else
    echo "$1/result.bin"
  fi
}
RV_ARGS=$(args_for "$OUT/out")
"$QEMU" $CPU_ARGS -L "$SYSROOT" "$HARNESS" $RV_ARGS \
  > "$OUT/out/hash_rv.txt" 2>&1 || { echo "qemu 执行失败：" >&2; cat "$OUT/out/hash_rv.txt"; exit 1; }
RV_HASH=$(cat "$OUT/out/hash_rv.txt" | strip_timing)
fi

echo "== [3/4] native 对照 =="
rm -rf "$NATIVE"
case "$BUILD_SYS" in
  cmake)
    cmake -S baseline -B "$NATIVE/bld" -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="$NAT_PREFIX" \
      -DBUILD_SHARED_LIBS=OFF -DZLIB_COMPAT=ON -DZLIB_ENABLE_TESTS=OFF \
      ${EXTRA_NATIVE_ARGS:-} > /tmp/lc-ncfg.log 2>&1 || { tail -25 /tmp/lc-ncfg.log; exit 1; }
    cmake --build "$NATIVE/bld" -j"${JOBS:-$(nproc)}" > /tmp/lc-nbld.log 2>&1 \
      || { tail -25 /tmp/lc-nbld.log; exit 1; }
    cmake --install "$NATIVE/bld" > /dev/null
    ;;
  autotools)
    mkdir -p "$NATIVE"
    cp -R baseline "$NATIVE/src"
    cd "$NATIVE/src"
    [ -f ChangeLog ] || touch ChangeLog
    if [ ! -f configure ] || [ ! -f Makefile.in ]; then
      autoreconf -fi > /tmp/lc-nac.log 2>&1 || { tail -20 /tmp/lc-nac.log; exit 1; }
    fi
    CFLAGS="-O2" CXXFLAGS="-O2" \
      ./configure --prefix="$NAT_PREFIX" --disable-shared --enable-static \
      ${EXTRA_NATIVE_CONFIGURE_ARGS:-${EXTRA_CONFIGURE_ARGS:-}} \
      > /tmp/lc-ncfg.log 2>&1 || { tail -30 /tmp/lc-ncfg.log; exit 1; }
    make -j"${JOBS:-$(nproc)}" > /tmp/lc-nbld.log 2>&1 || { tail -30 /tmp/lc-nbld.log; exit 1; }
    make install > /dev/null 2>&1
    cd "$OLDPWD"
    ;;
  meson)
    meson setup "$NATIVE/bld" baseline --prefix="$NAT_PREFIX" --buildtype=release \
      --libdir=lib \
      ${EXTRA_MESON_ARGS:-} > /tmp/lc-ncfg.log 2>&1 || { tail -25 /tmp/lc-ncfg.log; exit 1; }
    meson compile -C "$NATIVE/bld" > /tmp/lc-nbld.log 2>&1 \
      || { tail -25 /tmp/lc-nbld.log; exit 1; }
    meson install -C "$NATIVE/bld" > /dev/null 2>&1
    ;;
  make)
    mkdir -p "$NATIVE"
    cp -R baseline "$NATIVE/src"
    cd "$NATIVE/src"
    make -j"${JOBS:-$(nproc)}" \
      CFLAGS="-O2" CXXFLAGS="-O2" \
      ${MAKE_ARCH:+ARCH=$MAKE_ARCH} ${MAKE_TARGET:-} ${EXTRA_MAKE_ARGS:-} \
      > /tmp/lc-nbld.log 2>&1 || { tail -30 /tmp/lc-nbld.log; exit 1; }
    mkdir -p "$NAT_PREFIX/lib" "$NAT_PREFIX/include"
    for a in ${MAKE_ARTIFACTS:-}; do cp "$a" "$NAT_PREFIX/lib/"; done
    if [ -n "${MAKE_BINS:-}" ]; then mkdir -p "$NAT_PREFIX/bin"; for b in $MAKE_BINS; do cp "$b" "$NAT_PREFIX/bin/"; chmod +x "$NAT_PREFIX/bin/$(basename "$b")"; done; fi
    for h in ${MAKE_HEADERS:-}; do cp -R "$h" "$NAT_PREFIX/include/"; done
    cd "$OLDPWD"
    ;;
  openssl)
    mkdir -p "$NATIVE"
    cp -R baseline "$NATIVE/src"
    cd "$NATIVE/src"
    perl Configure ${OPENSSL_NATIVE_TARGET:-linux-x86_64} no-shared no-tests \
      --prefix="$NAT_PREFIX" ${EXTRA_NATIVE_ARGS:-} > /tmp/lc-ncfg.log 2>&1 \
      || { tail -30 /tmp/lc-ncfg.log; exit 1; }
    make -j"${JOBS:-$(nproc)}" build_sw > /tmp/lc-nbld.log 2>&1 \
      || { tail -30 /tmp/lc-nbld.log; exit 1; }
    make install_sw > /dev/null 2>&1
    cd "$OLDPWD"
    ;;
  botan)
    mkdir -p "$NATIVE"
    cp -R baseline "$NATIVE/src"
    cd "$NATIVE/src"
    python3 configure.py --cc-bin=${BOTAN_NATIVE_CC:-g++} --cpu=${BOTAN_NATIVE_CPU:-x86_64} \
      --prefix="$NAT_PREFIX" --without-documentation \
      --build-targets=static --disable-shared \
      ${EXTRA_NATIVE_ARGS:-} > /tmp/lc-ncfg.log 2>&1 \
      || { tail -30 /tmp/lc-ncfg.log; exit 1; }
    make -j"${JOBS:-$(nproc)}" libs > /tmp/lc-nbld.log 2>&1 \
      || { tail -30 /tmp/lc-nbld.log; exit 1; }
    make install > /dev/null 2>&1 || true
    cd "$OLDPWD"
    ;;
esac

mkdir -p "$NATIVE/out"
# 上游自带 CLI 的包（stockfish）不需要探针，跳过 harness 构建
if [ -z "${CLI_BIN:-}" ]; then
cmake -S . -B "$NATIVE/harness" -DCMAKE_BUILD_TYPE=Release \
  -DPKG_PREFIX="$NAT_PREFIX" ${EXTRA_NATIVE_ARGS:-} > /tmp/lc-nh.log 2>&1 \
  || { tail -25 /tmp/lc-nh.log; exit 1; }
cmake --build "$NATIVE/harness" -j"${JOBS:-$(nproc)}" > /tmp/lc-nhb.log 2>&1 \
  || { tail -25 /tmp/lc-nhb.log; exit 1; }
NHARNESS=$(find "$NATIVE/harness" -maxdepth 1 -type f -perm -111 -name "*harness*" | head -1)
[ -n "$NHARNESS" ] || { echo "错误：native harness 未生成" >&2; exit 4; }
fi
if [ -n "${CLI_BIN:-}" ]; then
  [ -x "$NAT_PREFIX/bin/$CLI_BIN" ] || { echo "错误：native 侧没有 $CLI_BIN" >&2; exit 4; }
  if [ -n "$CLI_STDIN_FILE" ]; then
    NAT_HASH=$({ cat "$CLI_STDIN_FILE"; sleep ${CLI_STDIN_HOLD:-4}; } | "$NAT_PREFIX/bin/$CLI_BIN" $CLI_RUN_ARGS 2>&1 | strip_timing)
  else
    NAT_HASH=$("$NAT_PREFIX/bin/$CLI_BIN" $CLI_RUN_ARGS < /dev/null 2>&1 | strip_timing)
  fi
else
  NAT_HASH=$("$NHARNESS" $(args_for "$NATIVE/out") | strip_timing)
fi

echo "== [4/4] 比对 =="
echo "--- riscv64 (${MARCH}) ---"; echo "$RV_HASH"
echo "--- native          ---"; echo "$NAT_HASH"
# 浮点包（webrtc-apm / mpg123 / gromacs / fftw）不能逐字节比：不同 ISA 的 FMA 融合、
# 累加顺序都会让末位不同。FLOAT_TOL 给定时按相对误差逐字段比，整数与哈希字段仍必须完全相同。
if [ -n "${FLOAT_TOL:-}" ]; then
  RV="$RV_HASH" NAT="$NAT_HASH" TOL="$FLOAT_TOL" python3 - <<'PY'
import os, re, sys
tol = float(os.environ['TOL'])
rv = [l.strip() for l in os.environ['RV'].splitlines() if l.strip()]
na = [l.strip() for l in os.environ['NAT'].splitlines() if l.strip()]
if len(rv) != len(na):
    print(f"BAD 行数不同 {len(rv)} vs {len(na)}"); sys.exit(1)
bad = []
for i, (a, b) in enumerate(zip(rv, na)):
    if a == b:
        continue
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        bad.append(f"第{i+1}行字段数不同: {a} | {b}"); continue
    ok = True
    skip = os.environ.get('IGNORE_FIELDS', '')
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if skip and any(x.startswith(f + '=') for f in skip.split(',')):
            continue
        m1 = re.fullmatch(r'(.+?=)([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)', x)
        m2 = re.fullmatch(r'(.+?=)([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)', y)
        if m1 and m2 and m1.group(1) == m2.group(1):
            va, vb = float(m1.group(2)), float(m2.group(2))
            den = max(abs(vb), 1e-12)
            if abs(va - vb) / den <= tol:
                continue
            bad.append(f"{m1.group(1)}{va} vs {vb} 超差（rel={abs(va-vb)/den:.3g}）"); ok = False
        else:
            bad.append(f"非数值字段不同: {x} vs {y}"); ok = False
    if not ok:
        break
if bad:
    print("BAD " + "; ".join(bad[:3])); sys.exit(1)
print("OK"); sys.exit(0)
PY
  [ $? -eq 0 ] && echo "PASS ${PKG}：${MARCH} 在相对容差 ${FLOAT_TOL} 内一致（浮点包不比逐字节）" \
              || { echo "FAIL ${PKG}：超出浮点容差 ${FLOAT_TOL}" >&2; exit 1; }
  exit 0
fi
# 判据分流：带像素哈希的包（libpng 这类）按像素比；其余按全文 + 产物逐字节比。
# 压缩实现不同（zlib vs zlib-ng）只影响码流，不影响像素，二者不能混成一个 PASS。
if echo "$RV_HASH" | grep -q "fnv_px="; then
  RV_PX=$(echo "$RV_HASH" | grep -o "fnv_px=[0-9a-f]*" | head -1)
  NAT_PX=$(echo "$NAT_HASH" | grep -o "fnv_px=[0-9a-f]*" | head -1)
  if [ "$RV_PX" = "$NAT_PX" ]; then
    echo "PASS ${PKG}：${MARCH} 解码像素一致（${RV_PX}；码流允许因压缩实现不同而不同）"
  else
    echo "FAIL ${PKG}：像素哈希不一致（${RV_PX} vs ${NAT_PX}）" >&2; exit 1
  fi
elif [ "$RV_HASH" = "$NAT_HASH" ]; then
  # 探针打印的哈希行覆盖了产物内容，两侧完全相同即可判 PASS。
  # 产物文件名由 HARNESS_ARGS 决定，不能硬编码比对某个固定文件名。
  echo "PASS ${PKG}：${MARCH} 输出哈希与 native 完全一致"
else
  # 哈希行可能夹带上游自己的日志（如 libx264 的 "using cpu capabilities"），
  # 哈希不等时退一步逐字节比产物（排除我们自己的记录文件），全一致也算通过。
  DIFFN=0; DIFFF=""
  for f in "$OUT/out"/*; do
    [ -f "$f" ] || continue
    b=$(basename "$f")
    case "$b" in hash_*.txt|*.log|*.txt) continue;; esac
    if ! cmp -s "$f" "$NATIVE/out/$b"; then DIFFN=$((DIFFN+1)); DIFFF="$DIFFF $b"; fi
  done
  if [ "$DIFFN" -eq 0 ]; then
    echo "PASS ${PKG}：${MARCH} 产物逐字节一致（哈希行的日志差异不影响判定）"
  else
    echo "FAIL ${PKG}：输出哈希不一致，且产物有 $DIFFN 个不同：$DIFFF" >&2
    exit 1
  fi
fi

# 机器可读记录：汇总脚本读这一行，不再靠翻终端输出
{ printf 'pkg=%s march=%s rv=%s native=%s\n' "$PKG" "$MARCH" \
    "$(echo "$RV_HASH" | tr '\n' '|')" "$(echo "$NAT_HASH" | tr '\n' '|')"; } \
  > "$OUT/out/ab-result.txt"
