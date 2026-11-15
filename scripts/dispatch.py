#!/usr/bin/env python3
"""生成 sub-agent 工作单：一个工程一份，自带元数据、门禁、允许/禁止、验收命令。

派工方只读 workorder，不需要再翻 plan.csv / project.conf；
工作单里的所有路径都是绝对路径（sub-agent 不继承本会话的 skill 目录清单）。

用法：
  python3 scripts/dispatch.py                 # 全部核心 48 项
  python3 scripts/dispatch.py --wave W1       # 只出 W1
  python3 scripts/dispatch.py --ids RVV-002
"""
import argparse
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKDIR = os.path.dirname(ROOT)          # 工程都建在主仓库的兄弟目录
SKILL_DIR = ("~/Library/Application Support/DoubaoWork/Default/"
             ".doubaowork/agent_mode/workspace/.user_skills/rvv-port-project")

WAVE_SCOPE = {
    "W1": "上游已有 RVV（先把参照实现抄明白，增量最小、收益最快）",
    "W2": "解码内核（视频/图像/语音解码 + 音频底座；位精确最严，消费端必经）",
    "W3": "编码与数学底座（x264/HEVC 软解/FFT/Eigen/密码库/存储）",
    "W4": "重编码与安全搜索（x265/tensorflow/hyperscan/TLS 家族）",
    "W5": "集成前置（ffmpeg 把 codec 成果集成起来；node/pcl 硬依赖已就绪）",
    "W6": "平台集成（chromium/opencv/kodi/vlc，消费前五波全部成果）",
}


