# rvv —— RISC-V RVV 开源软件移植管理工程

把 Gentoo / ChromiumOS 生态里**已经存在 x86（SSE/AVX）与 ARM（NEON）SIMD 路径**的软件，
系统地移植到 RISC-V RVV 1.0，并对收益做可复核的度量。

- **输入基线**：`simd_x86_aarch64+in+chromium.xlsx`（两张 sheet：`chromiumos`、`generic gentoo`，
  按 NEON / SSE / SSE2 / SSE3 / SSE4 / AVX / AVX2 列出的 167 条记录，去重后 166 个 Gentoo 包）。
- **管理对象**：不是 166 个零散补丁，而是 166 个**独立移植工程**（每个包一个仓库，
  沿用 `../libspeex-rvv` 的工程范式），本仓库负责立项、排序、门禁与汇总。
- **单个工程的范式**：`baseline/`（上游只读参照）+ `src/`（移植工作副本）+ `test/`（A/B 与内核差分）
  + `benchmark/` + `cmake/` + `scripts/` + `docs/` + `skills/`。详见 `docs/03-rvv-playbook.md`。

## 三条工作线

| 工作线 | 内容 | 落地位置 |
|---|---|---|
| **基建线** | 工具链矩阵、QEMU 靶场、真机农场（X60 / X100）、模板与脚手架、CI | W0 波次；Skill `rvv-port-project` |
| **移植线** | 按波次推进的逐包移植工程（子模块） | `projects/` |
| **度量线** | 难度/工作量/优先级评估、门禁证据、加速比与覆盖度看板 | `data/`、`STATUS.md` |

## 目录

```
rvv/
├── README.md
├── docs/
│   ├── 00-program-model.md        项目管理模型：工程形态、状态机 G0–G5、角色、节奏
│   ├── 01-difficulty-rubric.md    难度 D1–D5 与工作量估算模型（含锚点校准）
│   ├── 02-priority-rules.md       优先级判定规则 R1–R6 与三档定义
│   ├── 03-rvv-playbook.md         RVV 移植技术路线：四类路径 + 编码约定 + 工具链矩阵
│   ├── 04-isa-mapping.md          SSE/AVX/NEON → RVV 映射表与高频坑
│   ├── 05-waves.md                波次计划 W0–W7、里程碑、依赖与资源假设
│   ├── 06-acceptance.md           分类型验收口径与证据要求
│   └── 07-ai-schedule.md          AI 算力（60 token/s）下的时间轴重排（含项目级排期）
├── data/
│   ├── inventory.csv              166 包全量清单（来源表、ISA 列、类别、初判）
│   ├── plan.csv                   48 个核心项目：工作量 / 难点 / 优先级 / 波次 / 依赖
│   ├── upstream-probe.json        实测上游元数据（HEAD、SIMD 文件数、RVV 现状），仅元数据
│   ├── status.csv                 在册项目的门禁状态与证据指针（人工维护）
│   └── plan.xlsx                  汇总报表（由 scripts/build-xlsx.py 生成）
├── projects/
│   ├── README.md                  子模块约定与注册流程
│   └── <pkg>-rvv/                 每个移植工程一个 git submodule
├── scripts/
│   ├── new-project.sh             新建移植工程（调用 Skill 的生成器）
│   ├── add-submodule.sh           把已建工程挂进 projects/ 并写 .gitmodules
│   ├── sync.sh                    选择性初始化/更新子模块
│   ├── dashboard.py               data/*.csv → STATUS.md
│   ├── build-xlsx.py              data/*.csv + upstream-probe.json → data/plan.xlsx
│   └── verify.sh                  对本仓库自身做一致性检查
└── STATUS.md                      自动生成的看板（勿手改）
```

## 怎么用

**立一个新项目**（骨架来自 `libspeex-rvv`，由 Skill `rvv-port-project` 生成）：

```bash
./scripts/new-project.sh media-libs/libvpx      # 生成 ../libvpx-rvv 骨架，不下载源码
./scripts/add-submodule.sh media-libs/libvpx    # 挂到 projects/libvpx-rvv
./scripts/sync.sh libvpx                        # 需要时才浅拉取源码
```

**出报表**：

```bash
python3 scripts/build-xlsx.py                   # data/plan.xlsx
python3 scripts/dashboard.py                    # STATUS.md
./scripts/verify.sh                             # 清单完整性 / 子模块一致性
```

## 已落地状态

- 本仓库已 `git init`；`projects/libjpeg-turbo-rvv` 是第一个在册子模块（G0）。
- Skill 位于
  `<workspace>/.user_skills/rvv-port-project`（生成器 + 骨架 + 三份 reference），
  已通过 `quick_validate.py`，并在 `libjpeg-turbo-rvv` / `libvpx-rvv` 上实测：
  native 构建、内核差分 2/2（102 次比较）、`run_ab.sh` ALL PASS、paired 基准可运行。


## 当前判断（摘要，详见 docs 与 data/plan.csv）

- **166 个包里，真正值得按 `libspeex-rvv` 全流程做的只有 48 个**；其余 118 个归入长尾
  （P3，按需插单，不占主线产能）。核心 48 项合计 **1635–2812 人日，计划 2558 人日**
  （≈12.3 人年），加长尾粗估共 3100–3500 人日。
- **上游已有 RVV 的包要立刻摘果子**：`libjpeg-turbo`（15 个 RVV 内核）、`libpng`、`zlib-ng`、
  `pixman`、`openssl`（32 个 RISC-V 汇编）、`libgcrypt`（26 个）、`eigen`（RVV10 后端）、
  `ffmpeg`（151 个 RISC-V 文件）、`vlc`、`ceph`（crc32c）。这批的工作量是"集成 + 缺口 + 调优 + 回归"，
  不是从零内核，**W1 波次优先吃掉**。
- **真正吃产能的是四个方向**：视频编解码（libvpx / aom / openh264 / x264 / x265 / ffmpeg 缺口）、
  科学计算（gromacs / fftw / tensorflow / eigen 调优）、正则与几何（hyperscan / embree）、
  密码学（nettle / botan / crypto++ / openssl 缺口）。合计约占主线工作量 70%。
- **60 token/s 只快 4–5 倍，不是 20 倍**：生成侧 1 人日≈28 分钟（17×），但验证占 60%、
  评审占 15%，单项目墙钟约 `pd×0.05 天`。主线 24 个月 → **约 24 周**（2026-11-16 → 2027-05-04），
  前提是 2 个评审人（3 人可到 17 周）、3–4 个 agent、2–4 块板；评审人减到 1 人即退化为 43 周。详见 `docs/07-ai-schedule.md`。
- **RVV 移植的成本大头不是写内核，是验证**：需要 bit-exact 的包（编解码、定点音频、密码、
  棋类/科学）验证系数取 1.5–2.0，工作量按 1.0 估会系统性低估 40%–100%。

> 所有工作量是**经验估算区间**（人日，熟练 RVV 工程师），不是实测值。估算模型、锚点与
> 置信度说明见 `docs/01-difficulty-rubric.md`；`data/upstream-probe.json` 里的 SIMD 文件计数
> 是实测元数据，用来约束"内核面"的量级，避免凭印象拍数。
