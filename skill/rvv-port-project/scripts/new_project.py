#!/usr/bin/env python3
"""生成一个 <pkg>-rvv 移植工程骨架（不下载任何源码）。

用法：
    new_project.py media-libs/libvpx
    new_project.py media-libs/libvpx --upstream https://github.com/webmproject/libvpx --sha <40hex>
    new_project.py media-libs/libvpx --dry-run

骨架来自 assets/skeleton/（抽象自 libspeex-rvv）。元数据优先从主仓库的
data/plan.csv 自动带出（--plan 可指定），缺的字段用命令行参数或占位符补。
"""
import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from datetime import date

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKEL = os.path.join(SKILL_DIR, "assets", "skeleton")

ATOM_RE = re.compile(r"^[a-z0-9][a-z0-9+_.-]*/[A-Za-z0-9][A-Za-z0-9+_.-]*$")
PLAN_CANDIDATES = ("data/plan.csv", "../rvv/data/plan.csv",
                   "../../rvv/data/plan.csv", "rvv/data/plan.csv")


def short_name(atom):
    s = atom.split("/")[-1]
    s = re.sub(r"-(compat|bin|compat-.*)$", "", s)
    s = re.sub(r"-\d+(\.\d+)+$", "", s)      # tensorflow-1.14.0
    return s


def repo_name(atom):
    s = short_name(atom)
    # 少见的、会与 shell 名混淆的映射
    fixed = {"libsdl2": "SDL2", "johntheripper": "john", "crypto++": "cryptopp",
             "webrtc-audio-processing": "webrtc-ap", "webrtc-apm": "webrtc-ap",
             "openal": "openal-soft", "openjfx": "openjfx"}
    s = fixed.get(s.lower(), s)
    return f"{s}-rvv"


def find_plan(explicit):
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for c in PLAN_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def plan_row(path, atom):
    if not path:
        return {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("pkg") == atom:
                return r
    return {}


def render(text, subs):
    for k, v in subs.items():
        text = text.replace("{{%s}}" % k, str(v))
    return text


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("atom", help="Gentoo atom，如 media-libs/libvpx")
    ap.add_argument("--dir", default=".", help="生成到哪个父目录（默认当前目录）")
    ap.add_argument("--name", default="", help="仓库名（默认 <short>-rvv）")
    ap.add_argument("--upstream", default="", help="上游 git URL")
    ap.add_argument("--sha", default="", help="上游固定 commit（40 位）")
    ap.add_argument("--tag", default="", help="上游 tag（与 --sha 二选一）")
    ap.add_argument("--license", default="")
    ap.add_argument("--priority", default="", help="P0/P1/P2/P3")
    ap.add_argument("--wave", default="", help="W1..W7")
    ap.add_argument("--difficulty", default="", help="D1..D5")
    ap.add_argument("--path", default="", help="移植路径 A/B/C/D（默认取 plan.csv）")
    ap.add_argument("--validation", default="")
    ap.add_argument("--id", dest="rvv_id", default="")
    ap.add_argument("--plan", default="", help="主仓库 data/plan.csv")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="目标目录已存在时覆盖骨架文件")
    ap.add_argument("--no-git", action="store_true")
    a = ap.parse_args()

    atom = a.atom.strip().rstrip("/-")
    if not ATOM_RE.match(atom):
        sys.exit(f"不是合法的 Gentoo atom：{atom}（应形如 category/name）")

    repo = a.name or repo_name(atom)
    dest = os.path.abspath(os.path.join(a.dir, repo))

    row = plan_row(find_plan(a.plan), atom)
    if not row:
        print(f"提示：plan.csv 里没有 {atom}，按长尾处理（字段用参数/占位符）", file=sys.stderr)

    subs = {
        "PKG": atom,
        "SHORT": short_name(atom),
        "REPO": repo,
        "ID": a.rvv_id or row.get("id", "TBD"),
        "DIFFICULTY": a.difficulty or row.get("difficulty", "D2"),
        "PATH": a.path or row.get("path", "B"),
        "PRIORITY": a.priority or row.get("priority", "P3"),
        "WAVE": a.wave or row.get("wave", "-"),
        "VALIDATION": a.validation or row.get("validation", "待定"),
        "UPSTREAM_URL": a.upstream or (row.get("upstream") or ""),
        "UPSTREAM_SHA": a.sha or (row.get("pin") or ""),
        "UPSTREAM_TAG": a.tag or "",
        "LICENSE": a.license or row.get("license", "待核实"),
        "DATE": date.today().isoformat(),
    }
    if subs["UPSTREAM_URL"] and not subs["UPSTREAM_URL"].startswith("http"):
        subs["UPSTREAM_URL"] = ""   # plan.csv 里的 upstream 是 probe key，不是 URL
    if not subs["UPSTREAM_URL"]:
        print("提示：没有上游 URL。以后填进 project.conf 的 UPSTREAM_URL；"
              "fetch-upstream.sh 在它为空时会拒绝执行（不猜地址）", file=sys.stderr)

    if os.path.exists(dest) and not a.force:
        sys.exit(f"目标已存在：{dest}\n  换 --name，或确认要覆盖时加 --force")

    files = []
    for root, _, names in os.walk(SKEL):
        for n in names:
            src = os.path.join(root, n)
            rel = os.path.relpath(src, SKEL)
            files.append((src, rel))

    if a.dry_run:
        print(f"将生成 {dest}")
        for _, rel in sorted(files):
            print("  " + (rel[:-5] if rel.endswith(".tmpl") else rel))
        return

    os.makedirs(dest, exist_ok=True)
    for src, rel in files:
        out_rel = rel[:-5] if rel.endswith(".tmpl") else rel
        dst = os.path.join(dest, out_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, encoding="utf-8") as f:
            text = f.read()
        with open(dst, "w", encoding="utf-8") as f:
            f.write(render(text, subs))
        if dst.endswith(".sh"):
            os.chmod(dst, 0o755)

    # 空的源码/参照目录用 .gitkeep 占位（baseline 本身不入库）
    for d in ("baseline", "src"):
        os.makedirs(os.path.join(dest, d), exist_ok=True)
    for d in ("test/cases", "benchmark/cases"):
        os.makedirs(os.path.join(dest, d), exist_ok=True)

    if not a.no_git:
        subprocess.run(["git", "init", "-q"], cwd=dest, check=False)
        subprocess.run(["git", "add", "-A"], cwd=dest, check=False)
        name = subprocess.run(["git", "config", "user.name"], cwd=dest,
                              capture_output=True, text=True).stdout.strip()
        mail = subprocess.run(["git", "config", "user.email"], cwd=dest,
                              capture_output=True, text=True).stdout.strip()
        if name and mail:
            subprocess.run(["git", "commit", "-q", "-m",
                            f"scaffold: {atom} RVV port skeleton (G0)"],
                           cwd=dest, check=False)

    print(f"== 已生成 {dest}")
    print(f"   包        : {atom}")
    print(f"   工程      : {repo}")
    print(f"   难度/路径 : {subs['DIFFICULTY']} / {subs['PATH']}")
    print(f"   优先级/波 : {subs['PRIORITY']} / {subs['WAVE']}   验证：{subs['VALIDATION']}")
    print()
    print("下一步：")
    print(f"  cd {dest}")
    print("  ./scripts/fetch-upstream.sh --dry-run   # 先确认 URL/SHA")
    print("  ./scripts/build.sh riscv64 && ./test/run_ab.sh")
    print(f"  # 回主仓库挂子模块：./scripts/add-submodule.sh {atom}")


if __name__ == "__main__":
    main()
