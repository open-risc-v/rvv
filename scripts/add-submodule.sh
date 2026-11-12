#!/usr/bin/env bash
# 把已生成的 <short>-rvv 工程挂成 projects/ 下的 git submodule。
#
#   ./scripts/add-submodule.sh media-libs/libvpx
#   ./scripts/add-submodule.sh media-libs/libvpx https://github.com/you/libvpx-rvv.git
#   ./scripts/add-submodule.sh media-libs/libsdl2 --name SDL2-rvv
#
# 默认 URL 用相对路径 ../<repo>，指向同级的本地工程；镜像到远端后再统一改。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ $# -lt 1 ]; then
  echo "用法：$0 <gentoo-atom> [url] [--name <repo>]" >&2
  exit 2
fi

atom=$1; shift
url=""
name=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) name=$2; shift 2 ;;
    *) url=$1; shift ;;
  esac
done

short=${atom##*/}
short=${short%-compat}
repo=${name:-${short}-rvv}

if [ ! -d .git ]; then
  echo "错误：$ROOT 还不是 git 仓库，先执行 git init && git add -A && git commit" >&2
  exit 3
fi

if [ -f .gitmodules ] && grep -q "path = projects/$repo" .gitmodules; then
  echo "已注册：projects/${repo}（如需改 URL：git submodule set-url ...）" >&2
  exit 0
fi

if [ -z "$url" ]; then
  url="../$repo"
  if [ ! -d "$ROOT/../$repo/.git" ]; then
    echo "错误：找不到本地工程 $ROOT/../${repo}，先跑 ./scripts/new-project.sh $atom" >&2
    exit 4
  fi
fi

mkdir -p projects
# 本地同级工程用相对路径（../<repo>）时，git 默认禁止 file 传输；
# 只对本地路径放开，远端 https 地址不加这个开关。
case "$url" in
  ../*|/*|file://*) git -c protocol.file.allow=always submodule add -f "$url" "projects/$repo" ;;
  *)                git submodule add "$url" "projects/$repo" ;;
esac
git submodule absorbgitdirs "projects/$repo" 2>/dev/null || true

echo "== 已挂载 projects/${repo}（${url}）"
echo "下一步："
echo "  git add .gitmodules projects/$repo && git commit -m 'submodule: add $repo'"
echo "  ./scripts/sync.sh $short --depth 1"
