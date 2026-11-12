#!/usr/bin/env bash
# 初始化/更新子模块，或把上游源码拉进某个工程。
#
#   ./scripts/sync.sh libvpx                 # 只 update 该子模块（浅拉）
#   ./scripts/sync.sh --all                  # 全部子模块
#   ./scripts/sync.sh --upstream libvpx      # 让该工程把上游源码拉进 baseline/（显式动作）
#
# --upstream 会调用子工程的 scripts/fetch-upstream.sh，读 project.conf 里的
# UPSTREAM_URL / UPSTREAM_SHA；没有 URL 时直接拒绝，不猜。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

depth=1
all=0
upstream=0
targets=()

while [ $# -gt 0 ]; do
  case "$1" in
    --all) all=1; shift ;;
    --upstream) upstream=1; shift ;;
    --depth) depth=$2; shift 2 ;;
    *) targets+=("$1"); shift ;;
  esac
done

if [ "$all" -eq 1 ]; then
  git submodule update --init --depth "$depth" --recursive
  echo "== 全部子模块已同步"
  exit 0
fi

if [ ${#targets[@]} -eq 0 ]; then
  echo "用法：$0 <short>... | --all [--depth N] | --upstream <short>" >&2
  exit 2
fi

resolve_dir() {
  local t=$1 d
  for d in "projects/$t" "projects/$t-rvv"; do
    if [ -f "$d/project.conf" ] || [ -d "$d/.git" ]; then
      printf '%s\n' "$d"; return 0
    fi
  done
  for d in projects/*; do
    [ -d "$d" ] || continue
    if [ -f "$d/project.conf" ] && grep -q "^PKG=.*/$t\$" "$d/project.conf"; then
      printf '%s\n' "$d"; return 0
    fi
  done
  return 1
}

for t in "${targets[@]}"; do
  if ! dir=$(resolve_dir "$t"); then
    echo "错误：找不到匹配 '$t' 的子模块目录（projects/ 里没有 $t 或 $t-rvv）" >&2
    exit 4
  fi
  if [ "$upstream" -eq 1 ]; then
    if [ ! -x "$dir/scripts/fetch-upstream.sh" ]; then
      echo "错误：$dir 缺少 scripts/fetch-upstream.sh" >&2
      exit 5
    fi
    echo "== 拉取上游源码：$dir"
    ( cd "$dir" && ./scripts/fetch-upstream.sh )
  else
    git submodule update --init --depth "$depth" "$dir"
    echo "== 已同步 $dir"
  fi
done
