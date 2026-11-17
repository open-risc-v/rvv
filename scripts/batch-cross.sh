#!/bin/bash
# 批量推进：每个包 检出→拉上游→本机交叉基线，结果逐包打一行
cd /home/user/work/rvv || exit 1
for pkg in "$@"; do
  echo "=== $pkg ==="
  git submodule update --init --depth 1 "projects/$pkg" > /tmp/fetch-$pkg.log 2>&1
  git -C "projects/$pkg" checkout -f HEAD >> /tmp/fetch-$pkg.log 2>&1
  (cd "projects/$pkg" && ./scripts/fetch-upstream.sh >> /tmp/fetch-$pkg.log 2>&1)
  MARCH=${MARCH:-rv64gc} EXTRA_CMAKE_ARGS="${EXTRA_CMAKE_ARGS:-}" EXTRA_NATIVE_ARGS="${EXTRA_NATIVE_ARGS:-}" \
    ./scripts/local-cross.sh "$pkg" > /tmp/cross-$pkg.log 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then
    echo "PASS  $pkg  $(tail -1 /tmp/cross-$pkg.log)"
  else
    echo "FAIL  $pkg  rc=$rc  $(tail -2 /tmp/cross-$pkg.log | tr '\n' ' ')"
  fi
done
