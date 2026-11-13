#!/usr/bin/env python3
"""项目级排期：把人日摊到具体日期、agent 槽位、板卡槽位、评审队列。

输入：data/plan.csv（48 项）+ 波次依赖
资源：agents（每 agent 独占一个项目、24h 连续）、boards（验证 24h 独占）、
      reviewers（8h/日，评审队列单流水线，容量 = 评审人数 人日/日）
输出：data/ai-plan.csv + 控制台摘要（波次窗口、周产能、最晚项目）

用法：python3 scripts/ai-plan.py --tps 60 --agents 8 --boards 8 --reviewers 2
"""
import argparse
import csv
import math
import os
from datetime import date, timedelta

SPLIT = {"gen": 0.25, "ver": 0.60, "hum": 0.15}
TOK_PER_PD = 100_000
BOARD_H_PER_PD = 1.2
HUMAN_MULT = 0.5
BUFFER = 0.15
W0_DAYS = 10.0          # 基建：环境/硬件/CI，AI 压不动

WAVES_FALLBACK = {
    "W1": dict(scope="上游已有 RVV", deps=["W0"]),
    "W2": dict(scope="媒体编解码", deps=["W1"]),
    "W3": dict(scope="音频", deps=["W1"]),
    "W4": dict(scope="安全/压缩/存储", deps=["W2"]),
    "W5": dict(scope="数学科学", deps=["W4"]),
    "W6": dict(scope="平台应用", deps=["W5"]),
}


def load_waves(path="data/waves.csv"):
    """波次依赖由 data/deps.csv 推出（scripts/replan-waves.py 生成）。

    波次顺序即构建顺序；`deps` 为 W0（基建）或更早波次。
    没有 waves.csv 时退回手工基线。
    """
    if not os.path.exists(path):
        return WAVES_FALLBACK
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        d = [x for x in r["deps"].split("|") if x and x != "-"]
        out[r["wave"]] = dict(scope=r.get("scope", ""), deps=d or ["W0"])
    return out
PRIO = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def load_plan(path="data/plan.csv"):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["pd_plan"] = int(r["pd_plan"])
    return rows


def next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


class Pool:
    """非抢占资源池：每成员一个空闲时刻（自起点的天偏移，浮点）。"""

    def __init__(self, n):
        self.free = [0.0] * n

    def acquire(self, earliest, dur):
        i = min(range(len(self.free)), key=lambda k: max(self.free[k], earliest))
        st = max(self.free[i], earliest)
        self.free[i] = st + dur
        return i, st, self.free[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tps", type=float, default=60)
    ap.add_argument("--agents", type=int, default=8)
    ap.add_argument("--boards", type=int, default=8)
    ap.add_argument("--reviewers", type=int, default=2)
    ap.add_argument("--start", default="2026-11-16")
    ap.add_argument("--out", default="data/ai-plan.csv")
    a = ap.parse_args()

    start = date.fromisoformat(a.start)
    rows = load_plan()
    waves = load_waves()

    agents = Pool(a.agents)
    boards = Pool(a.boards)
    reviewer = Pool(1)
    # 评审人按 8h/工作日 → 折算成"人日/日历日"，否则周末会被白算进来
    review_capacity = float(a.reviewers) * 5 / 7

    def off(d):
        return next_weekday(start + timedelta(days=d)).isoformat()

    recs = []
    wave_exit = {}
    for w in waves:
        ready = max(wave_exit.get(d, W0_DAYS) for d in waves[w]["deps"])
        group = [r for r in rows if r["wave"] == w]
        group.sort(key=lambda r: (PRIO[r["priority"]], -r["pd_plan"]))

        for r in group:
            pd = r["pd_plan"]
            gen_h = SPLIT["gen"] * pd * TOK_PER_PD / (a.tps * 3600)
            ver_h = SPLIT["ver"] * pd * BOARD_H_PER_PD
            rev_pd = SPLIT["hum"] * pd * HUMAN_MULT

            gen_dur = gen_h / 24 * (1 + BUFFER)
            ver_dur = ver_h / 24 * (1 + BUFFER)

            ai, g0, g1 = agents.acquire(ready, gen_dur)
            bi, b0, b1 = boards.acquire(g1, ver_dur)
            _, r0, r1 = reviewer.acquire(b1, rev_pd / review_capacity)

            recs.append(dict(
                id=r["id"], pkg=r["pkg"], wave=w, priority=r["priority"],
                difficulty=r["difficulty"], pd=pd,
                tokens=int(SPLIT["gen"] * pd * TOK_PER_PD),
                gen_h=round(gen_h, 1), ver_h=round(ver_h, 1),
                gen_days=round(gen_dur, 2), ver_days=round(ver_dur, 2),
                review_pd=round(rev_pd, 1),
                agent="A%02d" % (ai + 1), board="B%02d" % (bi + 1),
                start=off(g0), gen_end=off(g1),
                verify_end=off(b1), review_end=off(r1)))

        wave_exit[w] = max(float((date.fromisoformat(x["review_end"]) - start).days)
                           for x in recs if x["wave"] == w)

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
        wr.writeheader()
        wr.writerows(recs)

    end_all = max(r["review_end"] for r in recs)
    days_all = (date.fromisoformat(end_all) - start).days
    print(f"项目 {len(recs)} 项；主线结束 {end_all}（{days_all} 天 ≈ {days_all/7:.1f} 周）")
    print()
    print("| 波次 | 项目 | 起 | 止（末次评审） | 人日 | 生成 token |")
    print("|---|---|---|---|---|---|")
    for w in waves:
        g = [r for r in recs if r["wave"] == w]
        print(f"| {w} | {len(g)} | {min(r['start'] for r in g)} | "
              f"{max(r['review_end'] for r in g)} | {sum(r['pd'] for r in g)} | "
              f"{sum(r['tokens'] for r in g)/1e6:.1f}M |")
    print(f"| 合计 | {len(recs)} | {min(r['start'] for r in recs)} | {end_all} | "
          f"{sum(r['pd'] for r in recs)} | {sum(r['tokens'] for r in recs)/1e6:.1f}M |")

    print()
    print("| 周 | 在跑 | agent 机日 | 板卡机日 | 当周完成评审 |")
    print("|---|---|---|---|---|")
    for wk in range(0, math.ceil(days_all / 7) + 1):
        lo, hi = wk * 7, (wk + 1) * 7
        live = [r for r in recs
                if (date.fromisoformat(r["start"]) - start).days < hi
                and (date.fromisoformat(r["verify_end"]) - start).days >= lo]
        done = [r for r in recs
                if lo <= (date.fromisoformat(r["review_end"]) - start).days < hi]
        def ov(off0, dur):
            return max(0.0, min(off0 + dur, hi) - max(off0, lo))
        gen_occ = sum(ov((date.fromisoformat(r["start"]) - start).days, r["gen_days"])
                      for r in live)
        ver_occ = sum(ov((date.fromisoformat(r["gen_end"]) - start).days, r["ver_days"])
                      for r in live)
        print(f"| {wk + 1} | {len(live)} | {gen_occ:.0f}/{a.agents*7} | "
              f"{ver_occ:.0f}/{a.boards*7} | {len(done)} |")

    print()
    print("最晚完成的 5 个项目：")
    for r in sorted(recs, key=lambda x: x["review_end"])[-5:]:
        print(f"  {r['review_end']}  {r['pkg']}（{r['wave']} {r['difficulty']} "
              f"{r['pd']} 人日，agent {r['agent']}，板 {r['board']}）")


if __name__ == "__main__":
    main()
