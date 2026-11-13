# RVV-014 media-libs/zimg → `zimg-rvv`

> 本单由 `scripts/dispatch.py` 生成，是唯一的派工依据。字段冲突时以本单为准。

## 0. 一句话任务

把 `baseline/` 里的上游实现**原样**跑通，逐内核把它改写成 `src/` 下的 RVV 实现，
每个内核都要有**位精确差分 + 成对性能数字**，最后交出 G2/G3/G4 证据包。不改上游语义、不改测试口径。

## 1. 元数据（只读）

| 项 | 值 |
|---|---|
| 包 / 编号 | `media-libs/zimg` / RVV-014 |
| 工程目录 | `~/work/zimg-rvv` |
| 上游 | `https://github.com/sekrit-twc/zimg` @ `67e0603271c080e22c8429856dd4a8a56587e61e` |
| 难度 / 路径 | D3 / B |
| 人日（计划） | 29（区间 20–30） |
| 优先级 / 波次 | P1 / W3 —— 编码与数学底座（x264/HEVC 软解/FFT/Eigen/密码库/存储） |
| 验证口径 | 容差 |
| 当前门禁 | **G0** |
| 上游 RVV 现状 | N |
| 已知难点 | 40 个 SIMD 文件（28 x86 / 12 neon）；resize/colorspace/bitdepth 三类内核；浮点容差可接受，但缩放滤波器系数必须与 C 版一致 |

## 2. 开工前必读（全部绝对路径，按顺序读）

1. `~/work/zimg-rvv/README.md` —— 本工程怎么构建、怎么跑 A/B
2. `~/work/zimg-rvv/skills/rvv-kernel-loop/SKILL.md` —— **每轮七步**，不许自创流程
3. `~/work/zimg-rvv/docs/plan.md` —— 要做什么、不做什么
4. `~/work/rvv/docs/03-rvv-playbook.md` —— 四条路径 A/B/C/D 与尾部掩码纪律
5. `~/work/rvv/docs/04-isa-mapping.md` —— SSE/NEON → RVV 映射表与七个必踩坑
6. `<internal-workspace>/Default/.doubaowork/agent_mode/workspace/.user_skills/rvv-port-project/references/adapt-build-system.md` —— 上游 CMake/autotools/meson 三种接法
7. `<internal-workspace>/Default/.doubaowork/agent_mode/workspace/.user_skills/rvv-port-project/references/gates.md` —— G0→G5 证据要求与"假通过"清单

## 3. 边界（越界即视为返工）

**允许**：在 `~/work/zimg-rvv/src/` 下新增 `*/rvv/*_rvv.c`；改 `cmake/upstream.cmake`；改 `test/`、
`benchmark/` 里的用例与登记表；改本工程 `docs/`；在本工程内 `git commit`。

**禁止**：
- 改 `~/work/zimg-rvv/baseline/` 任何内容（A/B 的参照，改一次全部作废）；
- 用 `-O3` vs `-O2`、改 CPU 频率、开 `-ffast-math` 制造"加速"（A/B 只许差 `RVV_KERNELS`）；
- 改上游语义（饱和、舍入、尾部处理、对齐要求）来"对齐"结果；
- 猜上游 URL 或 SHA；需要换固定点时停下来报给派工方；
- 跨工程改动、动主仓库 `data/` 与 `docs/`（状态回写由派工方做）；
- 用 qemu 的加速比当性能结论（qemu 只证明功能）。

## 4. 推进顺序（每步都要留下证据）

### G2 baseline 全绿
```bash
cd ~/work/zimg-rvv
./scripts/build.sh riscv64            # 缺交叉工具链用 ./scripts/docker-cross.sh
./test/run_ab.sh                      # 现在只有 00_framework，先让它 PASS
# 接上游构建：填 cmake/upstream.cmake，把 A/B 两侧都用的二进制编出来
cp test/cases/00_framework.sh test/cases/01_zimg_decode.sh   # 改成调上游程序，产出确定性文件
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
cd ~/work/zimg-rvv
./test/run_ab.sh                                   # 期望：ALL PASS，用例数 ≥1 且产出数 > 0
./build/riscv64/diff_kernels                       # 期望：0 FAIL
git status --porcelain                             # 期望：干净（都已提交）
```

## 6. 交付格式

1. 本工程内 `git commit`，消息前缀 `G2:` / `G3:` / `G4:`，一个提交一件事；
2. 证据包写到 `~/work/zimg-rvv/docs/evidence/G(2, 3, 4)-<YYYYMMDD>.md`：命令、输出摘要、失败与修正；
3. 回报给派工方一段话：**当前门禁、跑过的命令、关键数字（A/B/比值）、未完成项、需要人拍板的问题**。
