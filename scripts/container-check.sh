#!/usr/bin/env bash
# 在 Linux 容器里对一个 <pkg>-rvv 工程做交叉构建 + 功能自检。
#
# 为什么要这个脚本：骨架的 scripts/build.sh 是"宿主直编"（在 Linux 上直接 cmake），
# 在 macOS 上必然失败于 CMAKE_MAKE_PROGRAM / CMAKE_C_COMPILER 未设置。
# 本脚本统一走 rvv-cross 镜像，宿主上不编译任何东西。
#
#   ./scripts/container-check.sh ../speexdsp-rvv
#   IMAGE=rvv-cross:3 ./scripts/container-check.sh ../nettle-rvv
#
# 容器内产出 build/riscv64-docker/，只用于功能验证；性能数字一律真机取。
set -euo pipefail

PROJ=${1:?用法: container-check.sh <工程目录>}
IMAGE=${IMAGE:-rvv-cross:2}
PROJ=$(cd "$PROJ" && pwd)

docker run --rm -v "${PROJ}":/work -w /work "${IMAGE}" bash -lc '
set -e
SYSROOT=/usr/riscv64-linux-gnu
cmake -S . -B build/riscv64-docker -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-riscv64-linux.cmake \
      -D_USE_RVV=ON -DRVV_MARCH=rv64gcv > /tmp/cfg.log 2>&1 \
  || { echo "CONFIGURE FAIL"; tail -25 /tmp/cfg.log; exit 1; }
cmake --build build/riscv64-docker -j"$(nproc)" > /tmp/bld.log 2>&1 \
  || { echo "BUILD FAIL"; tail -30 /tmp/bld.log; exit 1; }
echo "BUILD OK: $(ls build/riscv64-docker | tr "\n" " ")"

echo "--- cpu_probe ---"
qemu-riscv64 -L "$SYSROOT" build/riscv64-docker/cpu_probe || true

echo "--- diff_kernels ---"
qemu-riscv64 -L "$SYSROOT" build/riscv64-docker/diff_kernels

echo "--- run_ab ---"
CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-riscv64-linux.cmake" \
RUNNER="qemu-riscv64 -L $SYSROOT" bash test/run_ab.sh
'
