#!/usr/bin/env python3
"""data/plan.xlsx：把 CSV 与探测元数据汇总成报表。

用法：python3 scripts/build-xlsx.py
输出：data/plan.xlsx（总览 / 核心计划 / 全量清单 / 波次计划 / 难度口径 / 图表）
"""
import csv
import json
import os
import unicodedata
from collections import Counter, OrderedDict

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "plan.xlsx")

# 新建文件配色：低饱和表头 + 语义状态色
C_TITLE = "2F5597"
C_HEAD = "D9E2F3"
C_LINE = "B8C7D9"
C_SUMMARY = "E1EAFF"
PRIO_FILL = {"P0": "F8D7DA", "P1": "FFF2CC", "P2": "DDEBF7", "P3": "EDEDED"}
FONT_CN = "微软雅黑"
THIN = Side(style="thin", color=C_LINE)


def dwidth(v):
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
               for ch in str(v or ""))


def style_header(ws, row, ncol, height=30):
    for c in range(1, ncol + 1):
        cell = ws.cell(row, c)
        cell.fill = PatternFill("solid", fgColor=C_HEAD)
        cell.font = Font(name=FONT_CN, bold=True, size=10, color="1F3864")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        b = Border(bottom=THIN)
        cell.border = b
    ws.row_dimensions[row].height = height


def style_body(ws, r1, r2, ncol, numeric_cols=(), center_cols=()):
    for r in range(r1, r2 + 1):
        for c in range(1, ncol + 1):
            cell = ws.cell(r, c)
            cell.font = Font(name=FONT_CN, size=10)
            cell.alignment = Alignment(
                horizontal="right" if c in numeric_cols else
                ("center" if c in center_cols else "left"),
                vertical="center", wrap_text=True)


