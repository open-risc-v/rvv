# 工程规格（project.conf 与目录约定）

## 1. 命名

| 输入 atom | 仓库名 | 说明 |
|---|---|---|
| `media-libs/libvpx` | `libvpx-rvv` | 常规：`<short>-rvv` |
| `media-libs/libsdl2` | `SDL2-rvv` | 大小写与常见名 |
| `dev-libs/crypto++` | `cryptopp-rvv` | 与上游常用名对齐 |
| `media-libs/webrtc-audio-processing` | `webrtc-ap-rvv` | 过长时缩写 |
| `media-libs/libpng-compat` | 不立项 | 兼容包并入主包 |

生成位置：默认与主仓库同级（`../<repo>`），可用 `--dir` 改。
主仓库 `scripts/new-project.sh` 已经把 `--dir` 预置成主仓库的父目录。

## 2. project.conf 字段

| 字段 | 含义 | 谁填 |
|---|---|---|
| `PKG` | Gentoo atom，必须与主仓库 `inventory.csv` 一致 | 生成器 |
| `SHORT` | atom 末段 | 生成器 |
| `REPO` | 仓库名 | 生成器 |
| `RVV_ID` | 主仓库 `plan.csv` 的编号（`RVV-0xx`） | 生成器（从 plan.csv 带出） |
| `DIFFICULTY` | D1–D5 | 生成器（plan.csv） |
| `PATH_KIND` | A 集成 / B 参照重写 / C 汇编复原 / D 架构重构 | 生成器（plan.csv） |
| `PRIORITY` | P0–P3 | 生成器（plan.csv） |
| `WAVE` | W1–W7 | 生成器（plan.csv） |
| `VALIDATION` | bit-exact / 一致 / 容差 / 集成+缺口 | 生成器（plan.csv） |
| `UPSTREAM_URL` | 上游 git 地址；**为空时 fetch-upstream 拒绝执行** | 人确认后填 |
| `UPSTREAM_SHA` | 40 位 commit；A/B 复现的唯一依据 | 人确认后填 |
| `UPSTREAM_TAG` | 可选，与 SHA 二选一 | 人 |
| `LICENSE` | 上游许可证（GPL 项目要单独标注） | 生成器 |
| `BASELINE_DIR` / `SRC_DIR` | 默认 `baseline` / `src` | 生成器 |
| `BENCH_CMD` | 端到端基准命令（可选） | G2 后填 |
| `CREATED` | 生成日期 | 生成器 |
| `OWNER` | 负责人 | 分配时填 |
| `GATE` | G0–G5，唯一状态字段 | 负责人每次升门禁时改 |

**规则**：`UPSTREAM_URL` 宁可为空，也不要猜。主仓库 `plan.csv` 里的 `upstream` 字段是
探测脚本的仓库键名，不是 URL；生成器不会把它当 URL 写入。

## 3. 目录与职责

```
src/       可编辑的移植副本。RVV 内核放 src/<lib>/rvv/，用 <module>_rvv.h + OVERRIDE_* 宏接入。
baseline/  上游只读快照，由 fetch-upstream.sh 按 URL+SHA 重建；不入库、不得打补丁。
test/      run_ab.sh（门禁）、cases/（用例）、diff_kernels.c（内核差分）、cpu_probe.c（探测）。
benchmark/ pair_bench.sh + cases/（每用例打印一个毫秒数）。
cmake/     toolchain-riscv64-linux.cmake（交叉）+ upstream.cmake（上游接入，G1 填）。
scripts/   build.sh / docker-cross.sh / device-test.sh / fetch-upstream.sh / Dockerfile.buildenv。
docs/      plan.md（范围与通过标准）/ rvv-notes.md（坑）/ perf-log.md / progress.md / final-report.md。
skills/rvv-kernel-loop/SKILL.md   单工程迭代循环的操作手册。
```

## 4. 与主仓库的关系

- 主仓库只读 `project.conf` 的 `PKG` 与目录名做一致性校验（`scripts/verify.sh`）；
  状态（GATE/OWNER）以 `data/status.csv` 为准，`project.conf` 的 `GATE` 是工程侧副本。
- 改了 `project.conf` 的 `GATE` 之后，同步更新 `data/status.csv` 对应行，
  并跑 `python3 scripts/dashboard.py` 刷新 `STATUS.md`。

## 5. 生成后必须人工确认的三件事

1. `UPSTREAM_URL` 是否正确（打开看一次，不要凭包名推 URL）；
2. `UPSTREAM_SHA` 是否固定（不固定就没有可复现的 A/B）；
3. `PATH_KIND` 与 `VALIDATION` 是否与主仓库 `plan.csv` 一致（不一致时以 plan.csv 为准并改回来）。
