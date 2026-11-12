#!/usr/bin/env python3
"""data/plan.csv + data/status.csv → STATUS.md（看板，勿手改）。

用法：python3 scripts/dashboard.py [--check]
  --check  有阻塞/超期项时以退出码 1 结束（供 CI 用）
"""
import csv
import os
import sys
from collections import Counter, OrderedDict
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "STATUS.md")
GATES = ["G0", "G1", "G2", "G3", "G4", "G5"]
STALE_DAYS = 14


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    plan = load("plan.csv")
    status = load("status.csv")
    st = {r["id"]: r for r in status}

    today = date.today()
    missing = [r["id"] for r in plan if r["id"] not in st]
    unknown = [r["id"] for r in status if r["id"] not in {p["id"] for p in plan}]

    stale, blocked = [], []
    for r in status:
        try:
            upd = datetime.strptime(r["updated"], "%Y-%m-%d").date()
        except ValueError:
            stale.append((r, "日期格式无效"))
            continue
        if (today - upd).days > STALE_DAYS and r["gate"] != "G5":
            stale.append((r, f"{(today - upd).days} 天未更新"))
        if r["blocker"].strip():
            blocked.append((r, r["blocker"]))

    lines = []
    a = lines.append
    a("# 移植工程看板")
    a("")
    a(f"> 由 `scripts/dashboard.py` 生成于 {today.isoformat()}；数据源 `data/status.csv` + `data/plan.csv`。"
      "改数据，不要改这里。")
    a("")
    a("## 1. 总览")
    a("")
    a("| 指标 | 值 |")
    a("|---|---|")
    a(f"| 在册项目 | {len(plan)} |")
    a(f"| 门禁分布 | " + " / ".join(
        f"{g} {sum(1 for r in status if r['gate']==g)}" for g in GATES) + " |")
    g4 = sum(1 for r in status if r["gate"] in ("G4", "G5"))
    a(f"| 达 G4 及以上 | {g4} / {len(plan)}（{g4/len(plan)*100:.0f}%） |")
    a(f"| 阻塞项 | {len(blocked)} |")
    a(f"| 超 {STALE_DAYS} 天未更新 | {len(stale)} |")
    a("")

    a("## 2. 按波次")
    a("")
    a("| 波次 | 项目数 | 规划人日 | G4+ | 进度 |")
    a("|---|---|---|---|---|")
    waves = OrderedDict()
    for p in plan:
        w = waves.setdefault(p["wave"], {"n": 0, "pd": 0, "done": 0})
        w["n"] += 1
        w["pd"] += int(p["pd_plan"])
        if st.get(p["id"], {}).get("gate") in ("G4", "G5"):
            w["done"] += 1
    for w_ in sorted(waves):
        d = waves[w_]
        a(f"| {w_} | {d['n']} | {d['pd']} | {d['done']} | {d['done']/d['n']*100:.0f}% |")
    a("")

    a("## 3. 在册项目")
    a("")
    a("| 编号 | 包 | 工程 | 优先级 | 波次 | 门禁 | 负责人 | 更新 | 阻塞 |")
    a("|---|---|---|---|---|---|---|---|---|")
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    for p in sorted(plan, key=lambda x: (x["wave"], order.get(x["priority"], 9), x["id"])):
        s = st.get(p["id"], {})
        a(f"| {p['id']} | `{p['pkg']}` | `{p['project']}` | {p['priority']} | {p['wave']} | "
          f"{s.get('gate','?')} | {s.get('owner','') or '-'} | {s.get('updated','')} | "
          f"{s.get('blocker','') or '-'} |")
    a("")

    if blocked:
        a("## 4. 阻塞项")
        a("")
        for r, why in blocked:
            a(f"- `{r['pkg']}`（{r['gate']}）：{why}")
        a("")
    if stale:
        a("## 5. 需要刷新")
        a("")
        for r, why in stale:
            a(f"- `{r['pkg']}`：{why}")
        a("")
    if missing:
        a("## 6. 缺少状态行（数据问题）")
        a("")
        a("- " + ", ".join(missing))
        a("")

    open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"written: {OUT}（{len(plan)} 项，G4+ {g4}，阻塞 {len(blocked)}）")

    if "--check" in sys.argv and (blocked or missing or unknown or stale):
        print("check: 有问题（阻塞/缺行/超期）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