def fit_cols(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def title_row(ws, text, ncol):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(1, 1)
    c.value = text
    c.fill = PatternFill("solid", fgColor=C_TITLE)
    c.font = Font(name=FONT_CN, bold=True, size=13, color="FFFFFF")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32


def read_csv(name):
    p = os.path.join(DATA, name)
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    plan = read_csv("plan.csv")
    inv = read_csv("inventory.csv")
    probe = json.load(open(os.path.join(DATA, "upstream-probe.json"), encoding="utf-8"))
    pmeta = {r["name"]: r for r in probe["repos"]}

    wb = Workbook()

    # ---------------------------------------------------------------- 总览
    ws = wb.active
    ws.title = "总览"
    title_row(ws, "RISC-V RVV 开源软件移植 · 管理总览", 8)
    ws.sheet_view.showGridLines = False
    fit_cols(ws, [22, 14, 12, 12, 12, 12, 16, 20])

    kpi = [
        ("输入清单", f"{len(inv)} 个包（原始 167 条记录，合并 1 个重名原子）", ""),
        ("核心立项", f"{len(plan)} 个（P0 {sum(1 for r in plan if r['priority']=='P0')} / "
                    f"P1 {sum(1 for r in plan if r['priority']=='P1')} / "
                    f"P2 {sum(1 for r in plan if r['priority']=='P2')} / "
                    f"P3 {sum(1 for r in plan if r['priority']=='P3')}）", ""),
        ("工作量（核心）", f"{sum(int(r['pd_low']) for r in plan)} – "
                        f"{sum(int(r['pd_high']) for r in plan)} 人日，规划值 "
                        f"{sum(int(r['pd_plan']) for r in plan)} 人日", ""),
        ("工作量（含长尾）", "3100 – 3500 人日（≈15–17 人年）", ""),
        ("产能假设", "8 人 × 24 个月 ≈ 3330 人日（0.8 有效系数）", ""),
        ("难度分布", " / ".join(f"{k} {v}" for k, v in
                              sorted(Counter(r["difficulty"] for r in plan).items())), ""),
        ("上游已有 RVV", f"{sum(1 for r in plan if r['rvv_upstream'] in ('Y','partial'))} 项"
                       f"（Y {sum(1 for r in plan if r['rvv_upstream']=='Y')} / "
                       f"partial {sum(1 for r in plan if r['rvv_upstream']=='partial')}）", ""),
        ("口径", "工作量是经验估算区间，不是实测；难度/优先级规则见 docs/01、docs/02", ""),
    ]
    r = 3
    for label, value, _ in kpi:
        ws.cell(r, 1, label).font = Font(name=FONT_CN, bold=True, size=10)
        ws.cell(r, 1).fill = PatternFill("solid", fgColor=C_SUMMARY)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
        ws.cell(r, 2, value).font = Font(name=FONT_CN, size=10)
        ws.cell(r, 2).alignment = Alignment(vertical="center", wrap_text=True)
        ws.row_dimensions[r].height = 22
        r += 1

    # 波次汇总
    r += 1
    ws.cell(r, 1, "波次汇总").font = Font(name=FONT_CN, bold=True, size=11, color=C_TITLE)
    r += 1
    head = ["波次", "项目数", "低(人日)", "高(人日)", "规划(人日)", "占比"]
    for i, h in enumerate(head, 1):
        ws.cell(r, i, h)
    style_header(ws, r, len(head), 24)
    hr = r
    rows = OrderedDict()
    for x in plan:
        t = rows.setdefault(x["wave"], [0, 0, 0, 0])
        t[0] += 1
        t[1] += int(x["pd_low"])
        t[2] += int(x["pd_high"])
        t[3] += int(x["pd_plan"])
    total = sum(t[3] for t in rows.values())
    for w_ in sorted(rows):
        r += 1
        t = rows[w_]
        ws.cell(r, 1, w_)
        ws.cell(r, 2, t[0])
        ws.cell(r, 3, t[1])
        ws.cell(r, 4, t[2])
        ws.cell(r, 5, t[3])
        ws.cell(r, 6, t[3] / total).number_format = "0.0%"
    style_body(ws, hr + 1, r, 6, numeric_cols=(2, 3, 4, 5, 6), center_cols=(1,))
    r += 1
    for i, v in enumerate(["合计", sum(t[0] for t in rows.values()),
                           sum(t[1] for t in rows.values()), sum(t[2] for t in rows.values()),
                           total, 1.0], 1):
        cell = ws.cell(r, i, v)
        cell.font = Font(name=FONT_CN, bold=True, size=10)
        cell.fill = PatternFill("solid", fgColor=C_SUMMARY)
        if i == 6:
            cell.number_format = "0.0%"
    style_body(ws, r, r, 6, numeric_cols=(2, 3, 4, 5, 6), center_cols=(1,))

    # ---------------------------------------------------------------- 核心计划
    ws2 = wb.create_sheet("核心计划")
    ws2.sheet_view.showGridLines = False
    cols = [("id", 9), ("pkg", 26), ("project", 22), ("priority", 9), ("wave", 7),
            ("difficulty", 10), ("pd_low", 8), ("pd_high", 9), ("pd_plan", 9),
            ("validation", 18), ("path", 7), ("rvv_upstream", 12), ("deps", 22),
            ("difficulty_notes", 60), ("rationale", 40)]
    title_row(ws2, "核心 48 项：优先级 / 难度 / 工作量 / 验证口径", len(cols))
    for i, (_, w) in enumerate(cols, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    r = 2
    for i, (k, _) in enumerate(cols, 1):
        ws2.cell(r, i, {"difficulty_notes": "难点", "rationale": "立项理由",
                        "pd_low": "低(人日)", "pd_high": "高(人日)", "pd_plan": "规划(人日)",
                        "pkg": "包", "project": "工程", "priority": "优先级", "wave": "波次",
                        "path": "路径", "rvv_upstream": "上游RVV", "deps": "依赖",
                        "validation": "验证口径", "difficulty": "难度", "id": "编号"}[k])
    style_header(ws2, r, len(cols), 34)
    first = r + 1
    for x in plan:
        r += 1
        for i, (k, _) in enumerate(cols, 1):
            v = x[k]
            if k in ("pd_low", "pd_high", "pd_plan"):
                v = int(v)
            ws2.cell(r, i, v)
        ws2.cell(r, 4).fill = PatternFill("solid", fgColor=PRIO_FILL.get(x["priority"], "FFFFFF"))
    style_body(ws2, first, r, len(cols), numeric_cols=(7, 8, 9), center_cols=(1, 4, 5, 6, 11, 12))
    ws2.freeze_panes = "C3"
    ws2.auto_filter.ref = f"A2:{get_column_letter(len(cols))}{r}"

    # ---------------------------------------------------------------- 全量清单
    ws3 = wb.create_sheet("全量清单")
    ws3.sheet_view.showGridLines = False
    cols3 = [("pkg", 26), ("short", 16), ("category", 16), ("isa_paths", 30),
             ("source_sheets", 20), ("difficulty", 10), ("priority", 9), ("wave", 7),
             ("in_plan", 8), ("merged_into", 14), ("simd_files", 10), ("x86_simd", 9),
             ("arm_simd", 9), ("riscv", 8), ("note", 52)]
    title_row(ws3, "全量清单：166 包 × ISA 归属 × 初判（长尾只给粗档）", len(cols3))
    for i, (_, w) in enumerate(cols3, 1):
        ws3.column_dimensions[get_column_letter(i)].width = w
    r = 2
    labels = {"pkg": "包", "short": "短名", "category": "类别", "isa_paths": "ISA 列",
              "source_sheets": "来源 sheet", "difficulty": "难度", "priority": "优先级",
              "wave": "波次", "in_plan": "立项", "merged_into": "并入",
              "simd_files": "SIMD 文件", "x86_simd": "x86", "arm_simd": "ARM",
              "riscv": "RISC-V", "note": "初判/说明"}
    for i, (k, _) in enumerate(cols3, 1):
        ws3.cell(r, i, labels[k])
    style_header(ws3, r, len(cols3), 30)
    first = r + 1
    for x in inv:
        r += 1
        m = pmeta.get(x["short"])
        vals = [x["pkg"], x["short"], x["category"], x["isa_paths"], x["source_sheets"],
                x["difficulty"], x["priority"], x["wave"], x["in_plan"],
                x["merged_into"] or "-",
                m["simd_path_files"] if m else "", m["x86_simd"] if m else "",
                m["arm_simd"] if m else "", m["riscv"] if m else "", x["note"]]
        for i, v in enumerate(vals, 1):
            ws3.cell(r, i, v)
        ws3.cell(r, 7).fill = PatternFill("solid", fgColor=PRIO_FILL.get(x["priority"], "FFFFFF"))
    style_body(ws3, first, r, len(cols3), numeric_cols=(11, 12, 13, 14),
               center_cols=(6, 7, 8, 9, 10))
    ws3.freeze_panes = "B3"
    ws3.auto_filter.ref = f"A2:{get_column_letter(len(cols3))}{r}"

    # ---------------------------------------------------------------- 波次计划
    ws4 = wb.create_sheet("波次计划")
    ws4.sheet_view.showGridLines = False
    cols4 = [("wave", 8), ("scope", 26), ("n", 8), ("low", 9), ("high", 9), ("plan", 9),
             ("window", 14), ("par", 8), ("exit", 52)]
    widths4 = [8, 26, 8, 10, 10, 10, 14, 8, 60]
    title_row(ws4, "波次计划：内容 / 产能 / 时间窗 / 出口条件", 9)
    fit_cols(ws4, widths4)
    wave_meta = {
        "W0": ("基建（工具链矩阵、靶场、模板与 Skill、CI、看板）", 0, 60, "M1–M2", "2",
               "任意包一条命令跑完 build+ab+bench"),
        "W1": ("上游已有 RVV：集成 + 缺口（图像/压缩/TLS）", 6, None, "M2–M4", "3–4",
               "6 项全部 G4，三条路径有真机加速比"),
        "W2": ("媒体编解码：图像 + 视频", 10, None, "M4–M10", "3–4",
               "libvpx/openh264/ffmpeg 解码 G4；图像四件套 G4"),
        "W3": ("音频与实时通信", 8, None, "M6–M9", "2",
               "opus/webrtc-ap G4，10ms 帧时延不退化"),
        "W4": ("安全 / 压缩 / 存储", 7, None, "M9–M12", "2–3",
               "openssl 缺口闭环；nettle/botan/cryptopp ≥G3"),
        "W5": ("数学与科学计算", 8, None, "M11–M16", "2–3",
               "eigen 调优达标；fftw/gromacs 达性能目标"),
        "W6": ("平台与应用（chromium 等）", 9, None, "M15–M22", "2",
               "chromium 完成集成+缺口，Skia 关键路径达标"),
        "W7": ("长尾（机会型插单）", 118, None, "全程", "≤1", "按需，不设出口"),
    }
    r = 2
    head4 = ["波次", "内容", "项目数", "低(人日)", "高(人日)", "规划(人日)",
             "时间窗", "并行度", "出口条件"]
    for i, h in enumerate(head4, 1):
        ws4.cell(r, i, h)
    style_header(ws4, r, 9, 28)
    first = r + 1
    for w_ in ["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7"]:
        scope, n, w0pd, win, par, exit_ = wave_meta[w_]
        r += 1
        if w_ == "W0":
            lo, hi, pd_ = 0, 0, w0pd
        elif w_ == "W7":
            lo, hi, pd_ = 500, 700, 600
        else:
            t = rows[w_]
            lo, hi, pd_ = t[1], t[2], t[3]
        vals = [w_, scope, n, lo, hi, pd_, win, par, exit_]
        for i, v in enumerate(vals, 1):
            ws4.cell(r, i, v)
    style_body(ws4, first, r, 9, numeric_cols=(3, 4, 5, 6), center_cols=(1, 7, 8))
    # 图表数据区（独立、便于跨表引用）
    r += 2
    ws4.cell(r, 1, "波次").font = Font(name=FONT_CN, bold=True, size=9)
    ws4.cell(r, 2, "低").font = Font(name=FONT_CN, bold=True, size=9)
    ws4.cell(r, 3, "高").font = Font(name=FONT_CN, bold=True, size=9)
    ws4.cell(r, 4, "规划").font = Font(name=FONT_CN, bold=True, size=9)
    chart_start = r
    for w_ in ["W1", "W2", "W3", "W4", "W5", "W6"]:
        t = rows[w_]
        r += 1
        for i, v in enumerate([w_, t[1], t[2], t[3]], 1):
            ws4.cell(r, i, v)

    # ---------------------------------------------------------------- 难度口径
    ws5 = wb.create_sheet("难度口径")
    ws5.sheet_view.showGridLines = False
    fit_cols(ws5, [10, 40, 14, 14, 18])
    title_row(ws5, "难度分级与工作量模型（详见 docs/01-difficulty-rubric.md）", 5)
    r = 2
    head5 = ["等级", "含义", "单内核成本(人日)", "验证系数 V", "本项目数量"]
    for i, h in enumerate(head5, 1):
        ws5.cell(r, i, h)
    style_header(ws5, r, 5, 28)
    d_rows = [
        ("D1", "接口级/开关级：只需接通上游已有派发，无自有内核", "0.2", "1.0",
         sum(1 for x in inv if x["difficulty"] == "D1")),
        ("D2", "内核级、有参照：x86/NEON 侧已有同构实现可逐句对照", "1.0", "1.0–1.5",
         sum(1 for x in inv if x["difficulty"] == "D2")),
        ("D3", "内核级、需自建：只有标量 C 参照，需自行设计向量化", "2.0", "1.5",
         sum(1 for x in inv if x["difficulty"] == "D3")),
        ("D4", "汇编级/严格契约：位精确、常数时间、码流格式约束", "3.5", "1.5–2.0",
         sum(1 for x in inv if x["difficulty"] == "D4")),
        ("D5", "架构级：需重写抽象层或多模块协同（如 fftw 的 simd 层）", "6.0", "2.0",
         sum(1 for x in inv if x["difficulty"] == "D5")),
    ]
    first = r + 1
    for d in d_rows:
        r += 1
        for i, v in enumerate(d, 1):
            ws5.cell(r, i, v)
    style_body(ws5, first, r, 5, numeric_cols=(3, 5), center_cols=(1, 4))
    r += 2
    ws5.cell(r, 1, "工作量模型").font = Font(name=FONT_CN, bold=True, size=11, color=C_TITLE)
    r += 1
    ws5.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws5.cell(r, 1, "工作量 = S + Σ[c(D) × (1 + 0.8×(n_k − 1))] × V + U；"
                  "S 为脚手架 2/4/8 人日，n_k 为同难度内核数（重复内核边际成本 0.8），"
                  "V 为验证系数，U 为上游化/文档 10–20%")
    ws5.cell(r, 1).font = Font(name=FONT_CN, size=10)
    ws5.cell(r, 1).alignment = Alignment(wrap_text=True, vertical="center")
    ws5.row_dimensions[r].height = 46

    # ---------------------------------------------------------------- 图表
    ws6 = wb.create_sheet("图表")
    ws6.sheet_view.showGridLines = False
    title_row(ws6, "波次工作量（人日）", 8)
    ch = BarChart()
    ch.type = "col"
    ch.title = "各波次工作量（人日）：低 / 高 / 规划"
    ch.y_axis.title = "人日"
    ch.x_axis.title = "波次"
    data = Reference(ws4, min_col=2, max_col=4,
                     min_row=chart_start, max_row=chart_start + 6)
    cats = Reference(ws4, min_col=1, min_row=chart_start + 1, max_row=chart_start + 6)
    ch.add_data(data, titles_from_data=True)
    ch.set_categories(cats)
    ch.height = 9
    ch.width = 18
    ws6.add_chart(ch, "A3")

    # ---------------------------------------------------------------- AI 排期
    # 数据来自 scripts/ai-capacity.py（默认 60 token/s / 8 agent / 8 板 / 2 评审）
    ai_path = os.path.join(DATA, "ai-schedule.csv")
    if os.path.exists(ai_path):
        ai = read_csv("ai-schedule.csv")
        ws7 = wb.create_sheet("AI 排期")
        ws7.sheet_view.showGridLines = False
        cols7 = [("wave", 8), ("scope", 34), ("pd", 9), ("gen_tokens", 12),
                 ("gen_agent_h", 12), ("verify_board_h", 13), ("reviewer_pd", 11),
                 ("start", 12), ("end", 12), ("calendar_days", 11)]
        fit_cols(ws7, [8, 34, 10, 13, 13, 14, 12, 12, 12, 11] + [12])
        title_row(ws7, "AI 算力（60 token/s）下的排期：人日 → token / 机时 / 评审",
                  len(cols7))
        labels7 = {"wave": "波次", "scope": "内容", "pd": "人日",
                   "gen_tokens": "生成 token", "gen_agent_h": "生成(agent-h)",
                   "verify_board_h": "验证(板-h)", "reviewer_pd": "评审(人日)",
                   "start": "开始", "end": "结束", "calendar_days": "日历(天)"}
        r7 = 2
        for i, (k, _) in enumerate(cols7, 1):
            ws7.cell(r7, i, labels7[k])
        style_header(ws7, r7, len(cols7), 32)
        first7 = r7 + 1
        for x in ai:
            r7 += 1
            for i, (k, _) in enumerate(cols7, 1):
                v = x[k]
                if k in ("pd", "gen_agent_h", "verify_board_h", "reviewer_pd", "calendar_days"):
                    try:
                        v = float(v)
                        v = int(v) if v == int(v) else v
                    except ValueError:
                        pass
                elif k == "gen_tokens":
                    try:
                        v = f"{int(v) / 1e6:.1f}M"
                    except ValueError:
                        pass
                ws7.cell(r7, i, v)
        style_body(ws7, first7, r7, len(cols7), numeric_cols=(3, 4, 5, 6, 7, 10),
                   center_cols=(1, 8, 9))

        # 参数脚注（来自第一行，避免每行重复）
        r7 += 2
        ws7.merge_cells(start_row=r7, start_column=1, end_row=r7, end_column=10)
        x0 = ai[0]
        ws7.cell(r7, 1, f"参数：tps={x0['tps']}  agent={x0['agents']}  "
                        f"板卡={x0['boards']}  评审人={x0['reviewers']}；"
                        f"拆分 生成25%/验证60%/评审15%；1 人日≈100k 输出 token、1.2 板时。"
                        f"重算：python3 scripts/ai-capacity.py --reviewers 3")
        ws7.cell(r7, 1).font = Font(name=FONT_CN, size=9, color="595959")
        ws7.cell(r7, 1).alignment = Alignment(wrap_text=True, vertical="center")
        ws7.row_dimensions[r7].height = 34

    # ---------------------------------------------------------------- 项目排期
    plan_path = os.path.join(DATA, "ai-plan.csv")
    if os.path.exists(plan_path):
        pr = read_csv("ai-plan.csv")
        ws8 = wb.create_sheet("项目排期")
        ws8.sheet_view.showGridLines = False
        cols8 = [("id", 10), ("pkg", 28), ("wave", 7), ("priority", 8), ("difficulty", 9),
                 ("pd", 7), ("tokens", 10), ("agent", 8), ("board", 7),
                 ("start", 11), ("verify_end", 11), ("review_end", 11)]
        fit_cols(ws8, [10, 28, 8, 9, 10, 8, 10, 8, 8, 12, 12, 12])
        title_row(ws8, "项目级排期：人日 → 日期 / agent 槽 / 板卡槽 / 评审（48 项）", len(cols8))
        labels8 = {"id": "编号", "pkg": "包", "wave": "波次", "priority": "优先级",
                   "difficulty": "难度", "pd": "人日", "tokens": "生成 token",
                   "agent": "agent", "board": "板卡", "start": "起",
                   "verify_end": "验证完", "review_end": "评审完"}
        r8 = 2
        for i, (k, _) in enumerate(cols8, 1):
            ws8.cell(r8, i, labels8[k])
        style_header(ws8, r8, len(cols8), 30)
        first8 = r8 + 1
        for x in sorted(pr, key=lambda t: (t["wave"], t["review_end"])):
            r8 += 1
            for i, (k, _) in enumerate(cols8, 1):
                v = x[k]
                if k in ("pd",):
                    v = int(v)
                elif k == "tokens":
                    v = f"{int(v) / 1e3:.0f}k"
                ws8.cell(r8, i, v)
            ws8.cell(r8, 4).fill = PatternFill("solid", fgColor=PRIO_FILL.get(x["priority"], "FFFFFF"))
        style_body(ws8, first8, r8, len(cols8), numeric_cols=(6, 7),
                   center_cols=(1, 3, 4, 5, 8, 9, 10, 11, 12))
        ws8.freeze_panes = "C3"
        ws8.auto_filter.ref = f"A2:{get_column_letter(len(cols8))}{r8}"
        r8 += 2
        ws8.merge_cells(start_row=r8, start_column=1, end_row=r8, end_column=len(cols8))
        ws8.cell(r8, 1, "生成：python3 scripts/ai-plan.py；时间窗含 1.15× 返工缓冲，"
                        "评审按 8h/工作日、容量=评审人数 人日/日。")
        ws8.cell(r8, 1).font = Font(name=FONT_CN, size=9, color="595959")
        ws8.cell(r8, 1).alignment = Alignment(wrap_text=True, vertical="center")
        ws8.row_dimensions[r8].height = 28

    wb.save(OUT)
    print("written:", OUT)


if __name__ == "__main__":
    main()
