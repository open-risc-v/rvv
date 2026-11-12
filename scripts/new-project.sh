#!/usr/bin/env bash
# 新建一个 <pkg>-rvv 移植工程骨架（不下载任何源码）。
#
#   ./scripts/new-project.sh media-libs/libvpx
#   ./scripts/new-project.sh media-libs/libvpx --upstream https://github.com/webmproject/libvpx
#   ./scripts/new-project.sh media-libs/libvpx --dry-run
#
# 生成位置：默认 ~/work/<short>-rvv（与本仓库同级），
# 可用 --dir 覆盖。真正的生成逻辑在 Skill rvv-port-project 里。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)

find_skill() {
  local c
  for c in \
    "${RVV_PORT_SKILL:-}" \
    "$HOME/Library/Application Support/DoubaoWork/Default/.doubaowork/agent_mode/workspace/.user_skills/rvv-port-project" \
    "$HOME/.doubaowork/agent_mode/workspace/.user_skills/rvv-port-project" \
    "$ROOT/.user_skills/rvv-port-project"; do
    if [ -n "$c" ] && [ -f "$c/SKILL.md" ]; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

if ! SKILL_DIR=$(find_skill); then
  cat >&2 <<'EOF'
找不到 Skill rvv-port-project。

请先安装该 Skill（应位于 workspace/.user_skills/rvv-port-project），
或用环境变量指定：
  RVV_PORT_SKILL=/path/to/rvv-port-project ./scripts/new-project.sh <atom>
EOF
  exit 2
fi

args=("$@")
has_dir=0
for a in "$@"; do
  [ "$a" = "--dir" ] && has_dir=1
done
if [ "$has_dir" -eq 0 ]; then
  args+=(--dir "$ROOT/../")
fi

exec python3 "$SKILL_DIR/scripts/new_project.py" "${args[@]}"
