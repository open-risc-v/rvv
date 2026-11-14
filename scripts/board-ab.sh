#!/usr/bin/env bash
# 真机 A/B：把某个工程的 G3 产物（A=RVV / B=标量）送到板上跑，取性能数字。
# 用法：./scripts/board-ab.sh pixman <board-host> [bench 参数]
# 前提：板上能跑静态 riscv64 二进制，A 侧 CPU 必须支持 RVV 1.0（vlen>=128）。
set -euo pipefail
PKG=${1:?包名，例如 pixman}
HOST=${2:?板子的 ssh 主机名或 IP}
shift 2 || true
ARGS=${*:-5}
P=~/work/${PKG}-rvv
[ -d "$P/build/rvv-k/on" ] || { echo "缺 $P/build/rvv-k，先跑 $P/scripts/rvv-kernel-ab.sh" >&2; exit 2; }

echo "== 板上环境"
ssh "$HOST" 'uname -a; grep -m1 isa /proc/cpuinfo || true; nproc; lscpu | grep -i "model name\|CPU max" || true'

rm -rf "${P}/build/board" && mkdir -p "${P}/build/board"
tar -C "$P/build/rvv-k" -cf - on off | tar -C "${P}/build/board" -xf -
scp -q -r "${P}/build/board/on" "${P}/build/board/off" "$HOST:/tmp/${PKG}-ab/"

echo "== 板上跑 A（RVV）"
ssh "$HOST" "cd /tmp/${PKG}-ab/on && ./bench_over ${ARGS}" | tee "${P}/build/board/A.txt"
echo "== 板上跑 B（标量）"
ssh "$HOST" "cd /tmp/${PKG}-ab/off && ./bench_over ${ARGS}" | tee "${P}/build/board/B.txt"
echo "== 功能复核（板上跑探针，与 native 哈希比对）"
ssh "$HOST" "cd /tmp/${PKG}-ab/on && ./harness/pixman_harness 2>/dev/null || true"
awk '/ns_per_px=/{for(i=1;i<=NF;i++) if($i ~ /ns_per_px=/){split($i,a,"=");A=a[2]}}' "${P}/build/board/A.txt" > /tmp/a.$$
awk '/ns_per_px=/{for(i=1;i<=NF;i++) if($i ~ /ns_per_px=/){split($i,a,"=");B=a[2]}}' "${P}/build/board/B.txt" > /tmp/b.$$
A=$(cat /tmp/a.$$); B=$(cat /tmp/b.$$); rm -f /tmp/a.$$ /tmp/b.$$
[ -n "$A" ] && [ -n "$B" ] && awk -v a="$A" -v b="$B" 'BEGIN{printf "== A/B 比：RVV %.3f ns/px，标量 %.3f ns/px，加速比 %.2fx\n", a, b, b/a}'
