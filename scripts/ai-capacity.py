#!/usr/bin/env python3
"""按 AI 输出算力（默认 60 token/s）重算排期，输出 data/ai-schedule.csv 与 markdown 表。

模型（三个资源、三份系数，全部可调）：
  工作量拆分  gen 25% / verify 60% / human 15%（验证占比来自 libspeex-rvv 实测）
  生成侧      1 人日 ≈ 100k 输出 token（含思考、工具调用、日志回读的放大）
  验证侧      1 人日 ≈ 1.2 机时（构建 + 差分 + A/B + 基准 + 毒化矩阵，含失败重跑）
  评审侧      人日 ×0.5（AI 先把证据嚼碎，人只做判断）
  日历        生成可 24h 跑；验证受板卡数限制；评审受评审人 × 8h/日 限制
用法：
  python3 scripts/ai-capacity.py --tps 60 --agents 8 --boards 8 --reviewers 2
"""
import argparse
import csv
import math
from datetime import date, timedelta

ROOT = "."
SPLIT = {"gen": 0.25, "ver": 0.60, "hum": 0.15}
TOK_PER_PD = 100_000
BOARD_H_PER_PD = 1.2
HUMAN_MULT = 0.5
BUFFER = 0.15          # 交接、等待、返工
W0_PD = 60

# 波次依赖（前置波次完成后才起，W3 可与 W2 并行）
WAVES = {
    "W0": dict(scope="基建：工具链/靶场/模板/CI/看板", deps=[]),
    "W1": dict(scope="上游已有 RVV：集成 + 缺口", deps=["W0"]),
    "W2": dict(scope="媒体编解码：图像 + 视频", deps=["W1"]),
    "W3": dict(scope="音频与实时通信", deps=["W1"]),
    "W4": dict(scope="安全 / 压缩 / 存储", deps=["W2"]),
    "W5": dict(scope="数学与科学计算", deps=["W4"]),
    "W6": dict(scope="平台与应用（chromium 等）", deps=["W5"]),
}


def load(path="data/plan.csv"):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["pd_plan"] = int(r["pd_plan"])
    return rows


def wave_pd(rows):
    out = {w: 0 for w in WAVES}
    out["W0"] = W0_PD
    for r in rows:
        out[r["wave"]] = out.get(r["wave"], 0) + r["pd_plan"]
    return out


def next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def workdays(start, n):
    """从 start 起数 n 个工作日，返回最后一个工作日。"""
    d = next_weekday(start)
    k = 0
    while k < max(1, n):
        k += 1
        if k < max(1, n):
            d += timedelta(days=1)
            d = next_weekday(d)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tps", type=float, default=60)
    ap.add_argument("--agents", type=int, default=8)
    ap.add_argument("--boards", type=int, default=8)
    ap.add_argument("--reviewers", type=int, default=2)
    ap.add_argument("--start", default="2026-11-16")
    ap.add_argument("--tail-pd", type=int, default=600)
    ap.add_argument("--out", default="data/ai-schedule.csv")
    a = ap.parse_args()

    rows = load()
    pds = wave_pd(rows)
    pds["W7"] = a.tail_pd

    # 三资源需求
    gen_tok_h = a.tps * 3600
    res = {}
    for w, pd in pds.items():
        gen_tok = pd * SPLIT["gen"] * TOK_PER_PD
        res[w] = dict(
            pd=pd,
            gen_tok=gen_tok,
            gen_h=gen_tok / gen_tok_h,
            ver_gh=pd * SPLIT["ver"] * BOARD_H_PER_PD,
            hum_pd=pd * SPLIT["hum"] * HUMAN_MULT,
        )

    # 日历：生成按 agents 并行（24h 连续），验证按 boards，评审按 reviewers×8h
    sched = {}
    start = date.fromisoformat(a.start)
    for w in ["W0", "W1", "W2", "W3", "W4", "W5", "W6"]:
        r = res[w]
        dep_end = max([sched[d]["end"] for d in WAVES[w]["deps"]], default=None)
        st = next_weekday(start if dep_end is None else dep_end + timedelta(days=1))
        gen_days = math.ceil(r["gen_h"] / (24 * a.agents))
        ver_days = math.ceil(r["ver_gh"] / (24 * a.boards))
        rev_days = math.ceil(r["hum_pd"] / a.reviewers)   # 工作日
        # 生成→验证流水；评审与验证部分重叠但受评审人限制，取最长者
        span = max(gen_days + ver_days, rev_days) * (1 + BUFFER)
        days = max(1, math.ceil(span))
        if w == "W0":      # 基建主要是环境与硬件配置，AI 压不动，至少 2 周
            days = max(days, 10)
        end = workdays(st, days)
        sched[w] = dict(start=st, end=end, days=(end - st).days + 1,
                        gen_days=gen_days, ver_days=ver_days, rev_days=rev_days)

    # 长尾：机会型，按 1 agent 插单，不占主线日历
    tail = res["W7"]

    total = dict(pd=sum(v["pd"] for v in res.values()),
                 gen_tok=sum(v["gen_tok"] for v in res.values()),
                 gen_h=sum(v["gen_h"] for v in res.values()),
                 ver_gh=sum(v["ver_gh"] for v in res.values()),
                 hum_pd=sum(v["hum_pd"] for v in res.values()))

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["wave", "scope", "pd", "gen_tokens", "gen_agent_h", "verify_board_h",
                     "reviewer_pd", "start", "end", "calendar_days", "agents", "boards",
                     "reviewers", "tps"])
        for w in list(WAVES) + ["W7"]:
            r = res[w]
            s = sched.get(w, {})
            wr.writerow([w, WAVES.get(w, {}).get("scope", "长尾（机会型插单）"),
                         r["pd"], int(r["gen_tok"]), round(r["gen_h"], 1),
                         round(r["ver_gh"], 1), round(r["hum_pd"], 1),
                         s.get("start", "-"), s.get("end", "-"), s.get("days", "-"),
                         a.agents, a.boards, a.reviewers, int(a.tps)])

    # ---------------- 输出 markdown
    print("| 波次 | 内容 | 人日 | 生成 token | 生成(agent-h) | 验证(板-h) | 评审(人日) | 日历 |")
    print("|---|---|---|---|---|---|---|---|")
    for w in list(WAVES) + ["W7"]:
        r = res[w]
        s = sched.get(w, {})
        cal = f"{s['start']} → {s['end']}（{s['days']}d）" if s else "全程插单"
        print(f"| {w} | {WAVES.get(w, {}).get('scope', '长尾')} | {r['pd']} | "
              f"{r['gen_tok']/1e6:.1f}M | {r['gen_h']:.0f} | {r['ver_gh']:.0f} | "
              f"{r['hum_pd']:.0f} | {cal} |")
    print(f"| **合计** | — | **{total['pd']}** | **{total['gen_tok']/1e6:.1f}M** | "
          f"**{total['gen_h']:.0f}** | **{total['ver_gh']:.0f}** | **{total['hum_pd']:.0f}** | — |")
    print()
    end6 = sched["W6"]["end"]
    print(f"主线结束：{end6}；总日历 {((end6 - date.fromisoformat(a.start)).days)/7:.1f} 周")
    print(f"评审瓶颈：{total['hum_pd']:.0f} 人日 / {a.reviewers} 人 = "
          f"{total['hum_pd']/a.reviewers:.0f} 工作日 ≈ {total['hum_pd']/a.reviewers/5:.1f} 周")


if __name__ == "__main__":
    main()