def conf_of(project):
    p = os.path.join(WORKDIR, project, "project.conf")
    d = {}
    if not os.path.exists(p):
        return d
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def body(r, conf):
    proj = os.path.join(WORKDIR, r["project"])
    gate = conf.get("GATE", "G0")
    sha = conf.get("UPSTREAM_SHA") or "（未固定）"
    url = conf.get("UPSTREAM_URL") or "（未填）"
    return f"""# {r['id']} {r['pkg']} → `{r['project']}`

> 本单由 `scripts/dispatch.py` 生成，是唯一的派工依据。字段冲突时以本单为准。

## 0. 一句话任务

把 `baseline/` 里的上游实现**原样**跑通，逐内核把它改写成 `src/` 下的 RVV 实现，
每个内核都要有**位精确差分 + 成对性能数字**，最后交出 G2/G3/G4 证据包。不改上游语义、不改测试口径。

## 1. 元数据（只读）

| 项 | 值 |
|---|---|
| 包 / 编号 | `{r['pkg']}` / {r['id']} |
| 工程目录 | `{proj}` |
| 上游 | `{url}` @ `{sha}` |
| 难度 / 路径 | {r['difficulty']} / {r['path']} |
| 人日（计划） | {r['pd_plan']}（区间 {r['pd_low']}–{r['pd_high']}） |
| 优先级 / 波次 | {r['priority']} / {r['wave']} —— {WAVE_SCOPE.get(r['wave'], '')} |
| 验证口径 | {r['validation']} |
| 当前门禁 | **{gate}** |
| 上游 RVV 现状 | {r['rvv_upstream']} |
| 已知难点 | {r['difficulty_notes']} |

## 2. 开工前必读（全部绝对路径，按顺序读）

1. `{proj}/README.md` —— 本工程怎么构建、怎么跑 A/B
2. `{proj}/skills/rvv-kernel-loop/SKILL.md` —— **每轮七步**，不许自创流程
3. `{proj}/docs/plan.md` —— 要做什么、不做什么
4. `{ROOT}/docs/03-rvv-playbook.md` —— 四条路径 A/B/C/D 与尾部掩码纪律
5. `{ROOT}/docs/04-isa-mapping.md` —— SSE/NEON → RVV 映射表与七个必踩坑
6. `{SKILL_DIR}/references/adapt-build-system.md` —— 上游 CMake/autotools/meson 三种接法
7. `{SKILL_DIR}/references/gates.md` —— G0→G5 证据要求与"假通过"清单

## 3. 边界（越界即视为返工）

**允许**：在 `{proj}/src/` 下新增 `*/rvv/*_rvv.c`；改 `cmake/upstream.cmake`；改 `test/`、
`benchmark/` 里的用例与登记表；改本工程 `docs/`；在本工程内 `git commit`。

**禁止**：
- 改 `{proj}/baseline/` 任何内容（A/B 的参照，改一次全部作废）；
- 用 `-O3` vs `-O2`、改 CPU 频率、开 `-ffast-math` 制造"加速"（A/B 只许差 `RVV_KERNELS`）；
- 改上游语义（饱和、舍入、尾部处理、对齐要求）来"对齐"结果；
- 猜上游 URL 或 SHA；需要换固定点时停下来报给派工方；
- 跨工程改动、动主仓库 `data/` 与 `docs/`（状态回写由派工方做）；
- 用 qemu 的加速比当性能结论（qemu 只证明功能）。

## 4. 推进顺序（每步都要留下证据）

### G2 baseline 全绿
```bash
cd {proj}
./scripts/build.sh riscv64            # 缺交叉工具链用 ./scripts/docker-cross.sh
./test/run_ab.sh                      # 现在只有 00_framework，先让它 PASS
# 接上游构建：填 cmake/upstream.cmake，把 A/B 两侧都用的二进制编出来
cp test/cases/00_framework.sh test/cases/01_{conf.get('SHORT','pkg')}_decode.sh   # 改成调上游程序，产出确定性文件
./test/run_ab.sh                      # A/B 逐字节一致 + 产出数 > 0，才算 G2
```

### G3 内核推进（每轮七步，一轮一个内核）
```bash
./build/riscv64/diff_kernels          # 差分：小尺寸/非 2 的幂/VL 边界/多种子/越界哨兵
./benchmark/pair_bench.sh             # A/B 交替 ≥5 次取中位
./test/run_ab.sh                      # 全 PASS 才继续
```

### G4 收敛
- 热点内核覆盖 ≥80%（占比 <5% 的写进 `docs/plan.md` 的"不做"清单）；
- `docs/perf-log.md` 每行都有 A、B、比值、规模、日期；
- 连续三轮无新增失败；`docs/final-report.md` 写清加速比区间与坑。

## 5. 验收（派工方会原样跑这些命令）

```bash
cd {proj}
./test/run_ab.sh                                   # 期望：ALL PASS，用例数 ≥1 且产出数 > 0
./build/riscv64/diff_kernels                       # 期望：0 FAIL
git status --porcelain                             # 期望：干净（都已提交）
```

## 6. 交付格式

1. 本工程内 `git commit`，消息前缀 `G2:` / `G3:` / `G4:`，一个提交一件事；
2. 证据包写到 `{proj}/docs/evidence/G{2,3,4}-<YYYYMMDD>.md`：命令、输出摘要、失败与修正；
3. 回报给派工方一段话：**当前门禁、跑过的命令、关键数字（A/B/比值）、未完成项、需要人拍板的问题**。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="")
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default="data/workorders")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(os.path.join(ROOT, "data/plan.csv"), encoding="utf-8-sig"))
                if False else csv.DictReader(open(os.path.join(ROOT, "data/plan.csv"),
                                                 encoding="utf-8-sig")))
    ids = {x.strip() for x in a.ids.split(",") if x.strip()}
    out = os.path.join(ROOT, a.out)
    os.makedirs(out, exist_ok=True)

    made = []
    for r in rows:
        if a.wave and r["wave"] != a.wave:
            continue
        if ids and r["id"] not in ids:
            continue
        conf = conf_of(r["project"])
        if not conf and not ids:
            continue                      # 还没建骨架的不出单
        short = conf.get("SHORT", r["pkg"].split("/")[-1])
        path = os.path.join(out, f"{r['id']}-{short}.md")
        open(path, "w", encoding="utf-8").write(body(r, conf))
        made.append((r["id"], r["pkg"], r["project"], os.path.relpath(path, ROOT)))

    idx = os.path.join(out, "INDEX.md")
    with open(idx, "w", encoding="utf-8") as f:
        f.write("# 工作单索引\n\n派工方按本项目级排期的顺序开工；每份单子自包含。\n\n")
        f.write("| 编号 | 包 | 工程 | 工作单 |\n|---|---|---|---|\n")
        for i, pkg, proj, rel in made:
            f.write(f"| {i} | `{pkg}` | `{proj}` | [{os.path.basename(rel)}]({rel.split('/')[-1]}) |\n")
        f.write("\n重新生成：`python3 scripts/dispatch.py --wave W1`\n")

    print(f"== 工作单 {len(made)} 份 → {a.out}/（含 INDEX.md）")
    for i, pkg, proj, rel in made:
        print(f"   {i}  {pkg:28s} {proj:22s} {rel}")


if __name__ == "__main__":
    main()
