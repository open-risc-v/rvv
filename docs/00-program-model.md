# 00 项目管理模型

## 1. 为什么一包一工程

167 个包如果做成一个大仓库，会出现三个必然问题：构建系统互相冲突、验证口径不统一、
单点回归拖死全量 CI。因此沿用 `libspeex-rvv` 已经验证过的形态：**每个包一个独立仓库**，
本仓库只做两件事——排序立项、汇总度量。工程之间唯一的耦合是"共享基建"
（工具链、QEMU 靶场、真机、模板、验证脚本），这些放在 W0 统一交付，不重复建设。

单个工程（`<pkg>-rvv`）的标准形态：

```
baseline/     上游代码快照，只读，A/B 的参照系（记录版本、sha256、获取方式）
src/          移植工作副本；RVV 内核集中放 src/<lib>/rvv/
test/         A/B 工具（bit-exact / 容差）+ 内核级差分测试（注册进 CTest）+ cpu_probe
benchmark/    端到端基准（paired 交替测量）
cmake/        工具链文件 + config.h 模板
scripts/      build / docker-cross / device-test / paired-bench
docs/         plan.md、rvv-notes.md、perf-log.md、progress.md、final-report.md、ref/
skills/       该工程的优化循环方法论（由模板带入，随包演进）
```

## 2. 状态机（门禁即交付物）

每个项目在 `data/status.csv` 里只有一个状态，状态只能逐级推进，**每一级的通过必须有证据文件**：

| 状态 | 含义 | 通过证据（缺一不可） |
|---|---|---|
| `G0 planned` | 已立项：难度、工作量、优先级、依赖已定 | `data/plan.csv` 行 + 立项说明 |
| `G1 scaffolded` | 骨架就位：目录、构建、A/B 工具、cpu_probe 可跑 | `docs/progress.md` 首条 + `./test/ab_run.sh` 可执行 |
| `G2 baseline-green` | 目标机（或 qemu）上 baseline 与 src（未开核）结果一致 | `docs/perf-log.md` 的基线表 + A/B PASS 记录 |
| `G3 kernels` | 内核按 plan.md 逐个落地，每个都有差分测试 | CTest 全绿 + `perf-log.md` 逐轮数据 |
| `G4 converged` | 收敛：无 ≥3% 未向量化热点且单轮增益 <2% | 剖析截图/占比表 + 收敛判定段 |
| `G5 upstreamed` | 补丁上游化（PR 合并或维护分支发布） | PR 链接或补丁集目录 |

**状态回退是允许的**（例如上游 rebase 后 A/B 失败 → 回到 G2），但必须在 `status.csv` 里
写原因。看板只认 `status.csv`，不认口头进度。

## 3. 角色与节奏

| 角色 | 职责 |
|---|---|
| 规划（1 人） | 维护 plan/inventory、难度与工作量口径、波次与资源；对本仓库做 verify |
| 基建（1 人） | 工具链矩阵、QEMU 靶场、真机农场、模板与 Skill、CI、看板 |
| 移植工程师（3–4 人） | 按波次认领项目，负责 G1→G5 全过程 |
| 评审（轮值） | 每轮结束做一次独立审查（参照 libspeex-rvv 的 code-review 文档形态） |

节奏：**两周一个迭代**，每迭代每人只推进 1 个项目（大包允许 2 人共享一个项目，
按内核族切分）。每个迭代末必须产出：`perf-log` 新增轮次、看板更新、至少一个门禁状态变化。

## 4. 度量口径（看板只认这几个数）

1. **A/B 通过率**：在册项目中 `G2 及以后` 且最近一次 A/B PASS 的比例。
2. **加速比**：目标机 paired 基准（同会话、交替、≥5 对取中位），分母是同编译选项的
   `RVV_KERNELS=OFF` 构建，**不是标量 C**（否则会虚高 2–3 倍）。
3. **覆盖度 f**：Amdahl 反推的热点覆盖比例，用来判断"还值不值得投"。
4. **人均产出**：每迭代落地的内核数（含差分测试），用于校准工作量模型。

## 5. 与 `libspeex-rvv` 的关系

`libspeex-rvv` 是本工程的**首个已完成样本**，同时是模板与校准锚点：

- 形态锚点：目录布局、A/B 门、paired 基准、毒化矩阵、perf-log 轮次记录，全部照搬。
- 工作量锚点：约 29 轮迭代、21 个 RVV override 点、单人两周量级 →
  **≈1.5–2 个内核/人日**（已有脚手架、已有差分测试的前提下）。
  模型见 `docs/01-difficulty-rubric.md`。
- 它本身也登记为 `projects/libspeex-rvv`（用 `speexdsp` 行引用，避免重复立项）。
