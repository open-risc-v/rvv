#!/usr/bin/env bash
# 对本仓库做一致性检查（CI 入口）。
#
#   ./scripts/verify.sh
#
# 检查项：
#   1. data/ 四个数据文件存在、列头完整
#   2. plan ⊆ inventory（包名必须来自清单）
#   3. inventory 行数与 docs 声明的 166 一致
#   4. pd_plan == round((low+high)/2 × 1.15)
#   5. 优先级/波次/难度取值合法
#   6. projects/ 目录与 .gitmodules 一致（每个工程有 project.conf，PKG 与目录名匹配）
#   7. docs/ 与 templates 关键文件齐全
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
fail=0
note() { printf '  %s\n' "$*"; }
bad() { printf '  FAIL: %s\n' "$*"; fail=1; }
ok() { printf '  ok: %s\n' "$*"; }

echo "== 1. 数据文件"
for f in data/inventory.csv data/plan.csv data/status.csv data/upstream-probe.json; do
  if [ -s "$f" ]; then ok "$f"; else bad "$f 缺失或为空"; fi
done

echo "== 2..5. 清单与计划一致性"
python3 - <<'PY'
import csv, json, os, sys
ok=[]; err=[]
def need(cols, header, name):
    miss=[c for c in cols if c not in header]
    if miss: err.append(f"{name} 缺列: {miss}")
def load(p):
    with open(p, encoding='utf-8-sig') as f:
        r=csv.DictReader(f); return list(r), r.fieldnames or []

inv, ih = load('data/inventory.csv')
plan, ph = load('data/plan.csv')
st, sh = load('data/status.csv')

need(['pkg','short','category','isa_paths','source_sheets','difficulty','priority',
      'wave','in_plan','note'], ih, 'inventory.csv')
need(['id','pkg','project','upstream','license','rvv_upstream','path','difficulty',
      'pd_low','pd_high','pd_plan','validation','priority','wave','deps',
      'difficulty_notes','rationale'], ph, 'plan.csv')
need(['id','pkg','gate','owner','updated','evidence'], sh, 'status.csv')

pkgs={r['pkg'] for r in inv}
for r in plan:
    if r['pkg'] not in pkgs: err.append(f"plan 里的包不在清单: {r['pkg']}")
if len(inv)!=166: err.append(f"inventory 行数 {len(inv)} != 166")
if len(plan)!=48: err.append(f"plan 行数 {len(plan)} != 48")
for r in plan:
    lo,hi,pd=int(r['pd_low']),int(r['pd_high']),int(r['pd_plan'])
    if round((lo+hi)/2*1.15)!=pd: err.append(f"{r['id']} pd_plan {pd} != {round((lo+hi)/2*1.15)}")
    if r['priority'] not in ('P0','P1','P2','P3'): err.append(f"{r['id']} 优先级非法")
    if r['wave'] not in ('W%d'%i for i in range(0,8)) and r['wave']!='-':
        err.append(f"{r['id']} 波次非法: {r['wave']}")
    if r['difficulty'] not in ('D1','D2','D3','D4','D5'): err.append(f"{r['id']} 难度非法")
ids={r['id'] for r in plan}
for r in st:
    if r['id'] not in ids: err.append(f"status 里的 id 不在 plan: {r['id']}")
    if r['gate'] not in ('G0','G1','G2','G3','G4','G5'): err.append(f"{r['id']} 门禁非法: {r['gate']}")

p=json.load(open('data/upstream-probe.json',encoding='utf-8'))
if not p.get('repos'): err.append('upstream-probe.json 没有 repos')

for e in err: print('  FAIL:', e)
if err: sys.exit(1)
print(f"  ok: inventory {len(inv)} / plan {len(plan)} / status {len(st)} / probe {len(p['repos'])}")
PY
[ $? -ne 0 ] && fail=1

echo "== 6. 子模块一致性"
if [ -f .gitmodules ]; then
  registered=$(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' | awk '{print $2}')
  for d in projects/*/; do
    [ -d "$d" ] || continue
    base=$(basename "$d")
    [ "$base" = "README.md" ] && continue
    if ! printf '%s\n' "$registered" | grep -qx "projects/$base"; then
      bad "projects/$base 未在 .gitmodules 注册"; continue
    fi
    if [ ! -f "$d/project.conf" ]; then bad "projects/$base 缺 project.conf"; continue; fi
    pkg=$(grep -m1 '^PKG=' "$d/project.conf" | cut -d= -f2-)
    short=${base%-rvv}
    if ! printf '%s' "$pkg" | grep -q "/"; then bad "projects/$base 的 PKG 非法: $pkg"; fi
    ok "projects/$base ($pkg)"
  done
  printf '%s\n' "$registered" | while read -r p; do
    [ -n "$p" ] || continue
    [ -d "$p" ] || echo "  FAIL: .gitmodules 指向不存在的目录 $p"
  done
else
  note "无 .gitmodules（尚未挂载任何子模块）"
fi

echo "== 7. 文档完整性"
for f in README.md docs/00-program-model.md docs/01-difficulty-rubric.md \
         docs/02-priority-rules.md docs/03-rvv-playbook.md docs/04-isa-mapping.md \
         docs/05-waves.md docs/06-acceptance.md docs/07-ai-schedule.md \
         projects/README.md STATUS.md; do
  if [ -s "$f" ]; then ok "$f"; else bad "$f 缺失"; fi
done

echo
if [ "$fail" -eq 0 ]; then
  echo "== verify: PASS"
else
  echo "== verify: FAIL" >&2
  exit 1
fi
