#!/usr/bin/env python3
"""按依赖关系重排构建顺序（波次）。

规则（顺序不能换）：
1. 硬依赖（hard）与归因依赖（bench）决定层级：layer = 1 + max(layer(dep))；
   soft 只记录，不阻塞（它们是"经验复用"，不是"必须先完成"）。
2. 已完成的项目（G2 及以上）钉在原波次，作为后续项的可用前提。
3. 同层内按优先级、再按工作量从大到小排——重的先落地，避免尾段堆积。
4. 每波按人日预算装填（默认 = 剩余总量 / 剩余波次数），允许 5% 超出，
   装不下的大项单独提前一波，不拆包。
5. 依赖未就绪的项不进入当前波（哪怕优先级为 P0）。

用法：
  python3 scripts/replan-waves.py --dry-run
  python3 scripts/replan-waves.py            # 写回 data/plan.csv
"""
import argparse
import csv
import os

HARD_BENCH = ("hard", "bench")
PRIO = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="data/plan.csv")
    ap.add_argument("--deps", default="data/deps.csv")
    ap.add_argument("--status", default="data/status.csv")
    ap.add_argument("--target", type=float, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan = load(a.plan)
    deps = load(a.deps)
    status = {r["project"]: r["gate"] for r in load(a.status)}

    name = {r["pkg"]: r["project"] for r in plan}
    pd = {r["project"]: int(r["pd_plan"]) for r in plan}
    prio = {r["project"]: r["priority"] for r in plan}

    edges = [(d["from_project"], d["to_project"], d["kind"]) for d in deps]
    for f, t, _ in edges:
        if f not in pd or t not in pd:
            raise SystemExit(f"依赖边引用了不在计划表里的工程：{f} -> {t}")

    # 层级（最长路径），只走 hard/bench
    layer = {p: 0 for p in pd}
    for _ in range(len(pd)):
        changed = False
        for f, t, k in edges:
            if k in HARD_BENCH:
                if layer[f] < layer[t] + 1:
                    layer[f] = layer[t] + 1
                    changed = True
        if not changed:
            break
    else:
        raise SystemExit("依赖环：hard/bench 边无法拓扑排序")

    done = [p for p, g in status.items() if g not in ("G0", "G1")]
    done = [p for p in done if p in pd]
    wave = {p: None for p in pd}
    for r in plan:
        if r["project"] in done:
            wave[r["project"]] = r["wave"]

    waves = sorted({r["wave"] for r in plan})
    start_w = max(w for w in waves if any(wave[p] == w for p in done))
    remaining = [w for w in waves if w > start_w]
    rest_pd = sum(pd[p] for p in pd if wave[p] is None)
    target = a.target or rest_pd / len(remaining)

    # 依赖就绪判定：hard/bench 的前置必须已排进更早的波
    order = {w: i for i, w in enumerate(waves)}

    # 优先级闸门：早期波次先做高优先级，P2/P3 只在后段填缝（避免"重量级波次里塞小项目"）
    gate = {w: {"W2": 1, "W3": 1, "W4": 2, "W5": 3, "W6": 3}.get(w, 3) for w in waves}

    for w in remaining:
        while True:
            ready = []
            for p in pd:
                if wave[p] is not None:
                    continue
                if PRIO[prio[p]] > gate[w]:
                    continue
                must = [t for f, t, k in edges if f == p and k in HARD_BENCH]
                if all(wave[t] is not None and order[wave[t]] < order[w] for t in must):
                    ready.append(p)
            if not ready:
                break
            ready.sort(key=lambda p: (PRIO[prio[p]], -pd[p], layer[p]))
            used = sum(pd[q] for q in pd if wave[q] == w)
            placed = False
            for p in ready:
                if used + pd[p] <= target * 1.05:
                    wave[p] = w
                    used += pd[p]
                    placed = True
                    break
            if not placed:
                if used == 0:      # 本波空着且单项就超预算：整项放进来，不拆分
                    wave[ready[0]] = w
                else:
                    break            # 预算装满，进下一波
        if all(wave.values()):
            break

    # 剩余项兜底：硬塞进最后一波（正常情况下到不了这里）
    last = remaining[-1]
    for p in pd:
        if wave[p] is None:
            wave[p] = last
            print(f"[warn] 兜底：{p} 放进 {last}")

    # 回写 deps 字段（只写 hard/bench，soft 留在 deps.csv）
    for r in plan:
        p = r["project"]
        must = [t for f, t, k in edges if f == p and k in HARD_BENCH]
        soft = [t for f, t, k in edges if f == p and k == "soft"]
        parts = []
        if must:
            parts.append("/".join(sorted(must)))
        if soft:
            parts.append("软:" + "/".join(sorted(soft)))
        r["deps_new"] = "；".join(parts) if parts else "-"
        r["layer_new"] = str(layer[p])
        r["wave_new"] = wave[p]

    # 报告
    print(f"预算/波：{target:.0f} 人日；层级最大 {max(layer.values())}")
    print()
    print("| 波次 | 项数 | 人日 | 项目 |")
    print("|---|---|---|---|")
    for w in waves:
        g = sorted([p for p in pd if wave[p] == w],
                   key=lambda p: (layer[p], PRIO[prio[p]], -pd[p]))
        print(f"| {w} | {len(g)} | {sum(pd[p] for p in g)} | "
              + "，".join(f"{p}({layer[p]},{pd[p]})" for p in g) + " |")
    print()
    moved = [(r["project"], r["wave"], r["wave_new"])
             for r in plan if r["wave"] != r["wave_new"]]
    print(f"波次变化 {len(moved)} 项：")
    for p, o, n in moved:
        print(f"  {p}: {o} -> {n}")

    if a.dry_run:
        return

    fields = list(plan[0].keys())
    for extra in ("layer", "deps_new"):
        pass
    if "layer" not in fields:
        fields.insert(fields.index("wave") + 1, "layer")
    with open(a.plan, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        for r in plan:
            r["wave"] = r["wave_new"]
            r["layer"] = r["layer_new"]
            old_deps = r["deps"]
            r["deps"] = r["deps_new"]
            r.pop("wave_new", None)
            r.pop("layer_new", None)
            r.pop("deps_new", None)
            wr.writerow(r)

    # 波次级依赖：由包级边自动推出
    # 波次是顺序阶段：第 n 波天然依赖第 n-1 波，再叠加包级跨波依赖
    wdeps = {}
    for i, w in enumerate(waves):
        ds = set()
        for f, t, k in edges:
            if k in HARD_BENCH and wave[f] == w and wave[t] != w:
                ds.add(wave[t])
        if i > 0:
            ds.add(waves[i - 1])
        ds.discard(w)
        wdeps[w] = sorted(ds)
    with open("data/waves.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["wave", "items", "pd", "deps"])
        for w in waves:
            g = [p for p in pd if wave[p] == w]
            wr.writerow([w, len(g), sum(pd[p] for p in g),
                         "|".join(wdeps[w]) if wdeps[w] else "-"])
    print("\n写回 data/plan.csv、data/waves.csv")


if __name__ == "__main__":
    main()
